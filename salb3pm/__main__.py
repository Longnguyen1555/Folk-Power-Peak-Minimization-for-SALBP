"""python -m salb3pm solve|benchmark|encoding-stats ..."""
from __future__ import annotations
import argparse
import json
import csv
from pathlib import Path
from .model import load_instance
from .solvers import solve, METHODS, OBJECTIVES
from .cnf import encode


def main(argv=None):
    ap=argparse.ArgumentParser(description="SALB3PM exact SAT and Gurobi solvers")
    sub=ap.add_subparsers(dest="command",required=True)
    one=sub.add_parser("solve",help="Solve one instance")
    one.add_argument("instance")
    one.add_argument("--method",choices=METHODS,default="incremental_sat")
    one.add_argument("--encoding",choices=["staircase","pairwise"],default="staircase")
    one.add_argument("--objective",choices=OBJECTIVES,default="peak")
    one.add_argument("--solver",default="cadical195")
    one.add_argument("--time-limit",type=float,default=60.0)
    one.add_argument("--json-out")
    many=sub.add_parser("benchmark",help="Run an experiment grid and save a CSV")
    many.add_argument("instances",nargs="+")
    many.add_argument("--methods",nargs="+",choices=METHODS,default=list(METHODS))
    many.add_argument("--encodings",nargs="+",choices=["staircase","pairwise"],default=["staircase","pairwise"])
    many.add_argument("--objective",choices=OBJECTIVES,default="peak")
    many.add_argument("--time-limit",type=float,default=30.0)
    many.add_argument("--solver",default="cadical195")
    many.add_argument("--out",default="results.csv")
    stats=sub.add_parser("encoding-stats",help="Compare CNF size of both encodings")
    stats.add_argument("instance")
    args=ap.parse_args(argv)
    if args.command=="solve":
        r=solve(load_instance(args.instance),method=args.method,encoding=args.encoding,
                objective=args.objective,time_limit=args.time_limit,solver_name=args.solver)
        text=json.dumps(r.as_dict(),ensure_ascii=False,indent=2)
        print(text)
        if args.json_out:
            Path(args.json_out).write_text(text+"\n",encoding="utf8")
    elif args.command=="encoding-stats":
        inst=load_instance(args.instance)
        for encoding in ("pairwise","staircase"):
            f=encode(inst,encoding).formula
            print(f"{encoding}: variables={f.pool.top} clauses={len(f.clauses)}")
    else:
        rows=[]
        for filename in args.instances:
            for path in sorted(Path().glob(filename)) if any(x in filename for x in "*?") else [Path(filename)]:
                inst=load_instance(path)
                for method in args.methods:
                    for encoding in (["staircase"] if method=="gurobi" else args.encodings):
                        r=solve(inst,method=method,encoding=encoding,objective=args.objective,
                                time_limit=args.time_limit,solver_name=args.solver)
                        met=r.metrics or {}
                        record={"instance":inst.name,"n":inst.n,"m":inst.stations,"c":inst.cycle,
                                "method":method,"encoding":encoding,"objective":args.objective,
                                "status":r.status,"peak":met.get("power_peak"),
                                "total_energy":met.get("total_energy"),"station_peak_sum":met.get("station_peak_sum"),
                                "time_s":r.elapsed_s,"iterations":r.iterations,"solver_instances":r.solver_instances,"cnf_vars":r.cnf_vars,
                                "cnf_clauses":r.cnf_clauses,"backend":r.backend,"proof":r.proof,
                                "message":r.message}
                        rows.append(record)
                        print(f"{inst.name:20} {method:16} {encoding:10} {r.status:11} "
                              f"peak={record['peak']} time={r.elapsed_s}s",flush=True)
        if rows:
            with open(args.out,"w",encoding="utf-8",newline="") as fp:
                writer=csv.DictWriter(fp,fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            print("Wrote",args.out)


if __name__=="__main__":
    main()
