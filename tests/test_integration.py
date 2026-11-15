"""Regression checks for shared encodings, public entry points and preserved data."""

from pathlib import Path
import json
import subprocess
import sys
from itertools import product
import random

from salb3pm.cnf import encode
from salb3pm.model import Instance, Schedule, load_instance, validate
from salb3pm.solvers import solve

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def brute(inst):
    choices = [
        list(product(range(inst.stations), range(inst.cycle - inst.durations[i] + 1)))
        for i in range(inst.n)
    ]
    vals = []
    for assignment in product(*choices):
        sch = Schedule(tuple(k for k, s in assignment), tuple(s for k, s in assignment))
        try:
            vals.append(validate(inst, sch)["power_peak"])
        except ValueError:
            continue
    return min(vals) if vals else None


def test_binary_and_incremental_match_bruteforce_on_random_dags():
    for seed in range(12):
        rng = random.Random(seed + 500)
        n = 3
        durations = tuple(rng.randint(1, 3) for _ in range(n))
        powers = tuple(rng.randint(1, 6) for _ in range(n))
        arcs = tuple(
            (i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.35
        )
        inst = Instance(durations, powers, 2, 4, arcs)
        target = brute(inst)
        for encoding in ("pairwise", "staircase"):
            for method in ("binary_sat", "multiple_sat", "incremental_sat", "maxsat"):
                outcome = solve(inst, method=method, encoding=encoding, time_limit=4)
                assert "cadical195" in outcome.backend
                if target is None:
                    assert outcome.status == "INFEASIBLE", outcome.as_dict()
                else:
                    assert outcome.status == "OPTIMAL", outcome.as_dict()
                    assert outcome.metrics["power_peak"] == target
                if outcome.iterations:
                    if method == "incremental_sat":
                        assert outcome.solver_instances == 1
                    else:
                        assert outcome.solver_instances == outcome.iterations


def test_original_small_example_and_objective_aliases():
    ins = load_instance(EXAMPLES / "small_example.3pm")
    assert ins.total_energy == 3 * 4 + 2 * 5 + 4 * 3 + 3 * 6 + 2 * 4
    for enc in ("pairwise", "staircase"):
        for obj in ("peak", "total_power", "peak_then_total_power"):
            r = solve(
                ins, method="incremental_sat", encoding=enc, objective=obj, time_limit=5
            )
            assert r.status == "OPTIMAL", r.as_dict()
            assert r.metrics["total_energy"] == 60
            if obj != "total_power":
                assert r.metrics["power_peak"] == 8


def test_thin_entrypoints_use_shared_cli():
    inst = EXAMPLES / "paper_py_2024.3pm"
    for name, expected_method in (
        ("MultipleSAT.py", "multiple_sat"),
        ("IncrementalSAT.py", "incremental_sat"),
        ("BinarySAT.py", "binary_sat"),
        ("StaircasePaperCuts.py", "paper_cuts"),
    ):
        output = subprocess.run(
            [
                sys.executable,
                str(ROOT / "solvers/SAT_based" / name),
                str(inst),
                "--encoding",
                "staircase",
                "--time-limit",
                "5",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert output.returncode == 0, output.stderr
        result = json.loads(output.stdout)
        assert result["method"] == expected_method
        assert result["backend"] == "pysat:cadical195"
        assert result["status"] == "OPTIMAL"
        assert result["metrics"]["power_peak"] == 10
        assert result["metrics"]["total_energy"] == 46


def test_benchmark_data_preserved():
    assert len(list((ROOT / "benchmarks/1993").glob("*.3pm"))) >= 100
    assert len(list((ROOT / "benchmarks/2013").glob("*.3pm"))) >= 20
