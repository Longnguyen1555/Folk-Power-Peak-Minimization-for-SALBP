"""Descending Multiple/Incremental SAT, binary search, and paper cuts."""

import time
from ..model import Instance, validate
from ..cnf import encode, station_peak_bank, binary_objective_bank
from ..backends import SATBackend
from ..results import (
    SolveResult,
    OBJECTIVES,
    normalized_objective,
    _finish,
    _record,
    publish,
)


def solve_sat(
    instance: Instance,
    *,
    method="incremental_sat",
    encoding="staircase",
    objective="peak",
    time_limit=60.0
):
    if method not in ("multiple_sat", "incremental_sat", "binary_sat", "paper_cuts"):
        raise ValueError(method)
    objective = normalized_objective(objective)
    if objective not in OBJECTIVES:
        raise ValueError(objective)
    started = time.monotonic()
    deadline = started + time_limit
    if method == "binary_sat":
        return solve_binary_sat(
            instance, encoding=encoding, objective=objective, time_limit=time_limit
        )
    if method == "paper_cuts" and objective == "station_peak_sum":
        raise ValueError("paper_cuts is a literature-specific power-peak method")
    base = encode(instance, encoding)
    station_bank = station_peak_bank(base) if objective == "station_peak_sum" else None
    objective_bank = (
        binary_objective_bank(base, station_bank)
        if method != "paper_cuts" and objective != "total_energy"
        else None
    )
    r = SolveResult(
        method,
        encoding,
        objective,
        "UNKNOWN",
        0,
        cnf_vars=base.formula.pool.top,
        cnf_clauses=len(base.formula.clauses),
        cnf_peak_clauses=len(base.formula.clauses),
    )
    loaded_clauses = len(base.formula.clauses)
    backend = SATBackend(base.formula.clauses)
    r.solver_instances += 1
    r.backend = backend.name
    publish(r)
    try:
        answer = backend.solve(deadline)
        r.iterations += 1
        if answer is None:
            r.status = "TIMEOUT"
            return _finish(r, started)
        if not answer:
            r.status = "INFEASIBLE"
            r.proof = "UNSAT of base feasibility CNF"
            return _finish(r, started)
        current_schedule = base.decode(backend.get_model())
        current_metrics = validate(instance, current_schedule)
        _record(r, instance, current_schedule)
        if objective == "total_energy":
            r.status = "OPTIMAL"
            r.proof = "All schedules have the same sum_i duration_i * power_i"
            return _finish(r, started)
        metric_name = "station_peak_sum" if station_bank else "power_peak"
        if r.metrics[metric_name] == instance.peak_lower_bound:
            r.status = "OPTIMAL"
            r.proof = "Feasible solution achieves unconditional max-task-power LB"
            return _finish(r, started)
        best = r.metrics[metric_name]
        while True:
            if time.monotonic() >= deadline:
                r.status = "TIMEOUT"
                break
            if method == "multiple_sat":
                # Rebuild the complete decision problem, including the objective
                # circuit, and instantiate a fresh solver for every tighter bound.
                backend.close()
                backend = None
                base = encode(instance, encoding)
                station_bank = (
                    station_peak_bank(base) if objective == "station_peak_sum" else None
                )
                objective_bank = binary_objective_bank(base, station_bank)
                r.cnf_clauses += len(base.formula.clauses)
            if method == "paper_cuts":
                # The original SAT paper forbids a set of simultaneously active
                # tasks with total power >= current incumbent for every slot.
                # Each cut is valid for all schedules that strictly beat incumbent.
                active_sets = set()
                for t, load in enumerate(current_metrics["power_profile"]):
                    if load < best:
                        continue
                    active = [
                        i
                        for i in range(instance.n)
                        if current_schedule.starts[i]
                        <= t
                        < current_schedule.starts[i] + instance.durations[i]
                    ]
                    for i in active[:]:
                        if sum(instance.powers[j] for j in active if j != i) >= best:
                            active.remove(i)
                    active_sets.add(tuple(sorted(active)))
                if not active_sets:
                    raise AssertionError("An incumbent peak must have an overload set")
                addition = [
                    [-base.activities[i, t] for i in active]
                    for active in active_sets
                    for t in range(instance.cycle)
                ]
            else:
                addition = objective_bank.atmost(best - 1)
            r.cnf_vars = max(r.cnf_vars, base.formula.pool.top)
            r.cnf_clauses += len(addition)
            if method == "multiple_sat":
                backend = SATBackend(base.formula.clauses + addition)
                loaded_clauses = len(base.formula.clauses) + len(addition)
                r.solver_instances += 1
                r.backend = backend.name
            else:
                backend.add_clauses(addition)
                loaded_clauses += len(addition)
            r.cnf_peak_clauses = max(r.cnf_peak_clauses, loaded_clauses)
            publish(r)
            answer = backend.solve(deadline)
            r.iterations += 1
            if answer is None:
                r.status = "TIMEOUT"
                break
            if not answer:
                r.status = "OPTIMAL"
                r.proof = "UNSAT after strict objective tightening"
                break
            schedule = base.decode(backend.get_model())
            measured = validate(instance, schedule)
            current_schedule, current_metrics = schedule, measured
            if method != "paper_cuts" and measured[metric_name] >= best:
                raise AssertionError("SAT bound violated by decoded schedule")
            if measured[metric_name] < best:
                _record(r, instance, schedule)
                best = measured[metric_name]
            if best == instance.peak_lower_bound:
                r.status = "OPTIMAL"
                r.proof = "Feasible solution achieves unconditional max-task-power LB"
                break
        return _finish(r, started)
    finally:
        if backend is not None:
            backend.close()


def solve_binary_sat(
    instance: Instance, *, encoding="staircase", objective="peak", time_limit=60.0
):
    started = time.monotonic()
    deadline = started + time_limit
    objective = normalized_objective(objective)
    base = encode(instance, encoding)
    bank = station_peak_bank(base) if objective == "station_peak_sum" else None
    objective_bank = (
        binary_objective_bank(base, bank) if objective != "total_energy" else None
    )
    result = SolveResult(
        "binary_sat",
        encoding,
        objective,
        "UNKNOWN",
        0,
        cnf_vars=base.formula.pool.top,
        cnf_clauses=len(base.formula.clauses),
        cnf_peak_clauses=len(base.formula.clauses),
    )

    def check(bound_clauses):
        result.solver_instances += 1
        backend = SATBackend(base.formula.clauses + bound_clauses)
        result.backend = backend.name
        result.cnf_peak_clauses = max(
            result.cnf_peak_clauses, len(base.formula.clauses) + len(bound_clauses)
        )
        publish(result)
        try:
            answer = backend.solve(deadline)
            result.iterations += 1
            return answer, base.decode(backend.get_model()) if answer else None
        finally:
            backend.close()

    answer, incumbent = check([])
    if answer is None:
        result.status = "TIMEOUT"
        return _finish(result, started)
    if not answer:
        result.status = "INFEASIBLE"
        result.proof = "UNSAT of base feasibility CNF"
        return _finish(result, started)
    _record(result, instance, incumbent)
    if objective == "total_energy":
        result.status = "OPTIMAL"
        result.proof = "All feasible schedules consume sum_i duration_i * power_i"
        return _finish(result, started)
    metric = "station_peak_sum" if bank else "power_peak"
    lower = instance.peak_lower_bound
    upper = result.metrics[metric]
    # Invariant: some known feasible incumbent has metric <= upper;
    # any objective < lower has been excluded by UNSAT or a valid LB.
    while lower < upper:
        if time.monotonic() >= deadline:
            result.status = "TIMEOUT"
            return _finish(result, started)
        middle = (lower + upper) // 2
        clauses = objective_bank.atmost(middle)
        result.cnf_vars = max(result.cnf_vars, base.formula.pool.top)
        result.cnf_clauses = max(
            result.cnf_clauses, len(base.formula.clauses) + len(clauses)
        )
        answer, schedule = check(clauses)
        if answer is None:
            result.status = "TIMEOUT"
            return _finish(result, started)
        if answer:
            _record(result, instance, schedule)
            upper = min(middle, result.metrics[metric])
        else:
            lower = middle + 1
    if not result.metrics or result.metrics[metric] != upper:
        raise AssertionError("Binary search did not retain certified incumbent")
    result.status = "OPTIMAL"
    result.proof = "Binary SAT bounds converge; UNSAT cuts and feasible incumbent"
    return _finish(result, started)
