"""
Pseudoboolean Inaugural Formulation (PBO-I) for 3PM Problem
==========================================================

This file implements the Pseudoboolean Inaugural formulation for solving
the 3-Partite Matching Problem (3PM) with power peak optimization.

Key Features:
- Uses the inaugural objective formulation
- Objective function employs unary encoding (same as MSAT-I)
- Implements all constraints from Eq. (2) to Eq. (8)
- Utilizes reduction rules to eliminate impossible assignments
- Supports precedence constraints between tasks

Formulation Details:
- X[j,k]: Boolean variable, true if task j is assigned to workstation k
- S[j,t]: Boolean variable, true if task j starts at time t
- A[j,t]: Boolean variable, true if task j is active at time t
- E[i]: Boolean variables for unary encoding of objective (power peak)
  
Constraints:
- Eq. (2): Task assignment constraint (each task assigned to exactly one workstation)
- Eq. (3): Precedence constraint (task i before task j)
- Eq. (4): Start time selection (each task has exactly one start time)
- Eq. (5): Start time exclusion (no duplicate start times)
- Eq. (6): Valid start time range
- Eq. (7): Non-overlap constraint on same workstation at same time
- Eq. (8): Power peak constraint (bounded by objective value)
"""

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


class PBOWriter:
    def __init__(self):
        self.variables = {"Happy":0}
        self.objective = ""
        self.constraints = []

    def get_internal_lit(self, lit_name):
        lit_name = str(lit_name)
        if lit_name.startswith("-"):
            name = lit_name[1:]
        else:
            name = lit_name
        if name not in self.variables:
            self.variables[name] = "x" + str(len(self.variables))
        if lit_name.startswith("-"):
            return "~" + self.variables[name]
        else:
            return self.variables[name]

    def set_objective(self, coeffs, vars, minimize=True):
        assert minimize == True
        terms = []
        for c, v in zip(coeffs, vars):
            if c >= 0:
                terms.append(f"+{c} {self.get_internal_lit(v)}")
            else:
                terms.append(f"{c} {self.get_internal_lit(v)}")
        self.objective = f"{'min' if minimize else 'max'}: {' '.join(terms)};"

    def add_clause(self, vars):
        op = ">="
        rhs = 1
        coeffs = [1] * len(vars)
        assert op == ">=" or op == "="
        self.add_constraint(coeffs, vars, op, rhs)

    def add_constraint(self, coeffs, vars, op, rhs):
        assert op == ">=" or op == "=" or op=="<="
        if op == "<=":
            coeffs = [-c for c in coeffs]
            rhs = -rhs
            op = ">="
        # 修改约束条件格式
        terms = []
        for c, v in zip(coeffs, vars):
            if c >= 0:
                terms.append(f"+{c} {self.get_internal_lit(v)}")
            else:
                terms.append(f"{c} {self.get_internal_lit(v)}")
        self.constraints.append(f"{' '.join(terms)} {op} {rhs};")

    def write_to_file(self, filename):
        with open(filename, 'w') as f:
            f.write(f"* #variable= {len(self.variables)}\n")
            f.write(f"* #constraints= {len(self.constraints)}\n")
            f.write(self.objective + "\n")
            for constraint in self.constraints:
                f.write(constraint + "\n")


# Dictionaries for tracking negated variables and constraints (reduction rules)
# These are used to eliminate impossible assignments and reduce problem size
neg_X = {}  # Track negated X[j,k] variables (task j cannot be assigned to workstation k)
neg_XS_pair = {}  # Track negated pairs (X[j,k], S[j,t]) (task j cannot start at time t on workstation k)
pos_A = {}  # Track positive A[j,t] variables (always true for long tasks - reduction rule)

def parse_3pm_file(input_file):
    """
    Parse the 3PM problem instance file.
    
    The file format:
    - Lines starting with 'c' are comments
    - First line: n m c (number of tasks, workstations, cycle time)
    - Next n lines: t w (processing time and power consumption for each task)
    - Remaining lines: i,j (precedence relations, terminated by -1,-1)
    
    Args:
        input_file: path to the 3PM instance file
    
    Returns:
        n: number of tasks
        m: number of workstations
        c: cycle time
        T: list of processing times (T[0] is dummy, T[1..n] are actual tasks)
        W: list of power consumption values (W[0] is dummy, W[1..n] are actual tasks)
        precedence_relations: list of (i,j) pairs indicating i must precede j
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
# Automatically assigns unique IDs to variables
vpool = IDPool(start_from=1)

# Boolean variable definitions for PBO-I formulation:
# X(j,k): task j assigned to workstation k (Eq. 2)
X = lambda j, k: vpool.id('X{0}@{1}'.format(j, k))

# S(j,t): task j starts at time t (Eq. 4)
S = lambda j, t: vpool.id('S{0}@{1}'.format(j, t))

# A(j,t): task j is active at time t (used in Eq. 7 and Eq. 8)
A = lambda j, t: vpool.id('A{0}@{1}'.format(j, t))

# E(i): unary encoding variable for objective (power peak)
# E(0) + E(1) + ... + E(ub) represents the power peak value
# This is the inaugural formulation using unary encoding (same as MSAT-I)
E = lambda j: vpool.id('E{0}'.format(j))

def get_single_machine_time(ealiest_st_time, T):
    """
    Calculate the makespan for a single machine scheduling problem.
    
    Args:
        ealiest_st_time: list of earliest start times for tasks
        T: list of processing times for tasks
    
    Returns:
        C_max: the makespan (maximum completion time)
    """
    C_max = 0
    st_T_pair = sorted(list(zip(ealiest_st_time, T)))
    for r, t in st_T_pair:
        C_max = max(C_max, r) + t
    return C_max


def get_precedence_constraints(pbo, n, m, c, T, W, precedence_relations):
    """
    Generate precedence constraints and reduction rules for the PBO-I formulation.
    
    This function computes the earliest and latest possible workstation assignments
    for each task based on precedence relations, then adds reduction constraints
    to eliminate impossible assignments.
    
    Implements reduction rules to prune the search space:
    - Tasks cannot be assigned to workstations before their predecessors complete
    - Tasks cannot be assigned to workstations after their successors must start
    
    Args:
        pbo: PBOWriter instance
        n: number of tasks
        m: number of workstations
        c: cycle time (capacity of each workstation)
        T: list of processing times (T[0] is dummy, T[1..n] are actual tasks)
        W: list of power consumption values
        precedence_relations: list of (i,j) pairs indicating i must precede j
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

    for i, j in precedence_relations:
        pre_list[j].append(i)
        suc_list[i].append(j)
        in_degree[j] += 1
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




    for i in range(1, n + 1):
        impossible_station_l = tau_list[i] // c
        for j in range(1, impossible_station_l + 1):
            pbo.add_clause([-X(i, j)])
            neg_X[X(i, j)] = 1
        assert impossible_station_l < m
        l_slot = tau_list[i] - c * (impossible_station_l)
        for t in range(l_slot):
            pbo.add_clause([-X(i, impossible_station_l + 1), -S(i, t)])
            neg_XS_pair[(X(i, impossible_station_l + 1), S(i, t))] = 1

        tau_r_list[i] += T[i]-1
        impossible_station_r = tau_r_list[i] // c
        for j in range(1, impossible_station_r + 1):
            pbo.add_clause([-X(i, m - j + 1)])
            neg_X[X(i, m-j+1)] = 1
        assert impossible_station_r < m
        r_slot = tau_r_list[i] - c * (impossible_station_r)
        for t in range(1, r_slot + 1):
            pbo.add_clause([-X(i, m - impossible_station_r), -S(i, c - t)])
            neg_XS_pair[(X(i, m - impossible_station_r), S(i, c - t))]=1

    return


def get_longTask_constraints(pbo, n, m, c, T, W, precedence_relations):
    """
    Generate reduction rules for long tasks.
    
    For long tasks (tasks where T[i] > c/2), certain time slots are always active
    regardless of the start time. This function identifies these time slots and
    sets the corresponding A[j,t] variables to true, reducing the number of variables.
    
    Reduction rule: If T[i] > c/2, then task i must be active at time slots
    from (c - T[i]) to (T[i] - 1), regardless of when it starts.
    
    Args:
        pbo: PBOWriter instance
        n: number of tasks
        m: number of workstations
        c: cycle time
        T: list of processing times
        W: list of power consumption values
        precedence_relations: list of precedence constraints
    """
    for i in range(1, n + 1):
        # Determine the range of time slots that are always active for task i
        l = c - T[i]
        r = T[i] - 1
        if l > r:
            continue

        # For long tasks, these time slots are always active
        for t in range(l, r + 1):
            pos_A[A(i, t)] = 1
            pbo.add_clause([A(i, t)])

    return

def get_wcnf_insatance(pbo, n, m, c, T, W, precedence_relations, vpool, ub, lb):


    var = []
    coef = []
    for i in range(0, ub + 1):
        # wcnf.append([-E(i)], weight=2 ** i)
        var.append(E(i))
        coef.append(1)
    pbo.set_objective(coef, var)

    # Eq. (2): Task assignment constraint
    # Each task must be assigned to exactly one workstation
    for j in range(1, n + 1):
        lits = [X(j, k) for k in range(1, m + 1) if X(j, k) not in neg_X]
        coef = [1] * len(lits)
        pbo.add_constraint(coef, lits, "=", 1)

    # Eq. (4): Start time selection constraint
    # Each task must have exactly one start time
    for j in range(1, n + 1):
        lits = [S(j, t) for t in range(0, c - T[j] + 1)]
        coef = [1] * len(lits)
        pbo.add_constraint(coef, lits, "=", 1)

    # Workstation capacity constraint
    # Tasks assigned to the same workstation have the sum of their processing times bounded by c
    for k in range(1, m + 1):
        lits = []
        weight = []
        for j in range(1, n + 1):
            if X(j, k) in neg_X:
                continue
            lits.append(X(j, k))
            weight.append(T[j])
        pbo.add_constraint(weight, lits, "<=", c)

    # Eq. (7): Non-overlap constraint
    # Two tasks on the same workstation cannot be active at the same time
    for j in range(1, n + 1):
        for k in range(1, m + 1):
            for i in range(1, j):
                for t in range(0, c):
                    if X(i, k) not in neg_X and X(j, k) not in neg_X:
                        # If tasks i and j are both on workstation k, they cannot both be active at time t
                        pbo.add_clause([-X(i, k), -X(j, k), -A(i, t), -A(j, t)])  # Eq. (7)

    # Eq. (5) and (6): Start time and activity constraints
    # Relate start time S[j,t] to activity A[j,t]
    for j in range(1, n + 1):
        for t in range(0, c - T[j] + 1):
            # If task j starts at time t, it must be active during [t, t+T[j])
            for t_prime in range(c):
                if t_prime >= t and t_prime - t < T[j]:
                    if A(j, t_prime) not in pos_A:
                        pbo.add_clause([-S(j, t), A(j, t_prime)])
                else:
                    pbo.add_clause([-S(j, t), -A(j, t_prime)])
        
        # Eq. (6): Invalid start times (task would exceed cycle time)
        for t in range(c - T[j] + 1, c):
            pbo.add_clause([-S(j, t)])

    # Eq. (3): Precedence constraint
    # If task i must precede task j, then task j cannot be assigned to a workstation
    # before task i, and the start times must respect the precedence order
    for i, j in precedence_relations:
        for k in range(1, m + 1):
            bound = k
            lits = [X(j, k)] if X(j, k) not in neg_X else []
            for h in range(1, k + 1):
                if X(i, h) in neg_X:
                    bound -= 1
                    continue
                lits.append(-X(i, h))
            # wcnf.extend(
            #     card.CardEnc.atmost(
            #         lits=lits,
            #         bound=bound,
            #         encoding=card_encoding, vpool=vpool
            #     )
            # )
            coef = [1] * len(lits)
            pbo.add_constraint(coef, lits, "<=", bound)
            for t in range(0, c - T[j] + 1):
                    S_lits = [-S(i, tau) for tau in range(0, t-T[i]+1)]
                    # wcnf.extend(
                    #     card.CardEnc.atmost(
                    #         lits = [S(j,t), X(i, k), X(j,k)] + S_lits,
                    #         bound = 2 + len(S_lits),
                    #         encoding=card_encoding, vpool=vpool
                    #     )
                    # )
                    lits = [S(j,t), X(i, k), X(j,k)] + S_lits
                    coef = [1] * len(lits)
                    pbo.add_constraint(coef, lits, "<=", 2 + len(S_lits))




    """ new precedence relations """

    for i in range(1, lb + 1):
        pbo.add_clause([E(i)])


    for i in range(2, ub + 1):
        pbo.add_clause([-E(i), E(i - 1)])


    for t in range(c):
        lits = [A(j, t) for j in range(1, 1 + n)] + [-E(x) for x in range(1, ub + 1)]
        weights = [W[j] for j in range(1, 1 + n)] + [1] * ub
        # wcnf.extend(PBEnc.leq(lits=lits, weights=weights, bound=ub, vpool=vpool, encoding=PB_encoding))
        pbo.add_constraint(weights, lits, "<=", ub)
    return


def merge_wcnf(wcnf1, wcnf2):
    """
    Merge two WCNF instances.
    
    Combines the hard and soft clauses from wcnf2 into wcnf1.
    
    Args:
        wcnf1: target WCNF instance
        wcnf2: source WCNF instance to merge from
    
    Returns:
        wcnf1: the merged WCNF instance
    """
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
    n, m, c, T, W, precedence_relations = parse_3pm_file(input_file)
    
    # Compute lower and upper bounds for power peak
    lb = min(W[1:])  # Lower bound: minimum power consumption
    ub = sum(sorted(W[1:], reverse=True)[:min(m, len(W) - 1)])  # Upper bound: sum of m largest powers
    print("lb:{0} ub:{1}".format(lb, ub))
    
    # Build PBO instance with inaugural formulation
    pbo = PBOWriter()
    get_precedence_constraints(pbo, n, m, c, T, W, precedence_relations)
    get_longTask_constraints(pbo, n, m, c, T, W, precedence_relations)
    get_wcnf_insatance(pbo, n, m, c, T, W, precedence_relations, vpool, ub, lb)

    solve_start_time = time.time()
    print(f"$$$ TimeEncoding: {solve_start_time - start_time}")
    # print(f"### nb_var {wcnf.nv} nb_cons {len(wcnf.hard)+len(wcnf.soft)}")
    pbo.write_to_file(output_path)