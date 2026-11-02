import time
import sys
import os
import cplex
import numpy as np
import time
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="python this.py <path/to/lp>")
    parser.add_argument("input_path", help="path/to/lp")
    args = parser.parse_args()

    start_time = time.time()
    # Read the ILP model from file (converted from SALB3PM formulation)
    prob = cplex.Cplex(args.input_path)
    read_end_time = time.time()

    # Configure solver parameters
    prob.parameters.threads.set(1)  # Single thread for fair comparison
    prob.parameters.clocktype.set(1)  # CPU clock (not wall clock)
    prob.parameters.timelimit.set(7200)  # Time limit as per experimental setup

    # Disable verbose output
    prob.set_log_stream(None)
    prob.set_error_stream(None)
    prob.set_warning_stream(None)
    # prob.set_results_stream(None)

    # Solve the ILP model
    prob.solve()
    end_time = time.time()

    if prob.solution.is_primal_feasible():
        print("Solution is feasible.")
        print("\n---------------------")
        print(f"@@@ {prob.solution.status[prob.solution.get_status()]}")
        # Output results-old: optimal objective value (minimum power peak)
        print(f">>> Benchmark {os.path.basename(args.input_path)} OPT {int(prob.solution.get_objective_value())}"
        f" TimeCost {end_time - start_time} TimeRead {read_end_time - start_time}")
        # print(f"### {prob.solution.get_values()}")
    else:
        print("Solution is infeasible.")