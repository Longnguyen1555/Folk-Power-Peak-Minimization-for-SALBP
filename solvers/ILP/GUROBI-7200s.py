import time
import sys
import os
from gurobipy import Model, GRB, read
import numpy as np
import argparse
import signal

TIME_LIMIT = 7200

# Status code mapping for GUROBI solver
status_map = {
    1: 'LOADED',
    2: 'OPTIMAL',
    3: 'INFEASIBLE',
    4: 'INF_OR_UNBD',
    5: 'UNBOUNDED',
    6: 'CUTOFF',
    7: 'ITERATION_LIMIT',
    8: 'NODE_LIMIT',
    9: 'TIME_LIMIT',
    10: 'SOLUTION_LIMIT',
    11: 'INTERRUPTED',
    12: 'NUMERIC',
    13: 'SUBOPTIMAL',
    14: 'INPROGRESS',
}

def check_cpu_time(start_time, time_limit):
    """Check if CPU time limit has been exceeded."""
    if time.process_time() - start_time > time_limit:
        raise TimeoutError

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="python this.py <path/to/lp>")
    parser.add_argument("input_path", help="path/to/lp")
    args = parser.parse_args()

    start_time = time.process_time()
    # Read the ILP model from file (converted from SALB3PM formulation)
    model = read(args.input_path)
    read_end_time = time.process_time()

    # Configure solver parameters
    model.Params.Threads = 1  # Single thread for fair comparison
    model.Params.TimeLimit = 7200  # Time limit as per experimental setup

    # Configure output verbosity
    model.Params.LogToConsole = 1  # Keep output but minimize
    model.Params.OutputFlag = 1  # Keep basic output
    model.Params.DisplayInterval = 1e3  # Reduce progress update frequency
    model.Params.TuneOutput = 0

    try:
        # Set up signal handler for CPU time limit
        signal.signal(signal.SIGALRM, lambda signum, frame: check_cpu_time(read_end_time, TIME_LIMIT))
        signal.setitimer(signal.ITIMER_REAL, 1, 1)
        # Solve the ILP model
        model.optimize()
    except TimeoutError:
        print("CPU time limit reached")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)

    end_time = time.process_time()

    if model.status == GRB.OPTIMAL:
        print("Solution is feasible.")
    else:
        print("Solution is infeasible or problem is unbounded.")

    print("\n---------------------")
    print(f"@@@ {status_map[model.status]}")
    # Output results-old: optimal objective value (minimum power peak)
    print(f">>> Benchmark {os.path.basename(args.input_path)} OPT {int(model.objVal)}"
          f" TimeCost {end_time - start_time} TimeRead {read_end_time - start_time}")
    # To print variable values, uncomment the following line:
    # print(f"### {[v.x for v in model.getVars()]}")