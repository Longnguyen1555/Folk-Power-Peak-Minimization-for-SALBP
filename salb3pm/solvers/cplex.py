"""Direct .3pm CPLEX MIP using the same coefficient model as Gurobi."""

import time

from ..results import SolveResult, _finish, _record, publish
from .mip import TimeIndexedMIP


def solve_cplex(instance, *, encoding="staircase", objective="peak", time_limit=60.0):
    started = time.monotonic()
    result = SolveResult(
        "cplex", "native", objective, "UNKNOWN", 0, backend="cplex:MIP"
    )
    try:
        import cplex
    except ImportError:
        result.status = "UNAVAILABLE"
        result.message = "Install cplex and configure a usable IBM CPLEX license"
        return _finish(result, started)
    try:
        model = TimeIndexedMIP(instance, objective)
        with cplex.Cplex() as solver:
            for stream in ("log", "error", "warning", "results"):
                getattr(solver, f"set_{stream}_stream")(None)
            result.solver_instances = 1
            solver.parameters.threads.set(1)
            solver.parameters.clocktype.set(2)  # wall clock
            solver.parameters.mip.tolerances.mipgap.set(0)
            solver.parameters.mip.tolerances.absmipgap.set(0)
            solver.variables.add(
                obj=[v.cost for v in model.variables],
                lb=[v.lower for v in model.variables],
                ub=[v.upper for v in model.variables],
                types="".join(v.kind for v in model.variables),
                names=[v.name for v in model.variables],
            )
            solver.objective.set_offset(model.offset)
            batch = []

            def flush():
                if batch:
                    solver.linear_constraints.add(
                        lin_expr=[
                            cplex.SparsePair(ind=list(row), val=list(row.values()))
                            for row, _, _ in batch
                        ],
                        senses="".join(sense for _, sense, _ in batch),
                        rhs=[rhs for _, _, rhs in batch],
                    )
                    batch.clear()

            for row in model.rows():
                batch.append(row)
                if len(batch) >= 256:
                    flush()
            flush()
            result.model_variables = solver.variables.get_num()
            result.model_constraints = solver.linear_constraints.get_num()
            publish(result)
            remaining = time_limit - (time.monotonic() - started)
            if remaining <= 0:
                result.status = "TIMEOUT"
                return _finish(result, started)
            solver.parameters.timelimit.set(remaining)
            solver.solve()
            result.iterations = 1
            if solver.solution.is_primal_feasible():
                _record(result, instance, model.decode(solver.solution.get_values()))
            status = solver.solution.get_status()
            codes = solver.solution.status
            if status in (codes.MIP_optimal, codes.optimal_tolerance):
                result.status = "OPTIMAL"
                result.proof = "CPLEX MIP optimum certificate"
            elif status == codes.MIP_infeasible:
                result.status = "INFEASIBLE"
                result.proof = "CPLEX MIP infeasibility certificate"
            elif status in (
                codes.MIP_time_limit_feasible,
                codes.MIP_time_limit_infeasible,
            ):
                result.status = "TIMEOUT"
            else:
                result.message = f"CPLEX status: {solver.solution.get_status_string()}"
    except cplex.exceptions.CplexError as exc:
        result.status = "UNAVAILABLE"
        result.message = f"CPLEX environment/license error: {exc}"
    return _finish(result, started)
