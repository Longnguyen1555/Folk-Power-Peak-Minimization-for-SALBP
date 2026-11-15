"""Native engines must match independent exhaustive schedules, including infeasibility."""

import subprocess
import sys
from itertools import product
from pathlib import Path

import pytest

from salb3pm.model import Instance, Schedule, validate
from salb3pm.processes import run_command
from salb3pm.solvers import solve
from salb3pm.solvers.pb import parse_output, resolve_binary
from scripts import experiment_matrix as matrix


def optimum(instance, objective):
    values = []
    choices = [
        list(product(range(instance.stations), range(instance.cycle - d + 1)))
        for d in instance.durations
    ]
    for assignment in product(*choices):
        schedule = Schedule(
            tuple(k for k, _ in assignment), tuple(t for _, t in assignment)
        )
        try:
            values.append(validate(instance, schedule)[objective])
        except ValueError:
            pass
    return min(values) if values else None


@pytest.mark.parametrize("method", ["cplex", "gurobi", "pb"])
def test_native_engines_against_exhaustive_schedules(method):
    if method == "pb" and not resolve_binary():
        pytest.skip("RoundingSAT not installed")
    for instance in (
        Instance((2, 1, 2), (2, 5, 3), 2, 3, ((0, 1),)),
        Instance((2, 2), (3, 4), 1, 3),
    ):
        for objective, metric in (
            ("peak", "power_peak"),
            ("station_peak_sum", "station_peak_sum"),
            ("total_energy", "total_energy"),
        ):
            expected = optimum(instance, metric)
            for encoding in (
                ("pairwise", "staircase") if method == "pb" else ("staircase",)
            ):
                result = solve(
                    instance,
                    method=method,
                    encoding=encoding,
                    objective=objective,
                    time_limit=5,
                )
                if result.status == "UNAVAILABLE":
                    pytest.skip(result.message)
                assert result.status == (
                    "OPTIMAL" if expected is not None else "INFEASIBLE"
                ), result.as_dict()
                assert result.model_variables > 0 and result.model_constraints > 0
                if expected is not None:
                    assert result.metrics[metric] == expected


def test_pb_status_and_model_parser():
    assert parse_output("o 5\ns OPTIMUM FOUND\nv x1 -x2 0\n") == ("OPTIMAL", 5, [1, -2])
    assert parse_output("s UNSATISFIABLE")[0] == "INFEASIBLE"
    assert parse_output("s SATISFIABLE")[0] == "TIMEOUT"
    with pytest.raises(ValueError):
        parse_output("v unsupported")


def test_full_matrix_plan(capsys):
    root = Path(__file__).resolve().parents[1]
    matrix.main(["--config", str(root / "configs/matrix_all_1993.json"), "--dry-run"])
    assert "1950 runs; limit=30s" in capsys.readouterr().out


def test_process_timeout_captures_partial_output():
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        run_command(
            [
                sys.executable,
                "-c",
                "import time; print('started', flush=True); time.sleep(30)",
            ],
            timeout=1,
        )
    assert "started" in caught.value.stdout
