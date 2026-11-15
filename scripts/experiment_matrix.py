#!/usr/bin/env python3
"""Isolated process benchmark with a hard wall-clock cutoff per run.

Unlike running RC2 in-process, subprocess timeout can stop any backend.
Every status and metric comes from the JSON-returning validated solver.
"""

import argparse
import csv
import glob
import hashlib
import json
import math
import subprocess
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from salb3pm.processes import run_command

METHODS = (
    "multiple_sat",
    "incremental_sat",
    "binary_sat",
    "paper_cuts",
    "maxsat",
    "gurobi",
    "cplex",
    "pb",
    "cpsat",
)
FIELDS = [
    "instance",
    "instance_file",
    "method",
    "encoding",
    "objective",
    "repeat",
    "time_limit_s",
    "status",
    "solver_status",
    "optimality_proven",
    "runtime_s",
    "wall_time_s",
    "solve_time_s",
    "peak",
    "total_energy",
    "station_peak_sum",
    "variables",
    "clauses",
    "constraints",
    "iterations",
    "solver_instances",
    "backend",
    "proof",
    "message",
]
KEY_FIELDS = (
    "instance_file",
    "method",
    "encoding",
    "objective",
    "repeat",
    "time_limit_s",
)
DEFAULT_METHODS = ["multiple_sat", "incremental_sat", "maxsat"]


def display_status(status):
    return {
        "OPTIMAL": "SAT",
        "SAT": "SAT",
        "INFEASIBLE": "UNSAT",
        "UNSAT": "UNSAT",
        "TIMEOUT": "Timeout",
        "Timeout": "Timeout",
    }.get(status, "Error")


def metrics_from_result(data, wall, status=None, message=None):
    metrics = data.get("metrics") or {}
    raw_status = status or data.get("status", "UNKNOWN")
    clauses = data.get("cnf_peak_clauses")
    return {
        "status": raw_status,
        "solver_status": raw_status,
        "optimality_proven": raw_status == "OPTIMAL",
        "runtime_s": wall,
        "wall_time_s": wall,
        "solve_time_s": data.get("elapsed_s"),
        "peak": metrics.get("power_peak"),
        "total_energy": metrics.get("total_energy"),
        "station_peak_sum": metrics.get("station_peak_sum"),
        "variables": (
            data.get("cnf_vars")
            if data.get("cnf_vars") is not None
            else data.get("model_variables")
        ),
        "clauses": clauses if clauses is not None else data.get("cnf_clauses"),
        "constraints": data.get("model_constraints"),
        "iterations": data.get("iterations"),
        "solver_instances": data.get("solver_instances"),
        "backend": data.get("backend"),
        "proof": data.get("proof"),
        "message": message if message is not None else data.get("message", ""),
    }


def row_key(row):
    return tuple(str(row[field]) for field in KEY_FIELDS)


def manifest_paths(filename):
    manifest = json.loads(Path(filename).read_text(encoding="utf8"))
    paths = []
    for record in manifest["instances"]:
        path = Path(record["path"]).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Instance changed since manifest creation: {path}")
        paths.append(str(path))
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("Manifest must contain unique, nonempty instance paths")
    return paths


def execute(path, method, encoding, objective, cutoff):
    cmd = [
        sys.executable,
        "-m",
        "salb3pm",
        "solve",
        str(path),
        "--method",
        method,
        "--encoding",
        encoding,
        "--objective",
        objective,
        "--time-limit",
        str(cutoff),
    ]
    with tempfile.TemporaryDirectory(prefix="salb3pm-") as directory:
        progress = Path(directory) / "progress.json"
        cmd.extend(["--progress-out", str(progress)])
        started = time.monotonic()
        try:
            result = run_command(cmd, cwd=ROOT, timeout=cutoff)
        except subprocess.TimeoutExpired:
            try:
                data = json.loads(progress.read_text(encoding="utf8"))
            except (OSError, ValueError):
                data = {}
            return metrics_from_result(
                data,
                round(time.monotonic() - started, 6),
                "TIMEOUT",
                "Hard subprocess cutoff; last published input-formula statistics",
            )
        wall = round(time.monotonic() - started, 6)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return metrics_from_result(
                {}, wall, "ERROR", (result.stderr or result.stdout)[-500:]
            )
        return metrics_from_result(data, wall)


def main(argv=None):
    preliminary = argparse.ArgumentParser(add_help=False)
    preliminary.add_argument("--config")
    selected, _ = preliminary.parse_known_args(argv)
    settings = {}
    if selected.config:
        try:
            settings = json.loads(Path(selected.config).read_text(encoding="utf8"))
            allowed = {
                "datasets",
                "methods",
                "encodings",
                "objective",
                "time_limit",
                "repeat",
                "out",
                "resume",
            }
            if not isinstance(settings, dict) or set(settings) - allowed:
                raise ValueError(
                    "Unknown configuration keys; use datasets/methods/encodings/objective/time_limit/repeat/out/resume"
                )
            for key in ("datasets", "methods", "encodings"):
                if key in settings and (
                    not isinstance(settings[key], list)
                    or not settings[key]
                    or any(not isinstance(item, str) for item in settings[key])
                ):
                    raise ValueError(f"{key} must be a nonempty list of strings")
        except (OSError, ValueError) as exc:
            preliminary.error(str(exc))
    ap = argparse.ArgumentParser(
        description="Reproducible per-process exact SALB3PM benchmark"
    )
    ap.add_argument(
        "--config", help="JSON matrix configuration; CLI options override its values"
    )
    ap.add_argument(
        "--datasets",
        nargs="+",
        help="Dataset directories, instance files or quoted globs",
    )
    ap.add_argument(
        "instances",
        nargs="*",
        help="Paths or quoted globs, e.g. 'benchmarks/1993/MERTENS-*.3pm'",
    )
    ap.add_argument(
        "--manifest", help="JSON instance manifest with path and SHA-256 per file"
    )
    ap.add_argument(
        "--methods",
        nargs="+",
        choices=METHODS,
        default=settings.get("methods", DEFAULT_METHODS),
    )
    ap.add_argument(
        "--encodings",
        nargs="+",
        choices=("pairwise", "staircase"),
        default=settings.get("encodings", ["pairwise", "staircase"]),
    )
    ap.add_argument("--objective", default=settings.get("objective", "peak"))
    ap.add_argument(
        "--time-limit", type=float, default=settings.get("time_limit", 30.0)
    )
    ap.add_argument("--repeat", type=int, default=settings.get("repeat", 1))
    ap.add_argument("--out", default=settings.get("out", "experiments/results.csv"))
    ap.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=settings.get("resume", False),
        help="Append missing runs without overwriting existing rows",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the matrix without launching solvers or writing results",
    )
    args = ap.parse_args(argv)
    try:
        args.time_limit = float(args.time_limit)
    except (TypeError, ValueError):
        ap.error("time_limit must be a finite positive number")
    if (
        not math.isfinite(args.time_limit)
        or args.time_limit <= 0
        or not isinstance(args.repeat, int)
        or isinstance(args.repeat, bool)
        or args.repeat <= 0
    ):
        ap.error("--time-limit and --repeat must be positive")
    if not isinstance(args.resume, bool):
        ap.error("resume must be true or false")
    if any(method not in METHODS for method in args.methods) or any(
        enc not in ("pairwise", "staircase") for enc in args.encodings
    ):
        ap.error("Invalid method or encoding in configuration")
    if args.instances and args.datasets:
        ap.error("Use positional instances OR --datasets")
    inputs = (
        args.instances
        or args.datasets
        or ([] if args.manifest else settings.get("datasets", []))
    )
    if bool(inputs) == bool(args.manifest):
        ap.error("Provide instance paths/globs OR --manifest")
    try:
        paths = (
            manifest_paths(args.manifest)
            if args.manifest
            else sorted(
                {
                    str(Path(x).resolve())
                    for g in inputs
                    for x in (
                        [str(p) for p in Path(g).rglob("*.3pm")]
                        if Path(g).is_dir()
                        else (glob.glob(g) or [g])
                    )
                }
            )
        )
        for path in paths:
            if not Path(path).is_file():
                raise ValueError(f"Instance does not exist: {path}")
        if not paths:
            raise ValueError("No .3pm instances found in the selected datasets")
    except (ValueError, KeyError, OSError) as exc:
        ap.error(str(exc))
    planned = (
        sum(
            1 if method in ("gurobi", "cplex", "cpsat") else len(args.encodings)
            for method in args.methods
        )
        * len(paths)
        * args.repeat
    )
    print(
        f"Matrix: {len(paths)} instances x {len(args.methods)} methods; {planned} runs; limit={args.time_limit:g}s",
        flush=True,
    )
    print(
        f"Methods: {', '.join(args.methods)}; encodings: {', '.join(args.encodings)}; objective: {args.objective}",
        flush=True,
    )
    if args.dry_run:
        print(f"Output: {args.out}; resume={args.resume}; no solvers launched")
        return
    out = Path(args.out)
    completed = set()
    append = args.resume and out.exists() and out.stat().st_size > 0
    if append:
        with out.open(encoding="utf8", newline="") as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames != FIELDS:
                ap.error("Existing CSV schema differs; choose a new output file")
            for row in reader:
                if (
                    None in row
                    or any(value is None for value in row.values())
                    or not row["status"]
                ):
                    ap.error(
                        "Existing CSV contains an incomplete row; repair it before resuming"
                    )
                completed.add(row_key(row))
    elif out.exists() and out.stat().st_size > 0:
        ap.error("Output exists; use --resume or a new --out path")
    print(
        f"{'Instance':25} {'Method':16} {'Encoding':10} {'Run':>3} {'Runtime(s)':>11} {'Variables':>10} {'Clauses':>10} {'Constraints':>11} {'Status':>8}",
        flush=True,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    with out.open("a" if append else "w", encoding="utf8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=FIELDS)
        if not append:
            writer.writeheader()
            fp.flush()
        for path in paths:
            for method in args.methods:
                for enc in (
                    ["native"]
                    if method in ("gurobi", "cplex", "cpsat")
                    else args.encodings
                ):
                    for rep in range(args.repeat):
                        row = {
                            "instance": Path(path).name,
                            "instance_file": path,
                            "method": method,
                            "encoding": enc,
                            "objective": args.objective,
                            "repeat": rep + 1,
                            "time_limit_s": args.time_limit,
                        }
                        key = row_key(row)
                        if key in completed:
                            skipped += 1
                            continue
                        row.update(
                            execute(
                                path,
                                method,
                                "staircase" if enc == "native" else enc,
                                args.objective,
                                args.time_limit,
                            )
                        )
                        raw_status = row.get("solver_status", row["status"])
                        row["solver_status"] = raw_status
                        row["optimality_proven"] = raw_status == "OPTIMAL"
                        row["runtime_s"] = row.get("runtime_s", row.get("wall_time_s"))
                        row["status"] = display_status(raw_status)
                        runtime = (
                            f"{row['runtime_s']:.3f}"
                            if row["runtime_s"] is not None
                            else "N/A"
                        )
                        variables = row.get("variables")
                        clauses = row.get("clauses")
                        constraints = row.get("constraints")
                        print(
                            f"{Path(path).name:25} {method:16} {enc:10} {rep+1:>3} {runtime:>11} {str(variables) if variables is not None else 'N/A':>10} {str(clauses) if clauses is not None else 'N/A':>10} {str(constraints) if constraints is not None else 'N/A':>11} {row['status']:>8}",
                            flush=True,
                        )
                        writer.writerow(row)
                        fp.flush()
                        completed.add(key)
                        written += 1
    print(f"Wrote {written} rows; skipped {skipped} existing runs: {out}")


if __name__ == "__main__":
    main()
