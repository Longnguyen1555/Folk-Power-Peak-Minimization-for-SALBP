"""Binary weighted MaxSAT using RC2 with a CaDiCaL SAT oracle."""

import time

from ..backends import CADICAL
from ..cnf import encode, binary_objective_bank, station_peak_bank
from ..results import SolveResult, _finish, _record, publish
from .sat import solve_sat


def build_wcnf(instance, encoding="staircase", objective="peak"):
    """Return the decoder and WCNF; only objective bits carry soft costs."""
    from pysat.formula import WCNF

    base = encode(instance, encoding)
    if objective == "total_energy":
        fixed = base.formula.pool.new("constant_energy")
        base.formula.add(fixed)
        costs = [(fixed, instance.total_energy)]
    else:
        station_bank = (
            station_peak_bank(base) if objective == "station_peak_sum" else None
        )
        bank = binary_objective_bank(base, station_bank)
        costs = [(bit, 1 << i) for i, bit in enumerate(bank.bits)]
    wcnf = WCNF()
    wcnf.extend(base.formula.clauses)
    for bit, weight in costs:
        wcnf.append([-bit], weight=weight)
    return base, wcnf


def solve_maxsat(instance, *, encoding="staircase", objective="peak", time_limit=60.0):
    started = time.monotonic()
    if objective == "total_energy":
        result = solve_sat(
            instance, encoding=encoding, objective=objective, time_limit=time_limit
        )
        result.method = "maxsat"
        result.message = "Constant objective: feasibility suffices"
        return result
    result = SolveResult(
        "maxsat", encoding, objective, "UNKNOWN", 0, backend="pysat:RC2/" + CADICAL
    )
    try:
        from pysat.examples.rc2 import RC2

        base, wcnf = build_wcnf(instance, encoding, objective)
    except ImportError as exc:
        result.status = "UNAVAILABLE"
        result.message = f"Install python-sat[pblib]: {exc}"
        return _finish(result, started)
    result.cnf_vars = base.formula.pool.top
    result.cnf_clauses = len(wcnf.hard)
    result.cnf_peak_clauses = len(wcnf.hard) + len(wcnf.soft)
    result.solver_instances = 1
    publish(result)
    with RC2(wcnf, solver=CADICAL, adapt=True) as rc2:
        model = rc2.compute()
        result.iterations = 1
        if model is None:
            result.status = "INFEASIBLE"
            result.proof = "RC2 hard formula unsatisfiable"
        else:
            _record(result, instance, base.decode(model))
            metric = (
                "station_peak_sum" if objective == "station_peak_sum" else "power_peak"
            )
            if result.metrics[metric] != rc2.cost:
                raise AssertionError(
                    f"MaxSAT cost {rc2.cost} != {metric} {result.metrics[metric]}"
                )
            result.status = "OPTIMAL"
            result.proof = "RC2 binary weighted MaxSAT optimum"
    if time.monotonic() - started > time_limit:
        result.message = (
            "RC2 exceeded advisory limit; use subprocess runner for hard cutoff"
        )
    return _finish(result, started)
