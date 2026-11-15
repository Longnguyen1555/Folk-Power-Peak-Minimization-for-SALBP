"""Check binary serialization and the refactored public entry points."""

import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from salb3pm.export import export_instance
from salb3pm.model import Instance, load_instance
from salb3pm.paper import build_paper_wcnf
from salb3pm.solvers.maxsat import build_wcnf

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("formulation", ["shared", "paper"])
@pytest.mark.parametrize("suffix", ["wcnf", "opb"])
def test_exported_binary_model_optimum(tmp_path, formulation, suffix):
    from pysat.formula import WCNF
    from pysat.examples.rc2 import RC2

    instance = load_instance(ROOT / "examples/paper_py_2024.3pm")
    output = tmp_path / f"model.{suffix}"
    info = export_instance(instance, output, formulation=formulation)
    assert info["objective_encoding"] == "binary"
    assert info["soft_clauses"] == instance.peak_upper_bound.bit_length()
    if suffix == "wcnf":
        formula = WCNF(from_file=str(output))
    else:
        # Read the emitted OPB independently and recover its CNF + bit costs.
        lines = output.read_text().splitlines()
        formula = WCNF()
        for weight, variable in re.findall(r"\+(\d+) x(\d+)", lines[1]):
            formula.append([-int(variable)], weight=int(weight))
        for line in lines[2:]:
            assert line.endswith(">= 1;")
            clause = [
                (-1 if neg else 1) * int(variable)
                for neg, variable in re.findall(r"\+1 (~?)x(\d+)", line)
            ]
            formula.append(clause)
    with RC2(formula, solver="cadical195") as solver:
        assert solver.compute() is not None
        assert solver.cost == 10


def test_paper_factory_has_no_cross_instance_state():
    instance = load_instance(ROOT / "examples/paper_py_2024.3pm")
    first = build_paper_wcnf(instance)
    infeasible = build_paper_wcnf(Instance((2, 2), (3, 5), 1, 2, ((0, 1),)))
    assert [] in infeasible.hard
    second = build_paper_wcnf(instance)
    assert (first.hard, first.soft, first.wght) == (
        second.hard,
        second.soft,
        second.wght,
    )


def test_shared_wcnf_soft_costs_are_binary():
    instance = load_instance(ROOT / "examples/paper_py_2024.3pm")
    _, formula = build_wcnf(instance)
    assert formula.wght == [
        1 << i for i in range(instance.peak_upper_bound.bit_length())
    ]
    assert all(len(clause) == 1 and clause[0] < 0 for clause in formula.soft)


def test_cli_rejects_backend_selection():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "salb3pm",
            "solve",
            str(ROOT / "examples/paper_py_2024.3pm"),
            "--solver",
            "glucose3",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_gurobi_stdout_is_valid_json():
    pytest.importorskip("gurobipy")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "salb3pm",
            "solve",
            str(ROOT / "examples/paper_py_2024.3pm"),
            "--method",
            "gurobi",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    data = json.loads(result.stdout)
    if data["status"] == "UNAVAILABLE":
        pytest.skip(data["message"])
    assert result.returncode == 0
    assert data["status"] == "OPTIMAL"
    assert data["encoding"] == "native"
    assert data["metrics"]["power_peak"] == 10
