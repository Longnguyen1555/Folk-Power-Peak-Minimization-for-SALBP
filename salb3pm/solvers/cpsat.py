"""Direct interval/Boolean OR-Tools CP-SAT model."""

import time
from ..model import Instance, Schedule
from ..results import SolveResult, normalized_objective, _finish, _record, publish


def solve_cpsat(
    instance: Instance, *, encoding="staircase", objective="peak", time_limit=60.0
):
    started = time.monotonic()
    objective = normalized_objective(objective)
    result = SolveResult(
        "cpsat", "native", objective, "UNKNOWN", 0, backend="ortools:CP-SAT"
    )
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        result.status = "UNAVAILABLE"
        result.message = "Install ortools to run CP-SAT"
        return _finish(result, started)
    ins = instance
    model = cp_model.CpModel()
    n, m, c = ins.n, ins.stations, ins.cycle
    station = [model.NewIntVar(0, m - 1, f"station_{i}") for i in range(n)]
    start = [model.NewIntVar(0, c - ins.durations[i], f"start_{i}") for i in range(n)]
    end = [model.NewIntVar(ins.durations[i], c, f"end_{i}") for i in range(n)]
    intervals = []
    assigned = {}
    active = {}
    for i in range(n):
        model.Add(end[i] == start[i] + ins.durations[i])
        for k in range(m):
            b = model.NewBoolVar(f"assigned_{i}_{k}")
            assigned[i, k] = b
            model.Add(station[i] == k).OnlyEnforceIf(b)
            model.Add(station[i] != k).OnlyEnforceIf(b.Not())
            intervals.append(
                (
                    k,
                    model.NewOptionalIntervalVar(
                        start[i], ins.durations[i], end[i], b, f"int_{i}_{k}"
                    ),
                )
            )
        model.AddExactlyOne(assigned[i, k] for k in range(m))
        for t in range(c):
            # Reify exact activity through the task's discrete start-choice literals.
            active[i, t] = model.NewBoolVar(f"active_{i}_{t}")
    for k in range(m):
        model.AddNoOverlap(item for k2, item in intervals if k2 == k)
    for i, j in ins.precedence:
        model.Add(station[i] <= station[j])
        same = model.NewBoolVar(f"same_station_{i}_{j}")
        model.Add(station[i] == station[j]).OnlyEnforceIf(same)
        model.Add(station[i] != station[j]).OnlyEnforceIf(same.Not())
        model.Add(end[i] <= start[j]).OnlyEnforceIf(same)
    # Include complete power profiles (not simply per-station energy sums).
    starts = {}
    for i in range(n):
        terms = []
        for s in range(c - ins.durations[i] + 1):
            b = model.NewBoolVar(f"task_{i}_starts_{s}")
            model.Add(start[i] == s).OnlyEnforceIf(b)
            model.Add(start[i] != s).OnlyEnforceIf(b.Not())
            starts[i, s] = b
            terms.append(b)
        model.AddExactlyOne(terms)
        for t in range(c):
            covers = [
                starts[i, s]
                for s in range(c - ins.durations[i] + 1)
                if s <= t < s + ins.durations[i]
            ]
            model.Add(active[i, t] == sum(covers))
    peak = model.NewIntVar(ins.peak_lower_bound, ins.peak_upper_bound, "power_peak")
    for t in range(c):
        model.Add(sum(ins.powers[i] * active[i, t] for i in range(n)) <= peak)
    if objective == "station_peak_sum":
        station_peaks = [
            model.NewIntVar(0, max(ins.powers), f"station_peak_{k}") for k in range(m)
        ]
        for i in range(n):
            for k in range(m):
                model.Add(station_peaks[k] >= ins.powers[i]).OnlyEnforceIf(
                    assigned[i, k]
                )
        model.Minimize(sum(station_peaks))
    elif objective == "total_energy":
        model.Minimize(ins.total_energy)
    else:
        model.Minimize(peak)
    solver = cp_model.CpSolver()
    result.model_variables = len(model.Proto().variables)
    result.model_constraints = len(model.Proto().constraints)
    publish(result)
    remaining = float(time_limit) - (time.monotonic() - started)
    if remaining <= 0:
        result.status = "TIMEOUT"
        return _finish(result, started)
    result.solver_instances = 1
    solver.parameters.max_time_in_seconds = remaining
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    result.iterations = 1
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        sched = Schedule(
            tuple(solver.Value(x) for x in station),
            tuple(solver.Value(x) for x in start),
        )
        _record(result, ins, sched)
    if status == cp_model.OPTIMAL:
        result.status = "OPTIMAL"
        result.proof = "OR-Tools CP-SAT optimum"
    elif status == cp_model.INFEASIBLE:
        result.status = "INFEASIBLE"
        result.proof = "OR-Tools CP-SAT infeasibility"
    elif status == cp_model.FEASIBLE:
        result.status = "TIMEOUT"
        result.message = "Feasible incumbent; no optimality certificate"
    else:
        result.status = "TIMEOUT" if status == cp_model.UNKNOWN else "UNKNOWN"
        result.message = f"CP-SAT status {solver.StatusName(status)}"
    return _finish(result, started)
