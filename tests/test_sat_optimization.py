"""Objective projection and solver lifecycle checks for repeated optimization."""

from itertools import product
from pathlib import Path
from types import SimpleNamespace

import pytest

from salb3pm.cnf import BinaryObjectiveBound, binary_objective_bank, encode
from salb3pm.model import Instance, Schedule, load_instance, validate
import salb3pm.solvers.sat as workflows
import salb3pm.backends as backends


def test_binary_comparator_exhaustive():
    for upper in range(1, 25):
        bits = list(range(1, upper.bit_length() + 1))
        bank = BinaryObjectiveBound(bits, 0, (1 << len(bits)) - 1)
        for bound in range(-1, bank.upper + 2):
            clauses = bank.atmost(bound)
            for value in range(bank.upper + 1):
                satisfied = all(
                    any(
                        bool(value & (1 << (abs(lit) - 1))) == (lit > 0)
                        for lit in clause
                    )
                    for clause in clauses
                )
                assert satisfied == (value <= bound), (value, bound, clauses)


@pytest.mark.parametrize("encoding", ["pairwise", "staircase"])
def test_reusable_peak_bank_projected_schedules(encoding):
    pytest.importorskip("pysat.pb")
    from pysat.solvers import Solver

    ins = Instance((1, 2), (3, 5), 2, 3, ((0, 1),))
    base = encode(ins, encoding)
    bank = binary_objective_bank(base)
    for bound in range(0, 10):
        with Solver(
            name="cadical195", bootstrap_with=base.formula.clauses + bank.atmost(bound)
        ) as sat:
            for k0, k1, s0, s1 in product(range(2), range(2), range(3), range(2)):
                schedule = Schedule((k0, k1), (s0, s1))
                assumptions = []
                for (i, k), lit in base.stations.items():
                    yes = (
                        schedule.stations[i] <= k
                        if encoding == "staircase"
                        else schedule.stations[i] == k
                    )
                    assumptions.append(lit if yes else -lit)
                for (i, t), lit in base.starts.items():
                    yes = (
                        schedule.starts[i] <= t
                        if encoding == "staircase"
                        else schedule.starts[i] == t
                    )
                    assumptions.append(lit if yes else -lit)
                try:
                    expected = validate(ins, schedule)["power_peak"] <= bound
                except ValueError:
                    expected = False
                assert sat.solve(assumptions=assumptions) == expected


@pytest.mark.parametrize("method", ["multiple_sat", "incremental_sat"])
def test_rebuild_vs_permanent_bounds(monkeypatch, method):
    pytest.importorskip("pysat.pb")
    real_encode, real_backend = workflows.encode, workflows.SATBackend
    encodings, backends, additions, bounds = [], [], [], []

    def traced_encode(*args, **kwargs):
        encoded = real_encode(*args, **kwargs)
        encodings.append(encoded)
        return encoded

    class Backend(real_backend):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            backends.append(self)

        def add_clauses(self, clauses):
            additions.append(clauses)
            super().add_clauses(clauses)

    real_atmost = BinaryObjectiveBound.atmost

    def traced_atmost(self, bound):
        if self.lower:
            bounds.append(bound)
        return real_atmost(self, bound)

    monkeypatch.setattr(workflows, "encode", traced_encode)
    monkeypatch.setattr(workflows, "SATBackend", Backend)
    monkeypatch.setattr(BinaryObjectiveBound, "atmost", traced_atmost)
    ins = load_instance(
        Path(__file__).resolve().parents[1] / "examples/small_example.3pm"
    )
    result = workflows.solve_sat(ins, method=method)
    assert result.status == "OPTIMAL"
    assert result.metrics["power_peak"] == 8
    assert bounds and all(b < a for a, b in zip(bounds, bounds[1:]))
    if method == "multiple_sat":
        assert len(encodings) == len(backends) == result.iterations >= 2
        assert not additions
        assert result.cnf_peak_clauses < result.cnf_clauses
    else:
        assert len(encodings) == len(backends) == 1
        assert len(additions) == result.iterations - 1
        assert result.cnf_peak_clauses == result.cnf_clauses
        # Only binary comparator clauses are added, with no new PB variables.
        assert result.cnf_vars == encodings[0].formula.pool.top
        assert all(len(cs) <= ins.peak_upper_bound.bit_length() for cs in additions)


@pytest.mark.parametrize("method", ["multiple_sat", "incremental_sat"])
def test_timeout_preserves_valid_incumbent(monkeypatch, method):
    real_solve = workflows.SATBackend.solve
    calls = []

    def stop_after_feasible(self, deadline):
        calls.append(self)
        return real_solve(self, deadline) if len(calls) == 1 else None

    monkeypatch.setattr(workflows.SATBackend, "solve", stop_after_feasible)
    ins = load_instance(
        Path(__file__).resolve().parents[1] / "examples/paper_py_2024.3pm"
    )
    result = workflows.solve_sat(ins, method=method)
    assert result.status == "TIMEOUT"
    assert result.iterations == 2
    assert validate(ins, result.schedule) == result.metrics
    assert not result.proof


@pytest.mark.parametrize("timed_out", [False, True])
def test_cadical_budget_exhaustion_is_not_unsat(monkeypatch, timed_out):
    # No interrupt API: a budget-limited UNKNOWN must be retried on the same solver.
    budgets, calls = [], []

    def limited():
        calls.append(True)
        return None if len(calls) == 1 else True

    fake = SimpleNamespace(conf_budget=budgets.append, solve_limited=limited)
    backend = object.__new__(workflows.SATBackend)
    backend.solver = fake
    ticks = iter([0, 2] if timed_out else [0, 0])
    monkeypatch.setattr(
        backends, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )
    assert backend.solve(1) is (None if timed_out else True)
    assert len(calls) == (1 if timed_out else 2)
    assert budgets[-1] == -1
