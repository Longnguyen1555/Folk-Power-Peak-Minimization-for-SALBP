from itertools import product
from pathlib import Path
import random
import pytest
from salb3pm.model import Instance, Schedule, load_instance, validate
from salb3pm.cnf import encode, atmost_power
from salb3pm.solvers import solve

EXAMPLES=Path(__file__).resolve().parents[1]/"examples"


def brute_force_optimum(inst: Instance):
    """Independent finite enumeration over station/time assignments (no CNF)."""
    possibilities = [list(product(range(inst.stations), range(inst.cycle-inst.durations[i]+1)))
                     for i in range(inst.n)]
    best = None
    for sequence in product(*possibilities):
        sched=Schedule(tuple(k for k,t in sequence),tuple(t for k,t in sequence))
        try:
            score=validate(inst,sched)["power_peak"]
        except ValueError:
            continue
        best = score if best is None else min(score,best)
    return best


def test_reference_py_example():
    ins=load_instance(EXAMPLES/"paper_py_2024.3pm")
    assert ins.n==4 and ins.peak_lower_bound==4
    assert ins.total_energy==46
    assert brute_force_optimum(ins)==10
    for enc in ["pairwise","staircase"]:
        for method in ("multiple_sat","incremental_sat","paper_cuts"):
            r=solve(ins,method=method,encoding=enc,time_limit=15)
            assert r.status=="OPTIMAL",(enc,method,r.as_dict())
            assert r.metrics["power_peak"]==10
            assert r.proof


def test_second_publication_example():
    ins=load_instance(EXAMPLES/"diamond_ictai_2024.3pm")
    assert brute_force_optimum(ins)==9
    for enc in ("pairwise","staircase"):
        for method in ("multiple_sat","incremental_sat","paper_cuts"):
            r=solve(ins,method=method,encoding=enc,time_limit=15)
            assert r.status=="OPTIMAL",r.as_dict()
            assert r.metrics["power_peak"]==9


def test_staircase_is_smaller_on_reference():
    ins=load_instance(EXAMPLES/"paper_py_2024.3pm")
    old=encode(ins,"pairwise").formula
    new=encode(ins,"staircase").formula
    assert new.pool.top < old.pool.top
    assert len(new.clauses) < len(old.clauses)


def test_energy_is_schedule_invariant():
    inst=Instance((2,1,1),(3,5,2),2,4)
    a=Schedule((0,0,1),(0,2,0))
    b=Schedule((0,1,0),(1,1,0))
    assert validate(inst,a)["total_energy"]==validate(inst,b)["total_energy"]==13
    r=solve(inst,method="incremental_sat",objective="total_energy",time_limit=12)
    assert r.status=="OPTIMAL"
    assert r.metrics["total_energy"]==13
    assert r.iterations==1


def test_infeasible_and_invalid_cases():
    inst=Instance((2,2),(4,3),1,2)
    for enc in ("pairwise","staircase"):
        r=solve(inst,method="incremental_sat",encoding=enc,time_limit=12)
        assert r.status=="INFEASIBLE"
    with pytest.raises(ValueError):
        Instance((1,1),(1,1),1,2,((0,1),(1,0)))
    with pytest.raises(ValueError):
        validate(Instance((2,2),(4,3),1,4),Schedule((0,0),(0,1)))


def test_parse_json_same_as_3pm():
    one=load_instance(EXAMPLES/"paper_py_2024.3pm")
    two=load_instance(EXAMPLES/"small.json")
    assert (one.durations,one.powers,one.stations,one.cycle,one.precedence)==\
           (two.durations,two.powers,two.stations,two.cycle,two.precedence)


@pytest.mark.parametrize("seed",list(range(7)))
def test_random_dag_against_bruteforce(seed):
    rnd=random.Random(seed)
    n=3
    durations=tuple(rnd.randint(1,3) for _ in range(n))
    powers=tuple(rnd.randint(1,5) for _ in range(n))
    arcs=tuple((i,j) for i in range(n) for j in range(i+1,n) if rnd.random()<0.4)
    inst=Instance(durations,powers,2,4,arcs)
    expected=brute_force_optimum(inst)
    for enc in ("staircase","pairwise"):
        r=solve(inst,method="incremental_sat",encoding=enc,time_limit=12)
        if expected is None:
            assert r.status=="INFEASIBLE"
        else:
            assert r.status=="OPTIMAL",r.as_dict()
            assert r.metrics["power_peak"]==expected


def test_maxsat_if_installed():
    pytest.importorskip("pysat")
    ins=load_instance(EXAMPLES/"paper_py_2024.3pm")
    for enc in ("pairwise","staircase"):
        r=solve(ins,method="maxsat",encoding=enc,time_limit=30)
        assert r.status=="OPTIMAL",r.as_dict()
        assert r.metrics["power_peak"]==10


def test_gurobi_if_installed():
    pytest.importorskip("gurobipy")
    ins=load_instance(EXAMPLES/"paper_py_2024.3pm")
    r=solve(ins,method="gurobi",time_limit=30)
    if r.status=="UNAVAILABLE":
        pytest.skip(r.message)
    assert r.status=="OPTIMAL",r.as_dict()
    assert r.metrics["power_peak"]==10


def test_station_peak_sum_against_independent_enumeration():
    ins=Instance((2,1,1),(6,4,2),2,4,((0,2),))
    possibilities=[list(product(range(ins.stations),range(ins.cycle-ins.durations[i]+1)))
                   for i in range(ins.n)]
    expected=min(validate(ins,Schedule(tuple(k for k,t in v),tuple(t for k,t in v)))["station_peak_sum"]
                 for v in product(*possibilities)
                 if _valid(ins,Schedule(tuple(k for k,t in v),tuple(t for k,t in v))))
    for method in ("multiple_sat","incremental_sat"):
        for encoding in ("staircase","pairwise"):
            r=solve(ins,method=method,encoding=encoding,objective="station_peak_sum",time_limit=20)
            assert r.status=="OPTIMAL",r.as_dict()
            assert r.metrics["station_peak_sum"]==expected


def _valid(ins, sched):
    try:
        validate(ins,sched)
        return True
    except ValueError:
        return False


def test_formula_projected_feasibility_all_assignments_tiny():
    # Fix the visible station/start decisions and ask if auxiliary CNF variables
    # can be extended to satisfy all clauses. Independent validator is oracle.
    import time
    from salb3pm.solvers import SATBackend
    ins=Instance((2,2),(3,2),2,3,((0,1),))
    for encoding in ("staircase","pairwise"):
        model=encode(ins,encoding)
        choices=[list(product(range(ins.stations),range(ins.cycle-ins.durations[i]+1)))
                 for i in range(ins.n)]
        for values in product(*choices):
            sched=Schedule(tuple(k for k,t in values),tuple(t for k,t in values))
            unit=[]
            if encoding=="staircase":
                for (i,k),lit in model.stations.items():
                    unit.append([lit if sched.stations[i]<=k else -lit])
                for (i,t),lit in model.starts.items():
                    unit.append([lit if sched.starts[i]<=t else -lit])
            else:
                for (i,k),lit in model.stations.items():
                    unit.append([lit if sched.stations[i]==k else -lit])
                for (i,t),lit in model.starts.items():
                    unit.append([lit if sched.starts[i]==t else -lit])
            backend=SATBackend(model.formula.clauses+unit)
            try:
                assert backend.solve(time.monotonic()+4)==_valid(ins,sched), (encoding,sched)
            finally:
                backend.close()
