#!/usr/bin/env python3
"""Isolated process benchmark with a hard wall-clock cutoff per run.

Unlike running RC2 in-process, subprocess timeout can stop any backend.
Every status and metric comes from the JSON-returning validated solver.
"""
import argparse
import csv
import glob
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def execute(path,method,encoding,objective,cutoff):
    cmd=[sys.executable,"-m","salb3pm","solve",str(path),"--method",method,
         "--encoding",encoding,"--objective",objective,"--time-limit",str(cutoff)]
    started=time.monotonic()
    try:
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=cutoff+3)
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","message":"Hard subprocess cutoff", "wall_time_s":round(time.monotonic()-started,6)}
    wall=round(time.monotonic()-started,6)
    try:
        data=json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status":"ERROR","message":(result.stderr or result.stdout)[-500:],"wall_time_s":wall}
    metrics=data.get("metrics") or {}
    return {"status":data.get("status","UNKNOWN"),"wall_time_s":wall,
            "solve_time_s":data.get("elapsed_s"), "peak":metrics.get("power_peak"),
            "total_energy":metrics.get("total_energy"),
            "station_peak_sum":metrics.get("station_peak_sum"),
            "variables":data.get("cnf_vars"), "clauses":data.get("cnf_clauses"),
            "iterations":data.get("iterations"),"solver_instances":data.get("solver_instances"),
            "backend":data.get("backend"),"proof":data.get("proof"),"message":data.get("message")}


def main():
    ap=argparse.ArgumentParser(description="Reproducible per-process exact SALB3PM benchmark")
    ap.add_argument("instances",nargs="+",help="Paths or quoted globs, e.g. 'benchmarks/1993/MERTENS-*.3pm'")
    ap.add_argument("--methods",nargs="+",default=["multiple_sat","incremental_sat","binary_sat","paper_cuts","maxsat","gurobi","cpsat"])
    ap.add_argument("--encodings",nargs="+",default=["pairwise","staircase"])
    ap.add_argument("--objective",default="peak")
    ap.add_argument("--time-limit",type=float,default=30.0)
    ap.add_argument("--repeat",type=int,default=1)
    ap.add_argument("--out",default="experiments/results.csv")
    args=ap.parse_args()
    if args.time_limit<=0 or args.repeat<=0: ap.error("--time-limit and --repeat must be positive")
    paths=sorted(set(x for g in args.instances for x in (glob.glob(g) or [g])))
    rows=[]
    for path in paths:
        for method in args.methods:
            for enc in (["native"] if method in ("gurobi","cpsat") else args.encodings):
                for rep in range(args.repeat):
                    used_enc = "staircase" if enc == "native" else enc
                    print(Path(path).name,method,enc,rep+1,flush=True)
                    values=execute(path,method,used_enc,args.objective,args.time_limit)
                    rows.append({"instance":Path(path).name,"method":method,"encoding":enc,
                                 "objective":args.objective,"repeat":rep+1,**values})
    if rows:
        out=Path(args.out)
        out.parent.mkdir(parents=True,exist_ok=True)
        with out.open("w",encoding="utf8",newline="") as fp:
            writer=csv.DictWriter(fp,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
            writer.writeheader();writer.writerows(rows)
        print("Wrote",out)

if __name__=="__main__":
    main()
