# Enhanced entry point: executes before legacy imports when explicitly requested.
# Default command-line behavior of this original file remains unchanged.
import sys as _enh_sys
from pathlib import Path as _enh_Path
_enh_sys.path.insert(0, str(_enh_Path(__file__).resolve().parents[2]))
from salb3pm.compat import enhanced_requested as _enh_requested, execute as _enh_execute
if _enh_requested(_enh_sys.argv[1:]):
    raise SystemExit(_enh_execute('multiple_sat', _enh_sys.argv[1:], 'cadical195'))

"""
SAT-based solver for SALB3PM using SAT-UNSAT search with Inaugural formulation (SAT-SU-I).

This solver implements the SAT-UNSAT search strategy to find the optimal power peak value.
It uses the inaugural objective formulation with unary encoding.

Search Strategy: SAT-UNSAT (SU)
- Iteratively finds SAT solutions and adds constraints to ban them
- Each iteration finds a solution with strictly lower power peak
- Continues until UNSAT, proving optimality
- More iterations than binary search but may find optimal value faster in practice

Objective Formulation: Inaugural (I)
- Uses unary encoding with E[1..ub] variables
- Minimizes the maximum power peak (Eq. 8)
- Simpler encoding but requires more variables than enhanced formulation

Constraints implemented (all from paper):
- Eq. (2): Each task assigned to exactly one workstation
- Eq. (3): Workload capacity constraint
- Eq. (4)-(5): Precedence and start time constraints
- Eq. (6): Impossible start times
- Eq. (7): Non-overlap constraint
- Eq. (8): Power peak constraint (objective with unary encoding)
"""

from pysat.card import CardEnc
from pysat.formula import *
from pysat.pb import *
from pysat.solvers import *
import re
import time
import os
import argparse
import pysat.card as card
from math import ceil,floor
from math import log2,ceil

# Encoding types for cardinality and pseudo-Boolean constraints
card_encoding = card.EncType.cardnetwrk
PB_encoding = EncType.best

# Variable pool for managing Boolean variables
vpool = IDPool(start_from=1)

# Boolean variable definitions:
# X(j,k): task j assigned to workstation k (Eq. 2)
# S(j,t): task j starts at time t (Eq. 4)
# A(j,t): auxiliary variable indicating if time t is active for task j (used in Eq. 7 and Eq. 8)
# E(j): unary encoding variable for objective (power peak) - inaugural formulation
X = lambda j, k: vpool.id('X{0}@{1}'.format(j, k))
S = lambda j, t: vpool.id('S{0}@{1}'.format(j, t))
A = lambda j, t: vpool.id('A{0}@{1}'.format(j, t))
E = lambda j: vpool.id('E{0}'.format(j))

# Dictionaries for tracking negated variables and constraints (reduction rules)
neg_X = {}  # Track negated X[j,k] variables
neg_XS_pair = {}  # Track negated X[j,k],S[j,t] pairs
pos_A = {}  # Track positive A[j,t] variables (active time slots)

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

def parse_str(S_str, key_char='S'):
    """Parse variable name to extract task index and time/workstation index."""
    j, t = S_str.lstrip(key_char).split('@', 1)
    return int(j), int(t)

def get_cnf_insatance(n, m, c, T, W, precedence_relations, vpool, ub):
    """
    Generate CNF instance with INAUGURAL objective formulation for SAT-SU-I.
    
    This function encodes all constraints from the paper into SAT clauses.
    The inaugural formulation uses unary encoding for the objective.
    
    Constraints:
    - Eq. (2): Task assignment constraint
    - Eq. (3): Workload capacity constraint
    - Eq. (4)-(5): Start time constraints
    - Eq. (6): Invalid start times
    - Eq. (7): Non-overlap constraint
    - Eq. (8): Power peak constraint with unary encoding
    
    Args:
        n: number of tasks
        m: number of workstations
        c: cycle time
        T: processing times
        W: power consumption values
        precedence_relations: list of (i,j) precedence pairs
        vpool: variable pool
        ub: upper bound on power peak
    
    Returns:
        cnf: CNF formula with all constraints
    """
    cnf = CNF()

    '''Eq. (3): Tasks assigned to the same workstation have the sum of their processing times bounded by c'''
    for k in range(1, m + 1):
        lits = []
        weight = []
        for j in range(1, n + 1):
            if X(j, k) in neg_X:
                continue
            lits.append(X(j, k))
            weight.append(T[j])
        cnf.extend(
            PBEnc.leq(
                lits=lits,
                weights=weight, bound=c, vpool=vpool, encoding=PB_encoding
            )
        )
    '''Tasks assigned  to the same workstation have the sum of their processing times bounded by c'''

    for j in range(1, n + 1):
        # Eq. (2): Each task assigned to exactly one workstation
        cnf.extend(
            card.CardEnc.equals(lits=[X(j, k) for k in range(1, m + 1) if X(j, k) not in neg_X], bound=1,
                                encoding=card_encoding,
                                vpool=vpool))  # (1)(2)
        # Eq. (4)-(5): Each task has exactly one start time
        cnf.extend(card.CardEnc.equals(lits=[S(j, t) for t in range(0, c - T[j] + 1)], bound=1,
                                       encoding=card_encoding, vpool=vpool))  # (4)(5)
        for k in range(1, m + 1):
            # Eq. (7): Non-overlap constraint for tasks on same workstation
            for i in range(1, j):
                cnf.extend([[-X(i, k), -X(j, k), -A(i, t), -A(j, t)] for t in range(0, c) if not X(j, k) in neg_X if not X(i, k) in neg_X])  # (7)

        # Eq. (5): Start time constraints - link S[j,t] with A[j,t']
        for t in range(0, c - T[j] + 1):
            for t_prime in range(c):
                if t_prime >= t and t_prime - t < T[j]:
                    if A(j, t_prime) not in pos_A:
                        cnf.append([-S(j, t), A(j, t_prime)])
                else:
                    cnf.append([-S(j, t), -A(j, t_prime)])
        # Eq. (6): Impossible start times
        cnf.extend([[-S(j, t)] for t in range(c - T[j] + 1, c)])  # (6)

    # Eq. (3): Precedence constraints
    for i, j in precedence_relations:
        for k in range(1, m + 1):
            bound = k
            lits = [X(j, k)] if X(j, k) not in neg_X else []
            for h in range(1, k + 1):
                if X(i, h) in neg_X:
                    bound -= 1
                    continue
                lits.append(-X(i, h))
            cnf.extend(
                card.CardEnc.atmost(
                    lits=lits,
                    bound=bound,
                    encoding=card_encoding, vpool=vpool
                )
            )
            for t in range(0, c - T[j] + 1):
                S_lits = [-S(i, tau) for tau in range(0, t - T[i] + 1)]
                cnf.extend(
                    card.CardEnc.atmost(
                        lits=[S(j, t), X(i, k), X(j, k)] + S_lits,
                        bound=2 + len(S_lits),
                        encoding=card_encoding, vpool=vpool
                    )
                )

    # Inaugural objective: unary encoding with E[1..ub] variables
    # Monotonicity: E[i] → E[i-1]
    for i in range(2, ub + 1):
        cnf.append([-E(i), E(i - 1)])

    # Eq. (8): Power peak constraint with unary encoding
    # At any time t, sum of power ≤ value represented by E variables
    for t in range(c):
        lits = [A(j, t) for j in range(1, 1 + n)] + [-E(x) for x in range(1, ub + 1)]
        weights = [W[j] for j in range(1, 1 + n)] + [1] * ub
        cnf.extend(PBEnc.leq(lits=lits, weights=weights, bound=ub, vpool=vpool, encoding=PB_encoding))

    return cnf

def trans(x:int):
    """Convert variable ID to variable name string."""
    if x>0:
        return vpool.obj(x)
    else:
        return f"-{vpool.obj(-x)}"

def custom_sort(record):
    """Custom sorting for variable names with natural number ordering."""
    name = record
    parts = re.split(r'([0-9]*\.[0-9]+|[0-9]+)', name)
    converted_parts = []
    for part in parts:
        if part.isdigit():
            converted_parts.append(int(part))
        elif re.match(r'[0-9]*\.[0-9]+', part):
            converted_parts.append(float(part))
        elif part:
            converted_parts.append(part)
    if type(converted_parts[0]) == int:
        return tuple([str(converted_parts[0])]+converted_parts[1:])
    return tuple(converted_parts)

def get_var_list(model, n, key_char='S'):
    """Extract variables of a specific type from the model."""
    S_list = []
    for m in model:
        if m is None:
            continue
        if m.find(key_char)!=-1 and m.find("-")==-1:
            S_list.append(m)
    return S_list

def get_specific_var_list(model, n, key_char):
    """Extract and sort variables to create a task-indexed list."""
    S_list = get_var_list(list(map(trans, model)), n, key_char)
    S_list.sort(key=custom_sort)
    S_model = [-1]
    for id, s in enumerate(S_list):
        j, t = parse_str(s, key_char)
        assert(j == id+1)
        S_model.append(t)
    return S_model

def get_maxW(n, T, W, s_model, x_model):
    """
    Calculate the maximum power peak from a SAT model.
    
    Args:
        n: number of tasks
        T: processing times
        W: power consumption values
        s_model: list of start times for each task
        x_model: list of workstation assignments for each task
    
    Returns:
        tuple: (max_power_peak, time_of_max_peak, list_of_tasks_at_that_time)
    """
    maxW = 0
    ret = None
    book_m = [[0] * c for _ in range(m + 1)]
    for i in range(1, n + 1):
        for j in range(s_model[i], s_model[i] + T[i]):
            assert book_m[x_model[i]][j] == 0
            book_m[x_model[i]][j] = i
    for t in range(0, c):
        task_list = []
        w = 0
        for s in range(1, m + 1):
            task = book_m[s][t]
            if task==0:
                continue
            task_list.append(task)
            w += W[task]
        if w > maxW:
            maxW = w
            ret = (maxW, t, task_list)

    return ret

def get_single_machine_time(ealiest_st_time, T):
    """
    Calculate the makespan for tasks on a single machine.
    Used for computing lower bounds on task completion times.
    """
    C_max = 0
    st_T_pair = sorted(list(zip(ealiest_st_time, T)))
    for r, t in st_T_pair:
        C_max = max(C_max, r) + t
    return C_max

def get_precedence_constraints(n, m, c, T, W, precedence_relations):
    """
    Apply reduction rules based on precedence constraints to eliminate impossible assignments.
    
    This implements the reduction rules to reduce the search space:
    - Forward pass: compute earliest possible workstation (tau_list)
    - Backward pass: compute latest possible workstation (tau_r_list)
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

    # Forward pass: compute earliest possible workstation
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

    # Backward pass: compute latest possible workstation
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
    cnf_precedence = CNF()
    for i in range(1, n + 1):
        # Left side: eliminate workstations before earliest possible
        impossible_station_l = tau_list[i] // c
        for j in range(1, impossible_station_l + 1):
            cnf_precedence.append([-X(i, j)])
            neg_X[X(i, j)] = 1
        assert impossible_station_l < m
        # Eliminate impossible start times on earliest workstation
        l_slot = tau_list[i] - c * (impossible_station_l)
        for t in range(l_slot):
            cnf_precedence.append([-X(i, impossible_station_l + 1), -S(i, t)])
            neg_XS_pair[(X(i, impossible_station_l + 1), S(i, t))] = 1

        # Right side: eliminate workstations after latest possible
        tau_r_list[i] += T[i]-1
        impossible_station_r = tau_r_list[i] // c
        for j in range(1, impossible_station_r + 1):
            cnf_precedence.append([-X(i, m - j + 1)])
            neg_X[X(i, m-j+1)] = 1
        assert impossible_station_r < m
        # Eliminate impossible start times on latest workstation
        r_slot = tau_r_list[i] - c * (impossible_station_r)
        for t in range(1, r_slot + 1):
            cnf_precedence.append([-X(i, m - impossible_station_r), -S(i, c - t)])
            neg_XS_pair[(X(i, m - impossible_station_r), S(i, c - t))]=1

    return cnf_precedence

def get_longTask_constraints(n, m, c, T, W, precedence_relations):
    """
    Generate reduction constraints for long tasks.
    
    For long tasks, certain time slots are always active, reducing the number of A[j,t] variables.
    This is part of the reduction rules to minimize variable count.
    """
    LongTask_cnf = CNF()
    for i in range(1, n + 1):
        # Determine the range of time slots that are always active for task i
        l = c - T[i]
        r = T[i] - 1
        if l > r:
            continue

        # For tasks that span more than half the cycle time, mark active slots
        for t in range(l, r + 1):
            pos_A[A(i, t)] = 1
            LongTask_cnf.append([A(i, t)])

    return LongTask_cnf

if __name__ == '__main__':
    """
    Main entry point for SAT-SU-I solver.
    
    Usage: python Cadical-SU-I.py <input_file>
    
    This solver uses SAT-UNSAT search with the inaugural objective formulation
    to find the optimal power peak value for SALB3PM.
    """
    parser = argparse.ArgumentParser(description="Solving SALB3PM with Cadical195.")
    parser.add_argument("input_file", type=str, help="Path to the .3pm document")
    parser.add_argument('--precedence_constraint', action='store_true', default=True,
                        help='Enable the precedence constraints')
    parser.add_argument('--no-precedence_constraint', action='store_false', dest='precedence_constraint',
                        help='Disable the precedence constraints')
    parser.add_argument('--long_task_constraint', action='store_true', default=True,
                        help='Enable the long-task constraints')
    parser.add_argument('--no-long_task_constraint', action='store_false', dest='long_task_constraint',
                        help='Disable the long-task constraints')
    args = parser.parse_args()

    input_file = args.input_file
    start_time = time.time()
    n, m, c, T, W, precedence_relations = parse_3pm_file(input_file)
    cnf = CNF()

    # Apply reduction rules
    if args.precedence_constraint:
        print("c precedence constraints enabled!")
        cnf_precedence = get_precedence_constraints(n, m, c, T, W, precedence_relations)
        cnf.extend(cnf_precedence)

    if args.long_task_constraint:
        print("c long task constraints enabled!")
        cnf_longTask = get_longTask_constraints(n, m, c, T, W, precedence_relations)
        cnf.extend(cnf_longTask)

    # Compute bounds
    lb = min(W[1:])
    ub = sum(sorted(W[1:], reverse=True)[:min(m, len(W) - 1)])
    cnf.extend(get_cnf_insatance(n, m, c, T, W, precedence_relations, vpool, ub))

    solve_start_time = time.time()
    print(f"$$$ Transformation time: {solve_start_time - start_time}")

    ff = 1
    MinW = float('inf')
    ub_cnf = CNF()
    print(f"@@@ nb_var {cnf.nv} nb_cons {len(cnf.clauses)}")

    E_lits = [E(x) for x in range(1, ub + 1)]

    # SAT-UNSAT search: iteratively find solutions and ban them
    while ff:
        solver = Solver(name='Cadical195', bootstrap_with=cnf.clauses+ub_cnf.clauses)
        solver.solve()
        if not solver.get_status():
            # UNSAT: found optimal solution
            break
        model = solver.get_model()
        s_model = get_specific_var_list(model, n, key_char='S')
        x_model = get_specific_var_list(model, n, key_char='X')
        focus_on = get_maxW(n, T, W, s_model, x_model)
        MinW = focus_on[0]
        print(f"new W : {MinW} | {time.time() - solve_start_time:.4f}")
        # Add constraint to ban this solution: sum of E[x] ≤ MinW-1 (unary encoding)
        ub_cnf = card.CardEnc.atmost(lits=E_lits, bound=MinW-1, vpool=vpool, encoding=card.EncType.cardnetwrk)

    end_time = time.time()
    print(f"### Benchmark {os.path.basename(input_file)} OPT {MinW} TotTime {end_time - start_time} RealTime {end_time - solve_start_time}")
# Report the schedule-invariant discrete energy for legacy baseline runs.
if __name__ == "__main__":
    print(f"### TotalEnergy {sum(T[j]*W[j] for j in range(1,n+1))} "
          f"TotalTaskPower {sum(W[1:])}")
