import time
import sys
import os
from ortools.sat.python import cp_model
import argparse
from google.protobuf import text_format
import numpy as np
from math import ceil,floor,log2

# Time limit for solving (7200 seconds as per experimental setup)
CUTOFF = 7200

def status_to_string(status):
    """Convert CP-SAT solver status to human-readable string."""
    if status == cp_model.OPTIMAL:
        return "OPTIMAL"
    elif status == cp_model.FEASIBLE:
        return "FEASIBLE"
    elif status == cp_model.INFEASIBLE:
        return "INFEASIBLE"
    elif status == cp_model.MODEL_INVALID:
        return "MODEL_INVALID"
    elif status == cp_model.UNKNOWN:
        return "UNKNOWN"
    else:
        return "UNDEFINED"

# Global variables for constraint reduction
X = {}  # X[j,k]: task j assigned to workstation k (Eq. 2)
S = {}  # S[j,t]: task j starts at time t (Eq. 4)
neg_X = {}  # Dictionary to track negated X variables for reduction rules
neg_XS_pair = {}  # Dictionary to track negated X-S pairs for reduction rules
W_max = None  # Maximum power peak (objective variable)

def get_initial_model(n, m, c, W):
    """
    Initialize the CP-SAT model with variables.
    
    Parameters:
    - n: number of tasks
    - m: number of workstations
    - c: cycle time
    - W: list of power consumption for each task
    
    Returns:
    - model: initialized CP-SAT model
    
    Variables:
    - X[j,k]: Boolean, task j assigned to workstation k
    - S[j,t]: Boolean, task j starts at time t (0 ≤ t < c)
    - W_max: Integer, maximum power peak (objective, Eq. 8)
    """
    global W_max
    model = cp_model.CpModel()
    for j in range(1, n + 1):
        for k in range(1, m + 1):
            X[j, k] = model.NewBoolVar(f'X{j}@{k}')
    for j in range(1, n + 1):
        for t in range(c):
            S[j, t] = model.NewBoolVar(f'S{j}@{t}')
    W_max = model.NewIntVar(0, sum(W), "W_max")
    model.Minimize(W_max)
    return model

def get_CP_SAT_model(model, n, m, c, T, W, precedence_relations):
    """
    Add all SALB3PM constraints to the CP-SAT model.
    
    Constraints implemented:
    - Eq. (2): Each task assigned to exactly one workstation
    - Eq. (3): Workload capacity constraint
    - Eq. (4): Precedence constraint (workstation ordering)
    - Eq. (5): Each task has exactly one start time
    - Eq. (6): Precedence constraint (temporal ordering)
    - Eq. (7): Non-overlap constraint for tasks on same workstation
    - Eq. (8): Power peak constraint (objective)
    """
    # Constraint (2): Each task assigned to exactly one workstation
    for j in range(1, n + 1):
        model.Add(sum(X[j, k] for k in range(1, m + 1) if not X[j, k] in neg_X) == 1)

    # Constraint (3): Workload capacity - sum of processing times on each workstation ≤ c
    for k in range(1, m + 1):
        model.Add(sum(X[j, k] * T[j] for j in range(1, n + 1) if not X[j, k] in neg_X) <= c)

    # Constraint (4): Precedence constraint - if task j on workstation k, 
    # then task i must be on workstation ≤ k
    for i, j in precedence_relations:
        for k in range(1, m + 1):
            if X[j, k] in neg_X:
                continue
            model.Add(X[j, k] <= sum(X[i, h] for h in range(1, k + 1) if not X[i, h] in neg_X))

    # Constraint (5): Each task has exactly one start time
    for j in range(1, n + 1):
        model.Add(sum(S[j, t] for t in range(c - T[j] + 1)) == 1)

    # Constraint (6): Precedence constraint (temporal) - if i→j, then start time of j 
    # must be after start time of i + T[i], considering workstation assignments
    for i, j in precedence_relations:
        for k in range(1, m + 1):
            for t in range(c - T[j] + 1):
                gamma_max = max(0, t - T[i] + 1)
                model.Add(S[j, t] <= sum(S[i, gamma] for gamma in range(gamma_max)) + 2
                          - (X[i, k] if not X[i, k] in neg_X else 0)
                          - (X[j, k] if not X[j,k] in neg_X else 0))

    # Constraint (7): Non-overlap constraint - tasks on same workstation cannot overlap
    for i in range(1, n + 1):
        for j in range(1, i):
            for k in range(1, m + 1):
                for t in range(c):
                    gama_start_i = max(0, t - T[i] + 1)
                    gama_start_j = max(0, t - T[j] + 1)
                    model.Add((X[i, k] if not X[i, k] in neg_X else 0) + (X[j, k] if not X[j,k] in neg_X else 0)
                              + sum(S[i, gama] for gama in range(gama_start_i, t + 1)) +
                              sum(S[j, gama] for gama in range(gama_start_j, t + 1)) <= 3)

    # Constraint (8): Power peak constraint - at any time t, sum of power ≤ W_max
    for t in range(c):
        expr = sum(W[j] * S[j, gama] for j in range(1, n + 1) for gama in range(max(0, t - T[j] + 1), t + 1))
        model.Add(expr <= W_max)

    return model

def parse_3pm_file(input_file):
    """
    Parse the .3pm input file format.
    
    Format:
    - Line 1: n m c (number of tasks, workstations, cycle time)
    - Lines 2 to n+1: t_i w_i (processing time and power for each task)
    - Remaining lines: i,j (precedence relations, terminated by -1,-1)
    """
    with open(input_file, 'r') as file:
        lines = file.readlines()

    # Skip comments and parse the first meaningful line
    line_index = 0
    while lines[line_index].startswith('c'):
        line_index += 1

    n, m, c = map(int, lines[line_index].strip().split())
    T, W = [0], [0]
    precedence_relations = []

    # Parse task information
    for i in range(1, n + 1):
        t, w = map(int, lines[line_index + i].strip().split())
        T.append(t)
        W.append(w)

    # Parse precedence relations
    for line in lines[line_index + n + 1:]:
        i, j = map(int, line.strip().split(','))
        if i == -1 and j == -1:
            break
        precedence_relations.append((i, j))

    return n, m, c, T, W, precedence_relations

def get_single_machine_time(ealiest_st_time, T):
    """
    Calculate the makespan for tasks on a single machine (no parallel workstations).
    Used for computing lower bounds on task completion times.
    """
    C_max = 0
    st_T_pair = sorted(list(zip(ealiest_st_time, T)))
    for r, t in st_T_pair:
        C_max = max(C_max, r) + t
    return C_max

def get_precedence_constraints(model, n, m, c, T, W, precedence_relations):
    """
    Apply reduction rules based on precedence constraints to eliminate impossible assignments.
    
    This implements the reduction rules described in the paper to reduce the search space:
    - Forward pass: compute earliest possible workstation for each task
    - Backward pass: compute latest possible workstation for each task
    - Add unit clauses to eliminate impossible X[j,k] and X[j,k],S[j,t] combinations
    """
    pre_list = [[] for _ in range(n + 1)]
    pre_task_list = [{i} for i in range(n + 1)]
    pre_time_list = [0] * (n + 1)
    suc_list = [[] for _ in range(n + 1)]
    suc_task_list = [{i} for i in range(n + 1)]
    suc_time_list = [0] * (n + 1)
    in_degree = [0] * (n + 1)
    que = [0] * (n + 1)
    ql = 0
    qr = 0
    topo_list = []
    tau_list = [0]*(n+1)
    tau_r_list = [0]*(n+1)

    # Build precedence graph
    for i, j in precedence_relations:
        pre_list[j].append(i)
        suc_list[i].append(j)
        in_degree[j] += 1
        
    # Topological sort
    for i in range(1, n + 1):
        if in_degree[i] == 0:
            que[qr] = i
            qr += 1
    while ql != qr:
        me = que[ql]
        ql += 1
        topo_list.append(me)
        for tt in suc_list[me]:
            in_degree[tt] -= 1
            if in_degree[tt] == 0:
                que[qr] = tt
                qr += 1

    # Forward pass: compute earliest possible workstation (tau_list)
    for me in topo_list:
        for suc in suc_list[me]:
            pre_task_list[suc] = pre_task_list[suc].union(pre_task_list[me])
        pre_time_list[me] = sum([T[pre] for pre in pre_task_list[me]])
        tau_i = (ceil(pre_time_list[me]/c)-1) * c
        single_machine_value = get_single_machine_time([tau_list[j] for j in pre_task_list[me] if j!=me],
                                                       [T[j] for j in pre_task_list[me] if j!=me])
        tau_i = max(tau_i, single_machine_value)
        if tau_i > floor(tau_i/c)*c and len(pre_list[me])!=0:
            tau_i = max(tau_i, floor(tau_i/c)*c + min([T[j] for j in pre_list[me]]))
        if ceil((tau_i + T[me])/c) > floor(tau_i/c) + 1:
            tau_i = (floor(tau_i/c) + 1) * c
        tau_list[me] = tau_i

    # Backward pass: compute latest possible workstation (tau_r_list)
    for me in topo_list[::-1]:
        for pre in pre_list[me]:
            suc_task_list[pre] = suc_task_list[pre].union(suc_task_list[me])
        suc_time_list[me] = sum([T[suc] for suc in suc_task_list[me]])
        tau_i_r = (ceil(suc_time_list[me]/c)-1) * c
        single_machine_value = get_single_machine_time([tau_r_list[j] for j in suc_task_list[me]  if j!=me],
                                                       [T[j] for j in suc_task_list[me] if j!=me])
        tau_i_r = max(tau_i_r, single_machine_value)
        if tau_i_r > floor(tau_i_r/c)*c and len(suc_list[me])!=0:
            tau_i_r = max(tau_i_r, floor(tau_i_r/c)*c + min([T[j] for j in suc_list[me]]))
        if ceil((tau_i_r + T[me])/c) > floor(tau_i_r/c) + 1:
            tau_i_r = (floor(tau_i_r/c) + 1) * c
        tau_r_list[me] = tau_i_r

    # Add reduction constraints to eliminate impossible assignments
    for i in range(1, n + 1):
        # Left side: eliminate workstations before earliest possible
        impossible_station_l = tau_list[i] // c
        for j in range(1, impossible_station_l + 1):
            model.Add(X[i, j]  == 0)
            neg_X[X[i, j]] = 1
        assert impossible_station_l < m
        # Eliminate impossible start times on earliest workstation
        l_slot = tau_list[i] - c * (impossible_station_l)
        for t in range(l_slot):
            model.Add( (X[i, impossible_station_l + 1] + S[i,t])  <= 1)
            neg_XS_pair[(X[i, impossible_station_l + 1], S[i, t])] = 1

        # Right side: eliminate workstations after latest possible
        tau_r_list[i] += T[i]-1
        impossible_station_r = tau_r_list[i] // c
        for j in range(1, impossible_station_r + 1):
            model.Add(X[i, m-j+1]  == 0)
            neg_X[X[i, m-j+1]] = 1
        assert impossible_station_r < m
        # Eliminate impossible start times on latest workstation
        r_slot = tau_r_list[i] - c * (impossible_station_r)
        for t in range(1, r_slot + 1):
            model.Add( (X[i, m - impossible_station_r] + S[i, c - t])  <= 1)
            neg_XS_pair[(X[i, m - impossible_station_r], S[i, c - t])]=1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="python this.py <path/to/3pm>")
    parser.add_argument("input_path", help="path/to/3pm")
    args = parser.parse_args()
    input_file = args.input_path

    start_time = time.time()

    # Parse input file to get problem parameters
    n, m, c, T, W, precedence_relations = parse_3pm_file(input_file)

    # Build the CP-SAT model
    model = get_initial_model(n, m, c, W)
    get_precedence_constraints(model, n, m, c, T, W, precedence_relations)
    get_CP_SAT_model(model, n, m, c, T, W, precedence_relations)
    trans_end_time = time.time()
    print(f"$$$ Done modeling at {trans_end_time-start_time} seconds")
    
    # Create solver and solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = CUTOFF
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    end_time = time.time()

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("Solution is feasible.")
        print("\n---------------------")
        print(f"@@@ {status_to_string(status)}")
        print(f">>> Benchmark {os.path.basename(args.input_path)} OPT {int(solver.ObjectiveValue())}"
              f" TimeTot {end_time - start_time} TimeReal {end_time - trans_end_time} TimeTrans {trans_end_time - start_time}"
              f" Status {status_to_string(status)}")
    else:
        print(f">>> Benchmark {os.path.basename(args.input_path)} OPT {int(solver.ObjectiveValue())}"
              f" TimeTot {end_time - start_time} TimeReal {end_time - trans_end_time} TimeTrans {trans_end_time - start_time}"
              f" Status {status_to_string(status)}")