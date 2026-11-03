"""Persistent SAT searches over the original SALB3PM I/E encodings.

The reference Sudoku solver uses binary search with temporary assumptions for
Multiple SAT and permanently improving objective bounds for Incremental SAT:
https://github.com/Longnguyen1555/SAT_Sudoku_Solver/blob/782e5ae5b0b7cfbe90d14d232bbfbef67f753654/main.py

Here the existing E variables replace Sudoku's preference totalizer. The unary
I formulation already exposes bound literals; the binary E formulation uses
the same PBEnc.leq bound encoding as the original BS/SU implementations.
"""

import argparse
from dataclasses import dataclass
import importlib.util
from math import ceil, log2
from pathlib import Path
import time
from typing import Optional

from pysat.formula import CNF
from pysat.pb import PBEnc
from pysat.solvers import Solver


BACKENDS = {"Cadical": "Cadical195", "Maplesat": "Maplesat"}


@dataclass
class SearchResult:
    status: str
    peak: Optional[int] = None
    stations: Optional[list] = None
    starts: Optional[list] = None
    calls: int = 0
    variables: int = 0
    clauses: int = 0
    transformation_time: float = 0.0
    solve_time: float = 0.0


def load_encoding(backend, formulation):
    """Load a fresh original module, isolating its IDPool and reduction state."""
    path = Path(__file__).resolve().parents[1] / f"{backend}-BS-{formulation}.py"
    spec = importlib.util.spec_from_file_location("salb3pm_encoding", path)
    encoding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(encoding)
    return encoding


def validate_instance(n, m, c, durations, powers, precedences):
    """Reject malformed data and identify elementary infeasibility."""
    if min(n, m, c) <= 0:
        raise ValueError("Task count, workstation count and cycle time must be positive")
    if any(t <= 0 for t in durations[1:]) or any(w < 0 for w in powers[1:]):
        raise ValueError("Processing times must be positive and powers nonnegative")
    successors = [[] for _ in range(n + 1)]
    degree = [0] * (n + 1)
    for i, j in precedences:
        if not (1 <= i <= n and 1 <= j <= n):
            raise ValueError("Precedence task indices must be between 1 and n")
        successors[i].append(j)
        degree[j] += 1
    ready = [i for i in range(1, n + 1) if degree[i] == 0]
    visited = 0
    while ready:
        visited += 1
        for j in successors[ready.pop()]:
            degree[j] -= 1
            if degree[j] == 0:
                ready.append(j)
    return (visited == n and max(durations[1:]) <= c
            and sum(durations[1:]) <= m * c)


def decode_schedule(encoding, model, instance):
    """Check assignments, timing, non-overlap and precedence; compute real peak."""
    n, m, c, durations, powers, precedences = instance
    positives = {lit for lit in model if lit > 0}
    stations, starts = [0], [0]
    occupied = set()
    load = [0] * c
    for j in range(1, n + 1):
        xs = [k for k in range(1, m + 1) if encoding.X(j, k) in positives]
        ss = [t for t in range(c - durations[j] + 1)
              if encoding.S(j, t) in positives]
        if len(xs) != 1 or len(ss) != 1:
            raise RuntimeError("SAT model must assign one station and start per task")
        stations.append(xs[0])
        starts.append(ss[0])
        for t in range(ss[0], ss[0] + durations[j]):
            if (xs[0], t) in occupied:
                raise RuntimeError("SAT model contains overlapping tasks")
            occupied.add((xs[0], t))
            load[t] += powers[j]
    for i, j in precedences:
        if stations[i] > stations[j] or (
                stations[i] == stations[j] and starts[i] + durations[i] > starts[j]):
            raise RuntimeError("SAT model violates task precedence")
    return max(load), stations, starts


class ObjectiveBounds:
    def __init__(self, encoding, formulation, upper):
        self.encoding = encoding
        self.formulation = formulation
        self.upper = upper
        # Match the original enhanced formulation's E[0..nb_E] bit range.
        self.bits = ([encoding.E(i) for i in range(ceil(log2(upper + 1)) + 1)]
                     if formulation == "E" else [])

    def clauses(self, bound):
        if bound < 0:
            return [[]]
        if self.formulation == "I":
            # E is a monotone unary sequence: not E[k+1] means peak <= k.
            return [[-self.encoding.E(bound + 1)]] if bound < self.upper else []
        return PBEnc.leq(lits=self.bits, weights=[2 ** i for i in range(len(self.bits))],
                         bound=bound, vpool=self.encoding.vpool,
                         encoding=self.encoding.PB_encoding).clauses

    def apply(self, sat, bound, temporary):
        clauses = self.clauses(bound)
        if not temporary:
            sat.append_formula(clauses)
            return [], len(clauses)
        if self.formulation == "I" and bound >= 0:
            return [clause[0] for clause in clauses], 0
        # Every binary bound gets its own selector. Earlier, possibly UNSAT,
        # bounds remain disabled unless explicitly assumed in this solve call.
        selector = self.encoding.vpool.id()
        sat.append_formula([[-selector] + clause for clause in clauses])
        return [selector], len(clauses)


def solve(input_file, method, backend="Cadical", formulation="E",
          precedence_constraint=True, long_task_constraint=True, on_improvement=None):
    """Optimize one instance with one solver; return a checked best schedule.

    Multiple SAT moves a temporary bound in either direction using assumptions.
    Incremental SAT only tightens a permanent bound to incumbent_peak - 1.
    A first feasible model is required before any OPTIMAL result is reported.
    """
    if method not in {"multiple", "incremental"}:
        raise ValueError("Method must be multiple or incremental")
    if backend not in BACKENDS or formulation not in {"I", "E"}:
        raise ValueError("Unknown SAT backend or objective formulation")
    started = time.perf_counter()
    encoding = load_encoding(backend, formulation)
    instance = encoding.parse_3pm_file(input_file)
    n, m, c, durations, powers, precedences = instance
    result = SearchResult(status="INFEASIBLE")
    cnf = CNF()
    feasible = validate_instance(*instance)
    if feasible:
        if precedence_constraint:
            try:
                cnf.extend(encoding.get_precedence_constraints(*instance))
            except AssertionError:
                # Original reduction asserts when a task requires a station
                # outside 1..m, which proves that the instance is infeasible.
                feasible = False
        if long_task_constraint and feasible:
            cnf.extend(encoding.get_longTask_constraints(*instance))
    if not feasible:
        result.transformation_time = time.perf_counter() - started
        return result
    upper = sum(sorted(powers[1:], reverse=True)[:m])
    lower = max(max(powers[1:]), (sum(durations[j] * powers[j]
                 for j in range(1, n + 1)) + c - 1) // c)
    cnf.extend(encoding.get_cnf_insatance(*instance, encoding.vpool, upper))
    bounds = ObjectiveBounds(encoding, formulation, upper)
    result.variables = encoding.vpool.top
    result.clauses = len(cnf.clauses)
    result.transformation_time = time.perf_counter() - started
    solving = time.perf_counter()

    def accept(model):
        peak, stations, starts = decode_schedule(encoding, model, instance)
        if result.peak is not None and peak >= result.peak:
            raise RuntimeError("A tightened objective bound did not improve the peak")
        result.peak, result.stations, result.starts = peak, stations, starts
        if on_improvement is not None:
            on_improvement(peak, time.perf_counter() - solving)

    with Solver(name=BACKENDS[backend], bootstrap_with=cnf.clauses) as sat:
        result.calls += 1
        if sat.solve():
            accept(sat.get_model())
            while lower < result.peak:
                target = ((lower + result.peak) // 2 if method == "multiple"
                          else result.peak - 1)
                assumptions, added = bounds.apply(sat, target, temporary=method == "multiple")
                result.clauses += added
                result.calls += 1
                if sat.solve(assumptions=assumptions):
                    accept(sat.get_model())
                    if result.peak > target:
                        raise RuntimeError("SAT model exceeds the requested power bound")
                elif method == "multiple":
                    lower = target + 1
                else:
                    break
            result.status = "OPTIMAL"
    result.variables = encoding.vpool.top
    result.solve_time = time.perf_counter() - solving
    return result


def main(method, backend, formulation):
    parser = argparse.ArgumentParser(
        description=f"Solving SALB3PM with {backend} {method.title()} SAT ({formulation}).")
    parser.add_argument("input_file", help="Path to the .3pm document")
    for flag, description in (("precedence_constraint", "precedence reduction"),
                              ("long_task_constraint", "long-task reduction")):
        parser.add_argument(f"--{flag}", action="store_true", default=True,
                            help=f"Enable {description} (default)")
        parser.add_argument(f"--no-{flag}", action="store_false", dest=flag,
                            help=f"Disable {description}")
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        result = solve(args.input_file, method, backend, formulation,
                       args.precedence_constraint, args.long_task_constraint,
                       on_improvement=lambda peak, elapsed: print(
                           f"new W : {peak} | {elapsed:.4f}", flush=True))
    except (OSError, ValueError, IndexError) as error:
        parser.error(str(error))
    print(f"$$$ Transformation time: {result.transformation_time}")
    print(f"@@@ nb_var {result.variables} nb_cons {result.clauses}")
    print(f"c method {method} solver {backend} formulation {formulation} SAT_calls {result.calls}")
    print(f"@@@ {result.status}")
    objective = f"OPT {result.peak}" if result.peak is not None else "INFEASIBLE"
    print(f"### Benchmark {Path(args.input_file).name} {objective} "
          f"TotTime {time.perf_counter() - started} RealTime {result.solve_time} "
          f"Status {result.status}")
