"""Public dispatcher; implementations live in one module per solver family."""

from ..model import Instance
from ..results import METHODS, OBJECTIVES, SolveResult, normalized_objective
from .sat import solve_sat, solve_binary_sat
from .maxsat import solve_maxsat
from .gurobi import solve_gurobi
from .cplex import solve_cplex
from .pb import solve_pb
from .cpsat import solve_cpsat


def solve(
    instance: Instance,
    *,
    method="incremental_sat",
    encoding="staircase",
    objective="peak",
    time_limit=60.0,
):
    if time_limit <= 0:
        raise ValueError("time_limit must be positive")
    if objective not in OBJECTIVES:
        raise ValueError(objective)
    objective = normalized_objective(objective)
    if method in ("multiple_sat", "incremental_sat", "binary_sat", "paper_cuts"):
        return solve_sat(
            instance,
            method=method,
            encoding=encoding,
            objective=objective,
            time_limit=time_limit,
        )
    if method == "maxsat":
        return solve_maxsat(
            instance, encoding=encoding, objective=objective, time_limit=time_limit
        )
    if method == "gurobi":
        return solve_gurobi(
            instance, encoding=encoding, objective=objective, time_limit=time_limit
        )
    if method == "cpsat":
        return solve_cpsat(
            instance, encoding=encoding, objective=objective, time_limit=time_limit
        )
    if method == "cplex":
        return solve_cplex(
            instance, encoding=encoding, objective=objective, time_limit=time_limit
        )
    if method == "pb":
        return solve_pb(
            instance, encoding=encoding, objective=objective, time_limit=time_limit
        )
    raise ValueError(f"Unknown method {method}")
