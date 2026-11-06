#!/usr/bin/env python3
"""Build a fixed-feasibility CNF size table; no SAT solver needed."""
import argparse
import csv
import glob
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from salb3pm.model import load_instance
from salb3pm.cnf import encode


def main(argv=None):
    ap=argparse.ArgumentParser(description="Pairwise-vs-staircase feasibility encoding size")
    ap.add_argument("paths",nargs="+",help=".3pm paths and quoted globs")
    ap.add_argument("--out",default="experiments/encoding_stats.csv")
    args=ap.parse_args(argv)
    paths=sorted(set(p for item in args.paths for p in (glob.glob(item) or [item])))
    rows=[]
    for path in paths:
        ins=load_instance(path)
        for encoding in ("pairwise","staircase"):
            start=time.monotonic()
            formula=encode(ins,encoding).formula
            rows.append({"instance":ins.name,"file":path,"n":ins.n,"m":ins.stations,"c":ins.cycle,
                         "precedence_arcs":len(ins.precedence),"encoding":encoding,
                         "cnf_variables":formula.pool.top,"cnf_clauses":len(formula.clauses),
                         "encoding_time_s":round(time.monotonic()-start,5),
                         "total_energy_invariant":ins.total_energy})
            print(f"{ins.name:25} {encoding:12} {formula.pool.top:9} vars {len(formula.clauses):10} clauses")
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf8",newline="") as fp:
        writer=csv.DictWriter(fp,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    print(f"Wrote {out} ({len(rows)} rows)")

if __name__=="__main__":
    main()
