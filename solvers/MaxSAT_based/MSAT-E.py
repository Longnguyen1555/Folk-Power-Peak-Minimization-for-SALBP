# Explicit --solve invokes the new RC2 runner. No flags: generate original WCNF.
import sys as _enh_sys
from pathlib import Path as _enh_Path
_enh_sys.path.insert(0, str(_enh_Path(__file__).resolve().parents[2]))
from salb3pm.compat import execute as _enh_execute
if "--solve" in _enh_sys.argv[1:]:
    _enh_args = [x for x in _enh_sys.argv[1:] if x != "--solve"]
    # Original syntax had an output .wcnf positional argument; not used in solve mode.
    _enh_args = [x for x in _enh_args if not x.endswith(".wcnf")]
    raise SystemExit(_enh_execute("maxsat", _enh_args))

from pysat.formula import *
from pysat.pb import *
from pysat.solvers import *
from pysat.examples.rc2 import RC2
from math import log2, ceil
import time
import sys
import os
import re
import pysat.card as card
from math import ceil,floor
import argparse

# Encoding types for cardinality and pseudo-Boolean constraints
card_encoding = card.EncType.cardnetwrk
PB_encoding = EncType.best

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

# Variable pool for managing Boolean variables
vpool = IDPool(start_from=1)

# Boolean variables:
# X(j,k): task j assigned to workstation k (Eq. 2)
# S(j,t): task j starts at time t (Eq. 4)
# A(j,t): auxiliary variable indicating if time t is active for task j (used for long tasks)
# E(j): auxiliary variable for objective encoding (enhanced formulation - binary encoding)
X = lambda j, k: vpool.id('X{0}@{1}'.format(j, k))
S = lambda j, t: vpool.id('S{0}@{1}'.format(j, t))
A = lambda j, t: vpool.id('A{0}@{1}'.format(j, t))
E = lambda j: vpool.id('E{0}'.format(j))

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
    Generate constraints for long tasks (tasks with T[j] > c/2).
    
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

def get_wcnf_insatance(n, m, c, T, W, precedence_relations, vpool, ub, lb):
    """
    Generate MaxSAT instance with enhanced objective formulation (MSAT-E).
    
    The enhanced formulation uses binary encoding for the objective:
    - Variables E[0..nb_E-1] represent binary bits of the power peak value
    - Minimize sum(2^i * E[i]) to minimize power peak (Eq. 8)
    - This dramatically reduces the number of variables and clauses compared to inaugural formulation
    - See Table 1 in paper for comparison
    
    Constraints implemented:
    - Eq. (2): Each task assigned to exactly one workstation
    - Eq. (3): Workload capacity constraint
    - Eq. (4)-(5): Precedence and start time constraints
    - Eq. (6): Impossible start times
    - Eq. (7): Non-overlap constraint
    - Eq. (8): Power peak constraint (objective with binary encoding)
    
    Parameters:
    - ub: upper bound on power peak
    - lb: lower bound on power peak
    """
    wcnf = WCNF()

    # Enhanced objective: binary encoding with E[0..nb_E-1] variables
    # nb_E = ceil(log2(ub+1)) bits needed to represent power peak
    nb_E = ceil(log2(ub + 1))

    # Minimize sum(2^i * E[i]) to minimize power peak
    for i in range(0, nb_E + 1):
        wcnf.append([-E(i)], weight=2 ** i)

    '''Eq. (3): Tasks assigned to the same workstation have the sum of their processing times bounded by c'''
    for k in range(1, m + 1):
        lits = []
        weight = []
        for j in range(1, n + 1):
            if X(j, k) in neg_X:
                continue
            lits.append(X(j, k))
            weight.append(T[j])
        wcnf.extend(
            PBEnc.leq(
                lits=lits,
                weights=weight, bound=c, vpool=vpool, encoding=PB_encoding
            )
        )
    '''Tasks assigned  to the same workstation have the sum of their processing times bounded by c'''

    for j in range(1, n + 1):
        # Eq. (2): Each task assigned to exactly one workstation
        wcnf.extend(
            card.CardEnc.equals(lits=[X(j, k) for k in range(1, m + 1) if X(j, k) not in neg_X], bound=1, encoding=card_encoding,
                                vpool=vpool))  # (1)(2)
        # Eq. (4)-(5): Each task has exactly one start time
        wcnf.extend(card.CardEnc.equals(lits=[S(j, t) for t in range(0, c - T[j] + 1)], bound=1,
                                        encoding=card_encoding, vpool=vpool))  # (4)(5)
        for k in range(1, m + 1):
            # Eq. (7): Non-overlap constraint for tasks on same workstation
            for i in range(1, j):
                wcnf.extend([[-X(i, k), -X(j, k), -A(i, t), -A(j, t)] for t in range(0, c) if X(i, k) not in neg_X if X(j, k) not in neg_X])  # (7)

        # Eq. (5): Start time constraints - link S[j,t] with A[j,t']
        for t in range(0, c - T[j] + 1):
            for t_prime in range(c):
                if t_prime >= t and t_prime - t < T[j]:
                    if A(j, t_prime) not in pos_A:
                        wcnf.append([-S(j, t), A(j, t_prime)])
                else:
                    wcnf.append([-S(j, t), -A(j, t_prime)])
        # Eq. (6): Impossible start times
        wcnf.extend([[-S(j, t)] for t in range(c - T[j] + 1, c)])  # (6)

    """ Precedence constraints (Eq. 4) """
    for i, j in precedence_relations:
        for k in range(1, m + 1):
            # Workstation ordering: if j on k, then i must be on ≤ k
            bound = k
            lits = [X(j, k)] if X(j, k) not in neg_X else []
            for h in range(1, k + 1):
                if X(i, h) in neg_X:
                    bound -= 1
                    continue
                lits.append(-X(i, h))
            wcnf.extend(
                card.CardEnc.atmost(
                    lits=lits,
                    bound=bound,
                    encoding=card_encoding, vpool=vpool
                )
            )
            # Temporal ordering: if i→j and both on k, then start time of j > start time of i
            for t in range(0, c - T[j] + 1):
                    S_lits = [-S(i, tau) for tau in range(0, t-T[i]+1)]
                    wcnf.extend(
                        card.CardEnc.atmost(
                            lits = [S(j,t), X(i, k), X(j,k)] + S_lits,
                            bound = 2 + len(S_lits),
                            encoding=card_encoding, vpool=vpool
                        )
                    )

    """ Objective constraints for enhanced formulation """
    # Lower bound: binary value must be ≥ lb
    lits = [E(x) for x in range(nb_E + 1)]
    weights = [2 ** x for x in range(nb_E + 1)]
    wcnf.extend(PBEnc.geq(lits=lits, weights=weights, bound=lb, vpool=vpool, encoding=PB_encoding))

    # Eq. (8): Power peak constraint with binary encoding
    # At any time t, sum of power ≤ binary value represented by E bits
    l_ub = sum([2 ** i for i in range(nb_E + 1)])
    for t in range(c):
        lits = [A(j, t) for j in range(1, 1 + n)] + [-E(x) for x in range(nb_E + 1)]
        weights = [W[j] for j in range(1, 1 + n)] + [2 ** x for x in range(nb_E + 1)]
        wcnf.extend(PBEnc.leq(lits=lits, weights=weights, bound=l_ub, vpool=vpool, encoding=PB_encoding))

    return wcnf

def merge_wcnf(wcnf1, wcnf2):
    """Merge two WCNF formulas by combining hard and soft clauses."""
    for clause in wcnf2.hard:
        wcnf1.append(clause)

    for clause, weight in zip(wcnf2.soft, wcnf2.wght):
        wcnf1.append(clause, weight=weight)

    wcnf1.topw = max(wcnf1.topw, wcnf2.topw)
    return wcnf1

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="python this.py <path/to/3pm> <path/to/wcnf_old>")
    parser.add_argument("input_path", help="path/to/3pm")
    parser.add_argument("output_path", help="path/to/wcnf_old")
    args = parser.parse_args()
    input_file = args.input_path
    output_path = args.output_path

    start_time = time.time()
    # Parse input file
    n, m, c, T, W, precedence_relations = parse_3pm_file(input_file)
    # Compute bounds for objective
    lb = min(W[1:])
    ub = sum(sorted(W[1:], reverse=True)[:min(m, len(W) - 1)])
    print("lb:{0} ub:{1}".format(lb, ub))
    
    # Build MaxSAT instance with enhanced formulation
    wcnf = WCNF()
    wcnf.extend(get_precedence_constraints(n, m, c, T, W, precedence_relations))
    wcnf.extend(get_longTask_constraints(n, m, c, T, W, precedence_relations))
    wcnf = merge_wcnf(wcnf,get_wcnf_insatance(n, m, c, T, W, precedence_relations, vpool, ub, lb))

    solve_start_time = time.time()
    print(f"$$$ TimeEncoding: {solve_start_time - start_time}")
    print(f"### nb_var {wcnf.nv} nb_cons {len(wcnf.hard)+len(wcnf.soft)}")
    # Write to WCNF file for MaxSAT solvers
    wcnf.to_file(output_path)
# Report this invariant even when the original WCNF is only generated.
if __name__ == "__main__":
    print(f"### TotalEnergy {sum(T[j]*W[j] for j in range(1,n+1))} "
          f"TotalTaskPower {sum(W[1:])}")
