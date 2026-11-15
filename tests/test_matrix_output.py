"""Config overrides, result presentation, and statistics surviving hard timeout."""

import csv
import json
from pathlib import Path
import subprocess

import pytest

from scripts import experiment_matrix as matrix


def tiny_instance(tmp_path):
    path = tmp_path / "tiny.3pm"
    path.write_text("1 1 1\n1 2\n-1,-1\n")
    return path


def test_config_and_cli_overrides_dry_run(tmp_path, monkeypatch, capsys):
    tiny_instance(tmp_path)
    output = tmp_path / "results.csv"
    config = tmp_path / "matrix.json"
    config.write_text(
        json.dumps(
            {
                "datasets": [str(tmp_path)],
                "methods": ["maxsat"],
                "encodings": ["pairwise", "staircase"],
                "time_limit": 30,
                "out": str(output),
            }
        )
    )

    def forbidden(*args):
        pytest.fail("dry run must not launch a solver")

    monkeypatch.setattr(matrix, "execute", forbidden)
    matrix.main(
        [
            "--config",
            str(config),
            "--methods",
            "multiple_sat",
            "incremental_sat",
            "--encodings",
            "staircase",
            "--time-limit",
            "5",
            "--dry-run",
        ]
    )
    text = capsys.readouterr().out
    assert "2 runs; limit=5s" in text
    assert "multiple_sat, incremental_sat" in text
    assert not output.exists()


@pytest.mark.parametrize(
    "raw,display,optimal",
    [
        ("OPTIMAL", "SAT", True),
        ("INFEASIBLE", "UNSAT", False),
        ("TIMEOUT", "Timeout", False),
        ("UNAVAILABLE", "Error", False),
    ],
)
def test_output_columns_and_status(
    tmp_path, monkeypatch, capsys, raw, display, optimal
):
    instance = tiny_instance(tmp_path)
    monkeypatch.setattr(
        matrix,
        "execute",
        lambda *args: {
            "status": raw,
            "runtime_s": 1.25,
            "variables": 12,
            "clauses": 34,
        },
    )
    output = tmp_path / "output.csv"
    matrix.main(
        [
            str(instance),
            "--methods",
            "maxsat",
            "--encodings",
            "staircase",
            "--out",
            str(output),
        ]
    )
    text = capsys.readouterr().out
    assert all(
        label in text
        for label in ["Runtime(s)", "Variables", "Clauses", "Status", display]
    )
    with output.open(newline="") as fp:
        row = next(csv.DictReader(fp))
    assert row["status"] == display
    assert row["solver_status"] == raw
    assert row["optimality_proven"] == str(optimal)
    assert (row["runtime_s"], row["variables"], row["clauses"]) == ("1.25", "12", "34")


def test_hard_timeout_preserves_last_counts(monkeypatch):
    def killed(cmd, **kwargs):
        assert kwargs["timeout"] == 30
        progress = Path(cmd[cmd.index("--progress-out") + 1])
        progress.write_text(
            json.dumps(
                {
                    "status": "UNKNOWN",
                    "cnf_vars": 123,
                    "cnf_clauses": 999,
                    "cnf_peak_clauses": 456,
                    "metrics": {"power_peak": 10},
                }
            )
        )
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(matrix, "run_command", killed)
    result = matrix.execute("unused.3pm", "maxsat", "staircase", "peak", 30)
    assert result["status"] == "TIMEOUT"
    assert not result["optimality_proven"]
    assert (result["variables"], result["clauses"], result["peak"]) == (123, 456, 10)


def test_timeout_before_encoding_has_unknown_counts(monkeypatch):
    def killed(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(matrix, "run_command", killed)
    result = matrix.execute("unused.3pm", "maxsat", "staircase", "peak", 30)
    assert result["variables"] is None and result["clauses"] is None
    assert result["status"] == "TIMEOUT"
