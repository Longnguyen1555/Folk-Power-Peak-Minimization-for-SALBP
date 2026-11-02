import time
import sys
import os
from pyscipopt import Model
import numpy as np
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="python this.py <path/to/lp>")
    parser.add_argument("input_path", help="path/to/lp")
    args = parser.parse_args()

    start_time = time.time()
    # Create SCIP model and read from file (converted from SALB3PM formulation)
    model = Model()
    model.readProblem(args.input_path)
    read_end_time = time.time()

    # Configure solver parameters
    model.setParam('parallel/maxnthreads', 1)  # Single thread for fair comparison
    model.setParam('limits/time', 7200)  # Time limit as per experimental setup
    model.setParam('display/verblevel', 3)  # Verbosity level
    model.setParam('display/freq', 100)  # Display frequency

    # Solve the ILP model
    model.optimize()
    end_time = time.time()

    status = model.getStatus()
    if status == "optimal":
        print("Solution is feasible.")
        # To print variable values, uncomment the following line:
        # print(f"### {[model.getVal(v) for v in model.getVars()]}")
    else:
        print(f"Solution status: {status}")
    print("\n---------------------")
    print(f"@@@ {status}")
    # Output results-old: optimal objective value (minimum power peak)
    print(f">>> Benchmark {os.path.basename(args.input_path)} OPT {int(model.getObjVal())}"
          f" TimeCost {end_time - start_time} TimeRead {read_end_time - start_time}")