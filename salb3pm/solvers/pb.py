"""Native weighted OPB objective solved by external RoundingSAT."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from ..cnf import encode, station_peak_bank
from ..results import SolveResult, _finish, _record, publish
from ..processes import run_command


@dataclass
class PBProblem:
    encoded: object
    costs: dict
    inequalities: list

    @property
    def constraints(self):
        return len(self.encoded.formula.clauses) + len(self.inequalities)

    def rows(self):
        for clause in self.encoded.formula.clauses:
            yield {abs(lit): 1 if lit > 0 else -1 for lit in clause}, 1 - sum(
                lit < 0 for lit in clause
            )
        yield from self.inequalities

    def write(self, path):
        with Path(path).open("w", encoding="utf8") as fp:
            fp.write(
                f"* #variable= {self.encoded.formula.pool.top} #constraint= {self.constraints}\n"
            )
            fp.write(
                "min: " + " ".join(f"+{w} x{v}" for v, w in self.costs.items()) + ";\n"
            )
            for row, rhs in self.rows():
                fp.write(
                    " ".join(f"{w:+d} x{v}" for v, w in row.items()) + f" >= {rhs};\n"
                )


def build_pb(instance, encoding="staircase", objective="peak"):
    base = encode(instance, encoding)
    if objective == "total_energy":
        fixed = base.formula.pool.new("fixed_energy")
        base.formula.add(fixed)
        return PBProblem(base, {fixed: instance.total_energy}, [])
    station_bank = station_peak_bank(base) if objective == "station_peak_sum" else None
    upper = sum(station_bank[1]) if station_bank else instance.peak_upper_bound
    costs = {
        base.formula.pool.new("pb_objective_bit", i): 1 << i
        for i in range(upper.bit_length())
    }
    loads = (
        [station_bank]
        if station_bank
        else (
            ([base.activities[i, t] for i in range(instance.n)], instance.powers)
            for t in range(instance.cycle)
        )
    )
    inequalities = []
    for literals, weights in loads:
        row = dict(costs)
        for lit, weight in zip(literals, weights):
            row[lit] = row.get(lit, 0) - weight
        inequalities.append((row, 0))
    inequalities.extend(
        [
            (dict(costs), instance.peak_lower_bound),
            ({v: -w for v, w in costs.items()}, -upper),
        ]
    )
    return PBProblem(base, costs, inequalities)


def parse_output(text):
    status, cost, model = "UNKNOWN", None, {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("s "):
            label = line[2:].strip().upper()
            status = {
                "OPTIMUM FOUND": "OPTIMAL",
                "UNSATISFIABLE": "INFEASIBLE",
                "SATISFIABLE": "TIMEOUT",
                "UNKNOWN": "TIMEOUT",
            }.get(label, "UNKNOWN")
        elif line.startswith("o "):
            try:
                cost = int(line[2:].strip())
            except ValueError:
                continue
        elif line.startswith("v "):
            for token in line[2:].split():
                if token in ("0", ""):
                    continue
                if not re.fullmatch(r"-?x?[1-9][0-9]*", token):
                    raise ValueError(f"Unsupported PB model literal: {token}")
                variable = int(token.lstrip("-").lstrip("x"))
                model[variable] = not token.startswith("-")
    return status, cost, [v if value else -v for v, value in sorted(model.items())]


def resolve_binary():
    requested = os.environ.get("ROUNDINGSAT_BIN")
    if requested:
        return shutil.which(requested) or (
            str(Path(requested).resolve()) if Path(requested).is_file() else None
        )
    installed = (
        Path(__file__).resolve().parents[2]
        / "tools/roundingsat"
        / ("roundingsat.exe" if os.name == "nt" else "roundingsat")
    )
    return shutil.which("roundingsat") or (
        str(installed) if installed.is_file() else None
    )


def solve_pb(instance, *, encoding="staircase", objective="peak", time_limit=60.0):
    started = time.monotonic()
    result = SolveResult(
        "pb", encoding, objective, "UNKNOWN", 0, backend="RoundingSAT:PB"
    )
    binary = resolve_binary()
    if not binary:
        result.status = "UNAVAILABLE"
        result.message = "Set ROUNDINGSAT_BIN to a RoundingSAT executable, or put roundingsat on PATH"
        return _finish(result, started)
    problem = build_pb(instance, encoding, objective)
    result.model_variables = problem.encoded.formula.pool.top
    result.model_constraints = problem.constraints
    publish(result)
    with tempfile.TemporaryDirectory(prefix="salb3pm-pb-") as directory:
        path = Path(directory) / "instance.opb"
        problem.write(path)
        remaining = time_limit - (time.monotonic() - started)
        if remaining <= 0:
            result.status = "TIMEOUT"
            return _finish(result, started)
        result.solver_instances = 1
        # Use an explicit known command, never a shell-built solver command.
        command = [
            binary,
            "--print-sol=1",
            "--verbosity=0",
            f"--time-limit={remaining}",
            str(path),
        ]
        try:
            completed = run_command(command, timeout=remaining)
            text = completed.stdout
        except subprocess.TimeoutExpired as exc:
            text = exc.stdout or ""
            if isinstance(text, bytes):
                text = text.decode("utf8", errors="replace")
            completed = None
        except OSError as exc:
            result.status = "UNAVAILABLE"
            result.message = f"Cannot execute RoundingSAT: {exc}"
            return _finish(result, started)
        try:
            result.status, cost, model = parse_output(text)
            if completed is None:
                result.status = "TIMEOUT"
            result.iterations = 1
            if model:
                if {abs(x) for x in model} != set(range(1, result.model_variables + 1)):
                    raise ValueError(
                        "RoundingSAT did not return a complete input-variable assignment"
                    )
                positive = {x for x in model if x > 0}
                if not all(
                    sum(
                        weight
                        for variable, weight in row.items()
                        if variable in positive
                    )
                    >= rhs
                    for row, rhs in problem.rows()
                ):
                    raise ValueError(
                        "Returned PB assignment violates an input constraint"
                    )
                _record(result, instance, problem.encoded.decode(model))
                if result.status == "OPTIMAL":
                    metric = (
                        "station_peak_sum"
                        if objective == "station_peak_sum"
                        else (
                            "total_energy"
                            if objective == "total_energy"
                            else "power_peak"
                        )
                    )
                    encoded_cost = sum(
                        w for v, w in problem.costs.items() if v in positive
                    )
                    if encoded_cost != cost or cost != result.metrics[metric]:
                        raise ValueError(
                            "PB objective and independently validated schedule cost disagree"
                        )
            if result.status == "OPTIMAL":
                if not model:
                    raise ValueError("PB optimum has no model to validate")
                result.proof = (
                    "RoundingSAT optimum status with independently validated assignment"
                )
            elif result.status == "INFEASIBLE":
                result.proof = "RoundingSAT infeasibility status"
            elif result.status == "UNKNOWN":
                result.message = ((completed.stderr if completed else "") or text)[
                    -1000:
                ]
        except ValueError as exc:
            result.status = "ERROR"
            result.message = str(exc)
    return _finish(result, started)
