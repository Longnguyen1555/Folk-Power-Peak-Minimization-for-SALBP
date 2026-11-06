"""Backward-compatible routing for the original upstream solver entry points.

The legacy no-flags path is deliberately untouched; explicit modern flags
activate the shared, validated new encoder. This is a new solver formulation,
not a claim that the legacy E/I internal encoding has been changed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .model import load_instance
from .solvers import solve, METHODS, OBJECTIVES


def enhanced_requested(argv, *, extension=None):
    explicit = ("--encoding", "--objective", "--modern", "--time-limit", "--solve")
    if extension and any(x.lower().endswith(extension) for x in argv if not x.startswith("-")):
        return True
    return any(a == flag or a.startswith(flag+"=") for a in argv for flag in explicit)


def execute(default_method, argv=None, default_solver="cadical195"):
    parser=argparse.ArgumentParser(description="Run the extended SALB3PM solver on upstream .3pm data")
    parser.add_argument("input_file", help="Original .3pm instance")
    parser.add_argument("--encoding",choices=("pairwise","staircase"),default="staircase")
    parser.add_argument("--objective",choices=OBJECTIVES,default="peak")
    parser.add_argument("--method",choices=METHODS,default=default_method)
    parser.add_argument("--solver",default=default_solver)
    parser.add_argument("--time-limit",type=float,default=60.0)
    parser.add_argument("--json-out",default=None)
    parser.add_argument("--modern",action="store_true")
    parser.add_argument("--solve",action="store_true",help="Run MaxSAT instead of generating a WCNF")
    parser.add_argument("--no-precedence_constraint",action="store_true",help="Legacy reduction toggle; modern encoding does not use it")
    parser.add_argument("--no-long_task_constraint",action="store_true",help="Legacy reduction toggle; modern encoding does not use it")
    args=parser.parse_args(argv)
    instance=load_instance(args.input_file)
    result=solve(instance,method=args.method,encoding=args.encoding,objective=args.objective,
                 time_limit=args.time_limit,solver_name=args.solver)
    result_info=result.as_dict()
    data=json.dumps(result_info,ensure_ascii=False,indent=2)
    print(data)
    if args.json_out:
        Path(args.json_out).write_text(data+"\n",encoding="utf-8")
    met=result.metrics or {}
    print(f"### Benchmark {Path(args.input_file).name} OPT {met.get('power_peak')} "
          f"TotalPower {met.get('total_energy')} StationPeakSum {met.get('station_peak_sum')} "
          f"Status {result.status} Time {result.elapsed_s} Encoding {args.encoding} "
          f"Method {args.method} Objective {args.objective}")
    return 0 if result.status in ("OPTIMAL","INFEASIBLE") else 1
