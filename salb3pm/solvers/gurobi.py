"""Direct .3pm Gurobi MIP, sharing its coefficients with CPLEX."""

import time

from ..results import SolveResult, _finish, _record, publish
from .mip import TimeIndexedMIP


def solve_gurobi(instance, *, encoding="staircase", objective="peak", time_limit=60.0):
    started = time.monotonic()
    result = SolveResult(
        "gurobi", "native", objective, "UNKNOWN", 0, backend="gurobipy:MIP"
    )
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError:
        result.status = "UNAVAILABLE"
        result.message = "Install gurobipy and configure a usable Gurobi license"
        return _finish(result, started)
    try:
        model = TimeIndexedMIP(instance, objective)
        with gp.Env(empty=True) as env:
            env.setParam("OutputFlag", 0)
            env.start()
            with gp.Model("SALB3PM", env=env) as solver:
                result.solver_instances = 1
                solver.Params.Threads = 1
                solver.Params.MIPGap = 0
                solver.Params.MIPGapAbs = 0
                variables = [
                    solver.addVar(lb=v.lower, ub=v.upper, vtype=v.kind, name=v.name)
                    for v in model.variables
                ]
                for row, sense, rhs in model.rows():
                    expression = gp.LinExpr(
                        list(row.values()), [variables[i] for i in row]
                    )
                    solver.addConstr(
                        expression == rhs if sense == "E" else expression <= rhs
                    )
                solver.setObjective(
                    gp.quicksum(
                        v.cost * variables[i] for i, v in enumerate(model.variables)
                    )
                    + model.offset,
                    GRB.MINIMIZE,
                )
                solver.update()
                result.model_variables = solver.NumVars
                result.model_constraints = solver.NumConstrs
                publish(result)
                remaining = time_limit - (time.monotonic() - started)
                if remaining <= 0:
                    result.status = "TIMEOUT"
                    return _finish(result, started)
                solver.Params.TimeLimit = remaining
                solver.optimize()
                result.iterations = 1
                if solver.SolCount:
                    _record(result, instance, model.decode([v.X for v in variables]))
                if solver.Status == GRB.OPTIMAL:
                    result.status = "OPTIMAL"
                    result.proof = "Gurobi MIP optimum certificate"
                elif solver.Status == GRB.INFEASIBLE:
                    result.status = "INFEASIBLE"
                    result.proof = "Gurobi MIP infeasibility certificate"
                elif solver.Status == GRB.TIME_LIMIT:
                    result.status = "TIMEOUT"
                else:
                    result.message = f"Gurobi status code: {solver.Status}"
    except gp.GurobiError as exc:
        result.status = "UNAVAILABLE"
        result.message = f"Gurobi environment/license error: {exc}"
    return _finish(result, started)
