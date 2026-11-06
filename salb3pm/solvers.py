"""Exact SAT workflows, original-paper style cuts, weighted MaxSAT and Gurobi MIP.

A tiny dependency-free DPLL fallback permits smoke tests offline; research-scale
experiments require python-sat and (for MIP) gurobipy.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import time
from threading import Timer
from typing import Optional
from .model import Instance, Schedule, validate
from .cnf import Encoded, encode, atmost_power, station_peak_bank, atmost_weighted


METHODS = ("multiple_sat", "incremental_sat", "binary_sat", "paper_cuts", "maxsat", "gurobi", "cpsat")
OBJECTIVES = ("peak", "total_energy", "total_power", "peak_then_total_energy", "peak_then_total_power", "station_peak_sum")


def normalized_objective(objective):
    return {"total_power": "total_energy", "peak_then_total_power": "peak_then_total_energy"}.get(objective, objective)


@dataclass
class SolveResult:
    method: str
    encoding: str
    objective: str
    status: str
    elapsed_s: float
    iterations: int = 0
    solver_instances: int = 0
    schedule: Optional[Schedule] = None
    metrics: Optional[dict] = None
    backend: str = ""
    proof: str = ""
    cnf_vars: Optional[int] = None
    cnf_clauses: Optional[int] = None
    message: str = ""

    def as_dict(self):
        v = asdict(self)
        if self.schedule is not None:
            v["schedule"] = {
                "stations": [x + 1 for x in self.schedule.stations],
                "starts": list(self.schedule.starts),
            }
        return v


class PureDPLL:
    """Small-instance correctness fallback; NOT a CDCL incremental SAT solver."""
    def __init__(self, clauses):
        self.clauses = [tuple(c) for c in clauses]
        self.max_id = max((abs(l) for c in clauses for l in c), default=0)
        self.assignment = None
        self.steps = 0

    def add_clause(self, clause):
        clause = tuple(clause)
        self.clauses.append(clause)
        self.max_id = max(self.max_id, *(abs(l) for l in clause), 0)

    def solve(self, deadline):
        self.steps = 0
        clauses = self.clauses
        def recurse(assignment):
            self.steps += 1
            if self.steps % 256 == 0 and time.monotonic() > deadline:
                raise TimeoutError("DPLL time limit")
            while True:
                unit = None
                undecided_clauses = []
                satisfied_all = True
                for clause in clauses:
                    unfixed = []
                    satisfied = False
                    for lit in clause:
                        v = assignment.get(abs(lit))
                        if v is None:
                            unfixed.append(lit)
                        elif v == (lit > 0):
                            satisfied = True
                            break
                    if satisfied:
                        continue
                    satisfied_all = False
                    if not unfixed:
                        return None
                    if len(unfixed) == 1:
                        unit = unfixed[0]
                        break
                    undecided_clauses.append(unfixed)
                if satisfied_all:
                    return assignment
                if unit is None:
                    break
                var, desired = abs(unit), unit > 0
                current = assignment.get(var)
                if current is not None and current != desired:
                    return None
                assignment[var] = desired
            freq = {}
            polarity = {}
            for clause in undecided_clauses:
                for lit in clause:
                    var = abs(lit)
                    freq[var] = freq.get(var,0) + 1
                    polarity[var] = polarity.get(var,0) + (1 if lit > 0 else -1)
            var = max(freq, key=freq.get)
            for value in (polarity[var] >= 0, polarity[var] < 0):
                next_assignment = assignment.copy()
                next_assignment[var] = value
                solved = recurse(next_assignment)
                if solved is not None:
                    return solved
            return None
        solved = recurse({})
        if solved is None:
            return False
        self.assignment = [i if solved.get(i,False) else -i for i in range(1,self.max_id+1)]
        return True

    def get_model(self):
        return self.assignment

    def delete(self):
        pass


class SATBackend:
    def __init__(self, clauses, solver_name="cadical195"):
        try:
            from pysat.solvers import Solver
            try:
                self.solver = Solver(name=solver_name, bootstrap_with=clauses)
            except (ImportError, ValueError, TypeError):
                self.solver = Solver(name="glucose3", bootstrap_with=clauses)
                solver_name = "glucose3"
            self.name = "pysat:" + solver_name
            self.native = True
        except ImportError:
            self.solver = PureDPLL(clauses)
            self.name = "pure-dpll:fallback"
            self.native = False

    def solve(self, deadline):
        if time.monotonic() >= deadline:
            return None
        if not self.native:
            try:
                return self.solver.solve(deadline)
            except TimeoutError:
                return None
        # Genuine interruptible PySAT solve, preserving the solver and learned clauses.
        delay = max(0, deadline-time.monotonic())
        t = Timer(delay, self.solver.interrupt)
        t.daemon = True
        t.start()
        try:
            ans = self.solver.solve_limited(expect_interrupt=True)
        finally:
            t.cancel()
            self.solver.clear_interrupt()
        return ans

    def get_model(self):
        return self.solver.get_model()

    def add_clauses(self, clauses):
        for clause in clauses:
            self.solver.add_clause(clause)

    def close(self):
        self.solver.delete()


def _finish(result, start):
    result.elapsed_s = round(time.monotonic()-start,6)
    return result


def _record(result, instance, schedule):
    metrics = validate(instance, schedule)
    metric_name = "station_peak_sum" if result.objective == "station_peak_sum" else "power_peak"
    if result.metrics is None or metrics[metric_name] < result.metrics[metric_name]:
        result.schedule = schedule
        result.metrics = metrics


def solve_sat(instance: Instance, *, method="incremental_sat", encoding="staircase",
              objective="peak", solver_name="cadical195", time_limit=60.0):
    if method not in ("multiple_sat", "incremental_sat", "binary_sat", "paper_cuts"):
        raise ValueError(method)
    objective = normalized_objective(objective)
    if objective not in OBJECTIVES:
        raise ValueError(objective)
    started = time.monotonic()
    deadline = started+time_limit
    if method == "binary_sat":
        return solve_binary_sat(instance, encoding=encoding, objective=objective,
                                solver_name=solver_name, time_limit=time_limit)
    if method == "paper_cuts" and objective == "station_peak_sum":
        raise ValueError("paper_cuts is a literature-specific power-peak method")
    base = encode(instance,encoding)
    station_bank = station_peak_bank(base) if objective == "station_peak_sum" else None
    r = SolveResult(method,encoding,objective,"UNKNOWN",0,
                    cnf_vars=base.formula.pool.top,
                    cnf_clauses=len(base.formula.clauses))
    backend = SATBackend(base.formula.clauses,solver_name)
    r.solver_instances += 1
    r.backend = backend.name
    try:
        answer = backend.solve(deadline)
        r.iterations += 1
        if answer is None:
            r.status = "TIMEOUT"
            return _finish(r,started)
        if not answer:
            r.status = "INFEASIBLE"
            r.proof = "UNSAT of base feasibility CNF"
            return _finish(r,started)
        current_schedule = base.decode(backend.get_model())
        current_metrics = validate(instance, current_schedule)
        _record(r, instance, current_schedule)
        if objective == "total_energy":
            r.status = "OPTIMAL"
            r.proof = "All schedules have the same sum_i duration_i * power_i"
            return _finish(r,started)
        metric_name = "station_peak_sum" if station_bank else "power_peak"
        if r.metrics[metric_name] == instance.peak_lower_bound:
            r.status = "OPTIMAL"
            r.proof = "Feasible solution achieves unconditional max-task-power LB"
            return _finish(r,started)
        best = r.metrics[metric_name]
        while True:
            if time.monotonic() >= deadline:
                r.status = "TIMEOUT"
                break
            if method == "paper_cuts":
                # The original SAT paper forbids a set of simultaneously active
                # tasks with total power >= current incumbent for every slot.
                # Each cut is valid for all schedules that strictly beat incumbent.
                active_sets = set()
                for t, load in enumerate(current_metrics["power_profile"]):
                    if load < best:
                        continue
                    active = [i for i in range(instance.n)
                              if current_schedule.starts[i] <= t < current_schedule.starts[i] + instance.durations[i]]
                    for i in active[:]:
                        if sum(instance.powers[j] for j in active if j != i) >= best:
                            active.remove(i)
                    active_sets.add(tuple(sorted(active)))
                if not active_sets:
                    raise AssertionError("An incumbent peak must have an overload set")
                addition = [[-base.activities[i,t] for i in active]
                            for active in active_sets for t in range(instance.cycle)]
            else:
                try:
                    addition = (atmost_weighted(base,*station_bank,best-1,instance.peak_lower_bound)
                                if station_bank else atmost_power(base,best-1))
                except RuntimeError as exc:
                    r.status = "UNAVAILABLE"
                    r.message = str(exc)
                    break
            r.cnf_vars = base.formula.pool.top
            r.cnf_clauses += len(addition)
            if method == "multiple_sat":
                backend.close()
                backend = SATBackend(base.formula.clauses+addition,solver_name)
                r.solver_instances += 1
                r.backend = backend.name
            else:
                backend.add_clauses(addition)
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
                _record(r,instance,schedule)
                best = measured[metric_name]
            if best == instance.peak_lower_bound:
                r.status = "OPTIMAL"
                r.proof = "Feasible solution achieves unconditional max-task-power LB"
                break
        return _finish(r,started)
    finally:
        backend.close()


def solve_maxsat(instance: Instance, *, encoding="staircase", objective="peak",
                 time_limit=60.0):
    start = time.monotonic()
    base = encode(instance,encoding)
    station_bank = station_peak_bank(base) if objective == "station_peak_sum" else None
    r = SolveResult("maxsat",encoding,objective,"UNKNOWN",0,
                    cnf_vars=base.formula.pool.top,cnf_clauses=len(base.formula.clauses))
    if objective == "total_energy":
        feasible = solve_sat(instance,method="incremental_sat",encoding=encoding,
                             objective=objective,time_limit=time_limit)
        feasible.method = "maxsat"
        feasible.message = "Constant-objective feasibility solved with SAT; no MaxSAT optimization necessary"
        return feasible
    try:
        from pysat.formula import WCNF
        from pysat.examples.rc2 import RC2
        from pysat.pb import PBEnc, EncType
    except ImportError:
        r.status="UNAVAILABLE"
        r.message="Install python-sat[pblib] to run RC2 MaxSAT"
        return _finish(r,start)
    U = instance.peak_upper_bound
    wcnf = WCNF()
    for clause in base.formula.clauses:
        wcnf.append(clause)
    if station_bank:
        for lit,weight in zip(*station_bank):
            wcnf.append([-lit],weight=weight)
    else:
        _populate_maxsat_peak_objective(wcnf,base,instance,PBEnc,EncType)
    r.cnf_vars = base.formula.pool.top
    r.cnf_clauses = len(wcnf.hard)
    r.backend = "pysat:RC2"
    r.solver_instances = 1
    with RC2(wcnf,solver="g3",adapt=True) as rc2:
        model = rc2.compute()
        r.iterations = 1
        if model is None:
            r.status="INFEASIBLE"
            r.proof="RC2 hard formula unsatisfiable"
        else:
            _record(r,instance,base.decode(model))
            metric_name = "station_peak_sum" if station_bank else "power_peak"
            if r.metrics[metric_name] != rc2.cost:
                raise AssertionError(f"MaxSAT cost {rc2.cost} != {metric_name} {r.metrics[metric_name]}")
            r.status="OPTIMAL"
            r.proof="RC2 weighted partial MaxSAT optimum"
    if time.monotonic()-start>time_limit:
        r.message="RC2 exceeded advisory time limit (no hard-interrupt contract)"
    return _finish(r,start)


def _populate_maxsat_peak_objective(wcnf, base, instance, PBEnc, EncType):
    U = instance.peak_upper_bound
    # Unary peak levels z_l. Σ_l z_l is an upper bound on all instantaneous loads.
    # Σ_i power_i*A[i,t] + Σ_l ¬z_l <= U  <=> load(t) <= Σ_l z_l.
    z = [base.formula.pool.new("peak_at_least",level) for level in range(1,U+1)]
    for k, lit in enumerate(z):
        wcnf.append([-lit],weight=1)
        if k > 0:
            wcnf.append([-lit,z[k-1]])
    for t in range(instance.cycle):
        pbc = PBEnc.atmost(
            lits=[base.activities[i,t] for i in range(instance.n)] + [-x for x in z],
            weights=list(instance.powers) + [1]*U,
            bound=U,top_id=base.formula.pool.top,encoding=EncType.binmerge)
        base.formula.pool.reserve(pbc.nv)
        for clause in pbc.clauses:
            wcnf.append(clause)


def solve_gurobi(instance: Instance, *, encoding="staircase", objective="peak",time_limit=60.0):
    start = time.monotonic()
    r = SolveResult("gurobi",encoding,objective,"UNKNOWN",0,backend="gurobipy:MIP")
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError:
        r.status="UNAVAILABLE"
        r.message="Install gurobipy and configure an appropriate Gurobi license"
        return _finish(r,start)
    try:
        n, c, m = instance.n,instance.cycle,instance.stations
        mdl = gp.Model("SALB3PM")
        r.solver_instances = 1
        mdl.Params.OutputFlag = 0
        mdl.Params.TimeLimit = float(time_limit)
        mdl.Params.MIPGap = 0.0
        mdl.Params.MIPGapAbs = 0.0
        x = mdl.addVars(n,m,vtype=GRB.BINARY,name="station")
        y = {(i,s):mdl.addVar(vtype=GRB.BINARY,name=f"start_{i}_{s}")
             for i in range(n) for s in range(c-instance.durations[i]+1)}
        for i in range(n):
            mdl.addConstr(gp.quicksum(x[i,k] for k in range(m)) == 1)
            mdl.addConstr(gp.quicksum(y[i,s] for s in range(c-instance.durations[i]+1)) == 1)
        starts = [gp.quicksum(s*y[i,s] for s in range(c-instance.durations[i]+1)) for i in range(n)]
        active = {(i,t):gp.quicksum(y[i,s] for s in range(c-instance.durations[i]+1)
                       if s <= t < s+instance.durations[i])
                  for i in range(n) for t in range(c)}
        for i,j in instance.precedence:
            mdl.addConstr(gp.quicksum(k*x[i,k] for k in range(m)) <=
                          gp.quicksum(k*x[j,k] for k in range(m)))
            for k in range(m):
                mdl.addConstr(starts[i]+instance.durations[i] <=
                              starts[j]+c*(2-x[i,k]-x[j,k]))
        for i in range(n):
            for j in range(i+1,n):
                for k in range(m):
                    for t in range(c):
                        mdl.addConstr(active[i,t]+active[j,t]+x[i,k]+x[j,k] <= 3)
        peak = mdl.addVar(vtype=GRB.INTEGER,lb=instance.peak_lower_bound,
                          ub=instance.peak_upper_bound,name="power_peak")
        for t in range(c):
            mdl.addConstr(gp.quicksum(instance.powers[i]*active[i,t]
                                      for i in range(n)) <= peak)
        if objective == "station_peak_sum":
            station_peaks = mdl.addVars(m,lb=0,vtype=GRB.CONTINUOUS,name="station_peak")
            for k in range(m):
                for i in range(n):
                    mdl.addConstr(station_peaks[k] >= instance.powers[i]*x[i,k])
            mdl.setObjective(gp.quicksum(station_peaks[k] for k in range(m)),GRB.MINIMIZE)
        elif objective == "total_energy":
            mdl.setObjective(gp.LinExpr(float(instance.total_energy)),GRB.MINIMIZE)
        else:
            # The secondary objective total_energy is constant, so this is exact
            # for both peak and lex(peak,total_energy).
            mdl.setObjective(peak,GRB.MINIMIZE)
        mdl.optimize()
        r.iterations=1
        if mdl.SolCount:
            schedule = Schedule(tuple(max(range(m),key=lambda k:x[i,k].X) for i in range(n)),
                                tuple(round(starts[i].getValue()) for i in range(n)))
            _record(r,instance,schedule)
        if mdl.Status == GRB.OPTIMAL:
            r.status="OPTIMAL"
            r.proof="Gurobi MIP optimum certificate"
        elif mdl.Status == GRB.INFEASIBLE:
            r.status="INFEASIBLE"
            r.proof="Gurobi infeasibility certificate"
        elif mdl.Status == GRB.TIME_LIMIT:
            r.status="TIMEOUT"
            r.message="Best incumbent (if any), optimality not proven"
        else:
            r.status="UNKNOWN"
            r.message=f"Gurobi status code: {mdl.Status}"
    except gp.GurobiError as exc:
        r.status="UNAVAILABLE"
        r.message=f"Gurobi environment/license error: {exc}"
    return _finish(r,start)


def solve(instance: Instance, *, method="incremental_sat", encoding="staircase",
          objective="peak", time_limit=60.0, solver_name="cadical195"):
    if objective not in OBJECTIVES:
        raise ValueError(objective)
    objective = normalized_objective(objective)
    if method in ("multiple_sat","incremental_sat","binary_sat","paper_cuts"):
        return solve_sat(instance,method=method,encoding=encoding,objective=objective,
                         time_limit=time_limit,solver_name=solver_name)
    if method == "maxsat":
        return solve_maxsat(instance,encoding=encoding,objective=objective,time_limit=time_limit)
    if method == "gurobi":
        return solve_gurobi(instance,encoding=encoding,objective=objective,time_limit=time_limit)
    if method == "cpsat":
        return solve_cpsat(instance,encoding=encoding,objective=objective,time_limit=time_limit)
    raise ValueError(f"Unknown method {method}")


# The upstream BS-E/BS-I solvers use binary search. Provide the same search
# strategy over the shared, independently validated staircase/pairwise CNF.
def solve_binary_sat(instance: Instance, *, encoding="staircase", objective="peak",
                     solver_name="cadical195", time_limit=60.0):
    started = time.monotonic()
    deadline = started + time_limit
    objective = normalized_objective(objective)
    base = encode(instance, encoding)
    bank = station_peak_bank(base) if objective == "station_peak_sum" else None
    result = SolveResult("binary_sat", encoding, objective, "UNKNOWN", 0,
                         cnf_vars=base.formula.pool.top,
                         cnf_clauses=len(base.formula.clauses))
    def check(bound_clauses):
        result.solver_instances += 1
        backend = SATBackend(base.formula.clauses + bound_clauses, solver_name)
        result.backend = backend.name
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
        try:
            clauses = (atmost_weighted(base, *bank, middle, instance.peak_lower_bound)
                       if bank else atmost_power(base, middle))
        except RuntimeError as exc:
            result.status = "UNAVAILABLE"
            result.message = str(exc)
            return _finish(result, started)
        result.cnf_vars = max(result.cnf_vars, base.formula.pool.top)
        result.cnf_clauses = max(result.cnf_clauses, len(base.formula.clauses) + len(clauses))
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


def solve_cpsat(instance: Instance, *, encoding="staircase", objective="peak", time_limit=60.0):
    started = time.monotonic()
    objective = normalized_objective(objective)
    result = SolveResult("cpsat", encoding, objective, "UNKNOWN", 0, backend="ortools:CP-SAT")
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        result.status = "UNAVAILABLE"
        result.message = "Install ortools to run CP-SAT"
        return _finish(result, started)
    ins = instance
    model = cp_model.CpModel()
    n, m, c = ins.n, ins.stations, ins.cycle
    station = [model.NewIntVar(0, m-1, f"station_{i}") for i in range(n)]
    start = [model.NewIntVar(0, c-ins.durations[i], f"start_{i}") for i in range(n)]
    end = [model.NewIntVar(ins.durations[i], c, f"end_{i}") for i in range(n)]
    intervals = []
    assigned = {}
    active = {}
    for i in range(n):
        model.Add(end[i] == start[i] + ins.durations[i])
        for k in range(m):
            b = model.NewBoolVar(f"assigned_{i}_{k}")
            assigned[i,k] = b
            model.Add(station[i] == k).OnlyEnforceIf(b)
            model.Add(station[i] != k).OnlyEnforceIf(b.Not())
            intervals.append((k, model.NewOptionalIntervalVar(start[i],ins.durations[i],end[i],b,f"int_{i}_{k}")))
        model.AddExactlyOne(assigned[i,k] for k in range(m))
        for t in range(c):
            # Reify exact activity through the task's discrete start-choice literals.
            active[i,t] = model.NewBoolVar(f"active_{i}_{t}")
    for k in range(m):
        model.AddNoOverlap(item for k2,item in intervals if k2 == k)
    for i,j in ins.precedence:
        model.Add(station[i] <= station[j])
        same = model.NewBoolVar(f"same_station_{i}_{j}")
        model.Add(station[i] == station[j]).OnlyEnforceIf(same)
        model.Add(station[i] != station[j]).OnlyEnforceIf(same.Not())
        model.Add(end[i] <= start[j]).OnlyEnforceIf(same)
    # Include complete power profiles (not simply per-station energy sums).
    starts = {}
    for i in range(n):
        terms=[]
        for s in range(c-ins.durations[i]+1):
            b=model.NewBoolVar(f"task_{i}_starts_{s}")
            model.Add(start[i] == s).OnlyEnforceIf(b)
            model.Add(start[i] != s).OnlyEnforceIf(b.Not())
            starts[i,s]=b
            terms.append(b)
        model.AddExactlyOne(terms)
        for t in range(c):
            covers=[starts[i,s] for s in range(c-ins.durations[i]+1)
                    if s<=t<s+ins.durations[i]]
            model.Add(active[i,t] == sum(covers))
    peak=model.NewIntVar(ins.peak_lower_bound,ins.peak_upper_bound,"power_peak")
    for t in range(c):
        model.Add(sum(ins.powers[i]*active[i,t] for i in range(n)) <= peak)
    if objective == "station_peak_sum":
        station_peaks=[model.NewIntVar(0,max(ins.powers),f"station_peak_{k}") for k in range(m)]
        for i in range(n):
            for k in range(m):
                model.Add(station_peaks[k] >= ins.powers[i]).OnlyEnforceIf(assigned[i,k])
        model.Minimize(sum(station_peaks))
    elif objective == "total_energy":
        model.Minimize(ins.total_energy)
    else:
        model.Minimize(peak)
    solver=cp_model.CpSolver()
    result.solver_instances=1
    solver.parameters.max_time_in_seconds = max(0.01,float(time_limit))
    solver.parameters.num_search_workers = 1
    status=solver.Solve(model)
    result.iterations=1
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        sched=Schedule(tuple(solver.Value(x) for x in station),
                       tuple(solver.Value(x) for x in start))
        _record(result,ins,sched)
    if status == cp_model.OPTIMAL:
        result.status="OPTIMAL"
        result.proof="OR-Tools CP-SAT optimum"
    elif status == cp_model.INFEASIBLE:
        result.status="INFEASIBLE"
        result.proof="OR-Tools CP-SAT infeasibility"
    elif status == cp_model.FEASIBLE:
        result.status="TIMEOUT"
        result.message="Feasible incumbent; no optimality certificate"
    else:
        result.status="TIMEOUT" if status == cp_model.UNKNOWN else "UNKNOWN"
        result.message=f"CP-SAT status {solver.StatusName(status)}"
    return _finish(result, started)
