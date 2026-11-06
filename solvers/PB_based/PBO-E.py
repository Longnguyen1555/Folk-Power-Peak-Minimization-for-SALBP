"""
Pseudoboolean Enhanced formulation (PBO-E) for the 3-PM problem.

This implementation uses an enhanced objective function with binary encoding
to minimize the power peak in the three-stage parallel machine scheduling problem.

Key Features:
- Enhanced objective using binary encoding (same as MSAT-E formulation)
- Pseudo-Boolean constraints for compact representation
- Reduction rules to minimize variable count

Reference: See paper for Eq. (1)-(8) detailed formulations
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
from math import ceil, floor
import argparse

# Encoding types for cardinality and pseudo-Boolean constraints
card_encoding = card.EncType.cardnetwrk
PB_encoding = EncType.best

class PBOWriter:
    """
    Writer for Pseudo-Boolean Optimization (PBO) instances.
    
    This class constructs PBO constraints and objectives in the OPB format,
    which is the standard input format for pseudo-Boolean solvers.
    """
    
    def __init__(self):
        self.variables = {"Happy":0}
        self.objective = ""
        self.constraints = []

    def get_internal_lit(self, lit_name):
        """Convert literal name to internal variable representation."""
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
        """
        Set the objective function to minimize or maximize.
        
        Args:
            coeffs: List of coefficients for each variable
            vars: List of variable identifiers
            minimize: If True, minimize the objective; otherwise maximize
        """
        assert minimize == True
        terms = []
        for c, v in zip(coeffs, vars):
            if c >= 0:
                terms.append(f"+{c} {self.get_internal_lit(v)}")
            else:
                terms.append(f"{c} {self.get_internal_lit(v)}")
        self.objective = f"{'min' if minimize else 'max'}: {' '.join(terms)};"

    def add_clause(self, vars):
        """Add a clause as a pseudo-Boolean constraint (sum >= 1)."""
        op = ">="
        rhs = 1
        coeffs = [1] * len(vars)
        assert op == ">=" or op == "="
        self.add_constraint(coeffs, vars, op, rhs)

    def add_constraint(self, coeffs, vars, op, rhs):
        """
        Add a pseudo-Boolean constraint.
        
        Args:
            coeffs: List of coefficients
            vars: List of variables
            op: Operator (">=", "=", or "<=")
            rhs: Right-hand side value
        """
        assert op == ">=" or op == "=" or op=="<="
        if op == "<=":
            coeffs = [-c for c in coeffs]
            rhs = -rhs
            op = ">="
        # Format constraint
        terms = []
        for c, v in zip(coeffs, vars):
            if c >= 0:
                terms.append(f"+{c} {self.get_internal_lit(v)}")
            else:
                terms.append(f"{c} {self.get_internal_lit(v)}")
        self.constraints.append(f"{' '.join(terms)} {op} {rhs};")

    def write_to_file(self, filename):
        """Write the PBO instance to a file in OPB format."""
        with open(filename, 'w') as f:
            f.write(f"* #variable= {len(self.variables)}\n")
            f.write(f"* #constraints= {len(self.constraints)}\n")
            f.write(self.objective + "\n")
            for constraint in self.constraints:
                f.write(constraint + "\n")

neg_X = {}  # Track negated X[j,k] variables (impossible task assignments)
neg_XS_pair = {}  # Track negated X[j,k] and S[j,t] pairs
pos_A = {}  # Track A[j,t] variables that are always true for long tasks

def parse_3pm_file(input_file):
    """
    Parse the 3-PM problem instance from a file.
    
    File format:
    - Line 1: n m c (number of tasks, workstations, and cycle time)
    - Lines 2 to n+1: t_i w_i (processing time and power consumption for each task)
    - Remaining lines: i,j (precedence relations, ending with -1,-1)
    
    Args:
        input_file: Path to the input file
        
    Returns:
        n: Number of tasks
        m: Number of workstations
        c: Cycle time
        T: List of processing times (indexed from 1)
        W: List of power consumptions (indexed from 1)
        precedence_relations: List of (i,j) pairs where task i precedes task j
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


vpool = IDPool(start_from=1)
X = lambda j, k: vpool.id('X{0}@{1}'.format(j, k))
S = lambda j, t: vpool.id('S{0}@{1}'.format(j, t))
A = lambda j, t: vpool.id('A{0}@{1}'.format(j, t))
E = lambda j: vpool.id('E{0}'.format(j))

def get_single_machine_time(ealiest_st_time, T):
    """
    Calculate the makespan for a single machine scheduling problem.
    
    Args:
        ealiest_st_time: List of earliest start times for each task
        T: List of processing times
        
    Returns:
        The makespan (maximum completion time)
    """
    C_max = 0
    st_T_pair = sorted(list(zip(ealiest_st_time, T)))
    for r, t in st_T_pair:
        C_max = max(C_max, r) + t
    return C_max


def get_precedence_constraints(pbo, n, m, c, T, W, precedence_relations):
    """
    Generate precedence-based reduction constraints to eliminate impossible assignments.
    
    This function computes the earliest and latest possible start times for each task
    based on precedence relations, and adds constraints to eliminate impossible
    task-workstation assignments.
    
    Args:
        pbo: PBOWriter instance
        n: Number of tasks
        m: Number of workstations
        c: Cycle time
        T: Processing times
        W: Power consumptions
        precedence_relations: List of (i,j) precedence pairs
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
        
    # Topological sorting
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

    # Forward pass: compute earliest possible workstation (tau)
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

    # Backward pass: compute latest possible workstation (tau_r)
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
            pbo.add_clause([-X(i, j)])
            neg_X[X(i, j)] = 1
        assert impossible_station_l < m
        l_slot = tau_list[i] - c * (impossible_station_l)
        for t in range(l_slot):
            pbo.add_clause([-X(i, impossible_station_l + 1), -S(i, t)])
            neg_XS_pair[(X(i, impossible_station_l + 1), S(i, t))] = 1

        # Right side: eliminate workstations after latest possible
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
    Generate reduction constraints for long tasks.
    
    For long tasks, certain time slots are always active, reducing the number of A[j,t] variables.
    This is part of the reduction rules to minimize variable count.
    
    Args:
        pbo: PBOWriter instance
        n: Number of tasks
        m: Number of workstations
        c: Cycle time
        T: Processing times
        W: Power consumptions
        precedence_relations: List of (i,j) precedence pairs
    """
    for i in range(1, n + 1):
        l = c - T[i]
        r = T[i] - 1
        if l > r:
            continue

        # For tasks that span most of the cycle, certain time slots are always active
        for t in range(l, r + 1):
            pos_A[A(i, t)] = 1
            pbo.add_clause([A(i, t)])

    return


def get_wcnf_insatance(pbo, n, m, c, T, W, precedence_relations, vpool, ub, lb):
    """
    Generate the complete PBO instance with all constraints.
    
    This function adds all the constraints from the paper:
    - Eq. (2): Each task assigned to exactly one workstation
    - Eq. (3): Precedence constraints
    - Eq. (4): Each task has exactly one start time
    - Eq. (5)-(6): Link between start time and active time
    - Eq. (7): No overlap on same workstation
    - Eq. (8): Power peak constraint with binary encoding
    
    Enhanced objective uses binary encoding (same as MSAT-E formulation).
    
    Args:
        pbo: PBOWriter instance
        n: Number of tasks
        m: Number of workstations
        c: Cycle time
        T: Processing times
        W: Power consumptions
        precedence_relations: List of (i,j) precedence pairs
        vpool: Variable pool
        ub: Upper bound on power peak
        lb: Lower bound on power peak
    """
    # Enhanced objective: binary encoding with E[0..nb_E-1] variables
    # nb_E = ceil(log2(ub+1)) bits needed to represent power peak
    nb_E = ceil(log2(ub + 1))

    var = []
    coef = []
    for i in range(0, nb_E + 1):
        var.append(E(i))
        coef.append(2 ** i)
    pbo.set_objective(coef, var)

    # Eq. (2): Tasks assigned to the same workstation have the sum of their processing times bounded by c
    for k in range(1, m + 1):
        lits = []
        weight = []
        for j in range(1, n + 1):
            if X(j, k) in neg_X:
                continue
            lits.append(X(j, k))
            weight.append(T[j])
        pbo.add_constraint(weight, lits, "<=", c)

    for j in range(1, n + 1):
        # Eq. (2): Each task assigned to exactly one workstation
        lits = [X(j, k) for k in range(1, m + 1) if X(j, k) not in neg_X]
        coef = [1] * len(lits)
        pbo.add_constraint(coef, lits, "=", 1)
        
        # Eq. (4)-(5): Each task has exactly one start time
        lits = [S(j, t) for t in range(0, c - T[j] + 1)]
        coef = [1] * len(lits)
        pbo.add_constraint(coef, lits, "=", 1)

        for k in range(1, m + 1):
            # Eq. (7): No overlap on same workstation - tasks cannot overlap in time
            for i in range(1, j):
                for t in range(0, c):
                    if X(i, k) not in neg_X and X(j, k) not in neg_X:
                        pbo.add_clause([-X(i, k), -X(j, k), -A(i, t), -A(j, t)])  # Eq. (7)

        # Eq. (5)-(6): Link between start time and active time
        for t in range(0, c - T[j] + 1):
            for t_prime in range(c):
                if t_prime >= t and t_prime - t < T[j]:
                    if A(j, t_prime) not in pos_A:
                        pbo.add_clause([-S(j, t), A(j, t_prime)])
                else:
                    pbo.add_clause([-S(j, t), -A(j, t_prime)])
        for t in range(c - T[j] + 1, c):
            pbo.add_clause([-S(j, t)])  # Eq. (6)

    # Eq. (3): Precedence constraints with enhanced formulation
    for i, j in precedence_relations:
        for k in range(1, m + 1):
            bound = k
            lits = [X(j, k)] if X(j, k) not in neg_X else []
            for h in range(1, k + 1):
                if X(i, h) in neg_X:
                    bound -= 1
                    continue
                lits.append(-X(i, h))
            coef = [1] * len(lits)
            pbo.add_constraint(coef, lits, "<=", bound)
            
            # Additional precedence constraints with time ordering
            for t in range(0, c - T[j] + 1):
                S_lits = [-S(i, tau) for tau in range(0, t-T[i]+1)]
                lits = [S(j,t), X(i, k), X(j,k)] + S_lits
                coef = [1] * len(lits)
                pbo.add_constraint(coef, lits, "<=", 2 + len(S_lits))

    # Lower bound: binary value must be >= lb
    lits = [E(x) for x in range(nb_E + 1)]
    weights = [2 ** x for x in range(nb_E + 1)]
    pbo.add_constraint(weights, lits, ">=", lb)

    # Eq. (8): Power peak constraint with binary encoding
    # At any time t, sum of power <= binary value represented by E bits
    l_ub = sum([2 ** i for i in range(nb_E + 1)])
    for t in range(c):
        lits = [A(j, t) for j in range(1, 1 + n)] + [-E(x) for x in range(nb_E + 1)]
        weights = [W[j] for j in range(1, 1 + n)] + [2 ** x for x in range(nb_E + 1)]
        pbo.add_constraint(weights, lits, "<=", l_ub)

    return


if __name__ == '__main__':
    """
    Main entry point for the PBO-E solver.
    
    Usage: python PBO-E.py <input_file> <output_file>
    
    Args:
        input_file: Path to the 3-PM problem instance file
        output_file: Path to write the PBO instance file
    """
    parser = argparse.ArgumentParser(description="python this.py <path/to/3pm> <path/to/wcnf_old>")
    parser.add_argument("input_path", help="path/to/3pm")
    parser.add_argument("output_path", help="path/to/wcnf_old")
    parser.add_argument("--objective", choices=("peak", "total_power", "total_energy", "peak_then_total_power", "peak_then_total_energy"), default="peak",
                        help="total_power/total_energy are constant for a fixed SALB3PM instance")
    args = parser.parse_args()
    input_file = args.input_path
    output_path = args.output_path

    start_time = time.time()
    
    # Parse the 3-PM instance
    n, m, c, T, W, precedence_relations = parse_3pm_file(input_file)
    
    # Compute lower and upper bounds for power peak
    lb = min(W[1:])
    ub = sum(sorted(W[1:], reverse=True)[:min(m, len(W) - 1)])
    print("lb:{0} ub:{1}".format(lb, ub))
    
    # Build PBO instance with enhanced formulation
    pbo = PBOWriter()
    get_precedence_constraints(pbo, n, m, c, T, W, precedence_relations)
    get_longTask_constraints(pbo, n, m, c, T, W, precedence_relations)
    get_wcnf_insatance(pbo, n, m, c, T, W, precedence_relations, vpool, ub, lb)

    solve_start_time = time.time()
    print(f"$$$ TimeEncoding: {solve_start_time - start_time}")
    
    # Write the PBO instance to file
    if args.objective in ("total_power", "total_energy"):
        # Every feasible schedule executes every task once. As an OPB objective,
        # represent the constant cost with one forced-true variable.
        fixed_name = "TOTAL_ENERGY_FIXED"
        pbo.add_clause([fixed_name])
        pbo.set_objective([sum(T[j]*W[j] for j in range(1, n+1))], [fixed_name])
    pbo.write_to_file(output_path)
# Schedule-invariant metric for reporting alongside original OPB output.
# PB files model peak; this number is NOT claimed to be an optimized energy saving.
if __name__ == "__main__":
    print(f"### TotalEnergy {sum(T[j]*W[j] for j in range(1,n+1))} "
          f"TotalTaskPower {sum(W[1:])}")
