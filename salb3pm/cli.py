"""One CLI for solving, benchmarking, inspecting encodings, and binary export."""

import argparse
import csv
import glob
import json
from pathlib import Path

from .cnf import encode
from .model import load_instance
from .solvers import solve, METHODS, OBJECTIVES
from .results import progress_output


def add_problem_options(parser):
    parser.add_argument(
        "--encoding", choices=("staircase", "pairwise"), default="staircase"
    )
    parser.add_argument("--objective", choices=OBJECTIVES, default="peak")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="SALB3PM: binary objectives, CaDiCaL SAT oracle"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("solve")
    one.add_argument("instance")
    one.add_argument("--method", choices=METHODS, default="incremental_sat")
    one.add_argument("--time-limit", type=float, default=60)
    one.add_argument("--json-out")
    one.add_argument("--progress-out", help=argparse.SUPPRESS)
    add_problem_options(one)
    many = commands.add_parser("benchmark")
    many.add_argument("instances", nargs="+")
    many.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    many.add_argument(
        "--encodings",
        nargs="+",
        choices=("staircase", "pairwise"),
        default=["staircase", "pairwise"],
    )
    many.add_argument("--objective", choices=OBJECTIVES, default="peak")
    many.add_argument("--time-limit", type=float, default=30)
    many.add_argument("--out", default="results.csv")
    stats = commands.add_parser("encoding-stats")
    stats.add_argument("instance")
    export = commands.add_parser("export")
    export.add_argument("instance")
    export.add_argument("output", help=".wcnf or .opb")
    export.add_argument("--formulation", choices=("shared", "paper"), default="shared")
    add_problem_options(export)
    args = parser.parse_args(argv)
    if hasattr(args, "time_limit") and args.time_limit <= 0:
        parser.error("--time-limit must be positive")
    if args.command == "solve":
        with progress_output(args.progress_out):
            result = solve(
                load_instance(args.instance),
                method=args.method,
                encoding=args.encoding,
                objective=args.objective,
                time_limit=args.time_limit,
            )
        text = json.dumps(result.as_dict(), ensure_ascii=False, indent=2)
        print(text)
        if args.json_out:
            out = Path(args.json_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf8")
        return 0 if result.status in ("OPTIMAL", "INFEASIBLE") else 1
    if args.command == "export":
        from .export import export_instance

        print(
            json.dumps(
                export_instance(
                    load_instance(args.instance),
                    args.output,
                    formulation=args.formulation,
                    encoding=args.encoding,
                    objective=args.objective,
                ),
                indent=2,
            )
        )
        return 0
    if args.command == "encoding-stats":
        instance = load_instance(args.instance)
        for encoding in ("pairwise", "staircase"):
            formula = encode(instance, encoding).formula
            print(
                f"{encoding}: variables={formula.pool.top} clauses={len(formula.clauses)}"
            )
        return 0
    rows = []
    for pattern in args.instances:
        for filename in sorted(glob.glob(pattern) or [pattern]):
            instance = load_instance(filename)
            for method in args.methods:
                for encoding in (
                    ["native"]
                    if method in ("gurobi", "cplex", "cpsat")
                    else args.encodings
                ):
                    result = solve(
                        instance,
                        method=method,
                        encoding="staircase" if encoding == "native" else encoding,
                        objective=args.objective,
                        time_limit=args.time_limit,
                    )
                    metrics = result.metrics or {}
                    rows.append(
                        {
                            "instance": instance.name,
                            "method": method,
                            "encoding": encoding,
                            "objective": args.objective,
                            "status": result.status,
                            "peak": metrics.get("power_peak"),
                            "total_energy": metrics.get("total_energy"),
                            "station_peak_sum": metrics.get("station_peak_sum"),
                            "time_s": result.elapsed_s,
                            "iterations": result.iterations,
                            "solver_instances": result.solver_instances,
                            "cnf_vars": result.cnf_vars,
                            "cnf_clauses": result.cnf_clauses,
                            "backend": result.backend,
                            "proof": result.proof,
                            "message": result.message,
                        }
                    )
                    print(
                        instance.name,
                        method,
                        encoding,
                        result.status,
                        metrics.get("power_peak"),
                        flush=True,
                    )
    if rows:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return 0
