"""Dataset guards and resumable planning; fixtures are synthetic, not paper data."""

import csv
import json

import pytest

from scripts import experiment_matrix, prepare_paper97


def synthetic_dataset(directory):
    directory.mkdir()
    parameters = dict(prepare_paper97.PAPER_ANCHORS)
    parameters.update({f"fixture_{i}": (2, 1, 2) for i in range(88)})
    for name, (n, m, c) in parameters.items():
        (directory / f"{name}.3pm").write_text(
            f"{n} {m} {c}\n" + "1 1\n" * n + "-1,-1\n", encoding="utf8"
        )
    return directory


def test_exact_97_matrix_and_resume(tmp_path, monkeypatch):
    directory = synthetic_dataset(tmp_path / "synthetic")
    manifest = tmp_path / "instances.json"
    manifest.write_text(
        json.dumps(prepare_paper97.inventory(directory)), encoding="utf8"
    )
    calls = []

    def execute(path, method, encoding, objective, cutoff):
        calls.append((path, method, encoding, objective, cutoff))
        return {"status": "OPTIMAL", "peak": 1, "backend": "pysat:cadical195"}

    monkeypatch.setattr(experiment_matrix, "execute", execute)
    output = tmp_path / "matrix.csv"
    args = [
        "--manifest",
        str(manifest),
        "--methods",
        "multiple_sat",
        "incremental_sat",
        "binary_sat",
        "--encodings",
        "pairwise",
        "staircase",
        "--time-limit",
        "3600",
        "--repeat",
        "1",
        "--resume",
        "--out",
        str(output),
    ]
    experiment_matrix.main(args)
    assert len(calls) == 97 * 3 * 2
    assert {x[1] for x in calls} == {"multiple_sat", "incremental_sat", "binary_sat"}
    assert {x[2] for x in calls} == {"pairwise", "staircase"}
    assert all(x[3:] == ("peak", 3600.0) for x in calls)
    experiment_matrix.main(args)
    assert len(calls) == 582
    with output.open(newline="") as fp:
        assert len(list(csv.DictReader(fp))) == 582


def test_reject_wrong_count_or_published_parameters(tmp_path):
    directory = synthetic_dataset(tmp_path / "synthetic")
    path = directory / "extra.3pm"
    path.write_text("1 1 1\n1 1\n-1,-1\n")
    with pytest.raises(ValueError, match="exactly 97"):
        prepare_paper97.inventory(directory)
    path.unlink()
    (directory / "BUXEY-5.3pm").write_text("1 1 1\n1 1\n-1,-1\n")
    with pytest.raises(ValueError, match="Table-II mismatch"):
        prepare_paper97.inventory(directory)


def test_manifest_detects_changed_input(tmp_path):
    directory = synthetic_dataset(tmp_path / "synthetic")
    data = prepare_paper97.inventory(directory)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(data), encoding="utf8")
    path = directory / "fixture_0.3pm"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="changed since manifest"):
        experiment_matrix.manifest_paths(manifest)
