"""Inventory a supplied ICTAI-2024 dataset before running the SAT matrix.

Count + Table-II parameter checks do not authenticate the original random power
weights. Keep the source URL/archive and hashes with the experiment results.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from salb3pm.model import load_instance

# ICTAI 2024, Table II: (number of tasks, stations, cycle time).
PAPER_ANCHORS = {
    "ROSZIEG-5": (25, 6, 25),
    "HESKIA-2": (28, 5, 205),
    "HESKIA-1": (28, 8, 138),
    "BUXEY-5": (29, 8, 41),
    "BUXEY-3": (29, 11, 33),
    "SAWYER30-6": (30, 8, 41),
    "SAWYER30-3": (30, 12, 30),
    "GUNTHER-5": (35, 9, 61),
    "WARNECKE-6": (58, 25, 65),
}


def inventory(directory, source=""):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"Dataset directory does not exist: {directory}")
    paths = sorted(directory.rglob("*.3pm"))
    if len(paths) != 97:
        raise ValueError(
            f"Expected exactly 97 .3pm instances, found {len(paths)}; do not truncate the 130-instance dataset"
        )
    records, parameters = [], {}
    for path in paths:
        if path.stem in parameters:
            raise ValueError(f"Duplicate instance name: {path.stem}")
        instance = load_instance(path)
        parameters[path.stem] = (instance.n, instance.stations, instance.cycle)
        records.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "n": instance.n,
                "m": instance.stations,
                "c": instance.cycle,
            }
        )
    for name, expected in PAPER_ANCHORS.items():
        actual = parameters.get(name)
        if actual != expected:
            raise ValueError(
                f"Table-II mismatch for {name}: expected (n,m,c)={expected}, found {actual}"
            )
    return {
        "dataset": "ICTAI-2024 supplied 97-instance set",
        "source": source,
        "validation": "97 unique files and nine Table-II parameter checks; original powers require source provenance",
        "instances": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--source", default="", help="Original download URL/archive identifier"
    )
    args = parser.parse_args(argv)
    try:
        manifest = inventory(args.directory, args.source)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if output.exists() and output.read_text(encoding="utf8") != text:
        parser.error(f"Existing manifest differs: {output}; choose a new output path")
    output.write_text(text, encoding="utf8")
    print(f"Checked 97 instances and nine published parameter anchors: {output}")


if __name__ == "__main__":
    main()
