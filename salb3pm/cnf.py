"""CNF construction with exact staircase/order encoding and a pairwise baseline.

Each station threshold Q[i,k] means station_i <= k. Each time threshold
B[i,t] means start_i <= t. Monotonic thresholds produce the staircase.
The activity A[i,t] is equivalent to B[i,t] AND NOT B[i,t-duration_i].
"""
from __future__ import annotations
from itertools import combinations
from dataclasses import dataclass
from typing import Iterable
from .model import Instance, Schedule


class VariablePool:
    def __init__(self):
        self.counter = 0
        self.names: dict[tuple, int] = {}

    @property
    def top(self):
        return self.counter

    def new(self, *name):
        key = tuple(name)
        if key not in self.names:
            self.counter += 1
            self.names[key] = self.counter
        return self.names[key]

    def reserve(self, top: int):
        self.counter = max(self.counter, top)


class Formula:
    def __init__(self, pool: VariablePool | None = None):
        self.pool = pool or VariablePool()
        self.clauses: list[list[int]] = []

    def add(self, *lits: int | bool):
        """True/False can be constants; 0 is not a legal literal."""
        if any(lit is True for lit in lits):
            return
        v = [int(lit) for lit in lits if lit is not False]
        if 0 in v:
            raise ValueError("Zero is not a SAT literal")
        if len(set(v)) < len(v):
            v = list(dict.fromkeys(v))
        if any(-x in v for x in v):
            return
        self.clauses.append(v)

    def at_most_one(self, lits: list[int], *, sequential: bool = True):
        if not sequential or len(lits) < 6:
            for a, b in combinations(lits, 2):
                self.add(-a, -b)
            return
        # Sinz ladder: n vars, n-1 auxiliary vars, O(n) clauses.
        aux = [self.pool.new("amo", len(self.clauses), i) for i in range(len(lits) - 1)]
        self.add(-lits[0], aux[0])
        for i in range(1, len(lits)-1):
            self.add(-lits[i], aux[i])
            self.add(-aux[i-1], aux[i])
            self.add(-lits[i], -aux[i-1])
        self.add(-lits[-1], -aux[-1])

    def exactly_one(self, lits: list[int], *, sequential: bool = True):
        self.add(*lits)
        self.at_most_one(lits, sequential=sequential)

    def extend(self, clauses: Iterable[list[int]]):
        for clause in clauses:
            self.add(*clause)


@dataclass
class Encoded:
    instance: Instance
    encoding: str
    formula: Formula
    activities: dict[tuple[int, int], int]
    stations: dict[tuple[int, int], int]
    starts: dict[tuple[int, int], int]

    def decode(self, model: list[int]) -> Schedule:
        positives = {lit for lit in model if lit > 0}
        n = self.instance.n
        if self.encoding == "staircase":
            station_values = tuple(next((k for k in range(self.instance.stations - 1)
                                         if self.stations[(i,k)] in positives),
                                        self.instance.stations-1) for i in range(n))
            start_values = tuple(next((t for t in range(self.instance.cycle-self.instance.durations[i])
                                       if self.starts[(i,t)] in positives),
                                      self.instance.cycle-self.instance.durations[i]) for i in range(n))
        else:
            station_values = tuple(next(k for k in range(self.instance.stations)
                                        if self.stations[(i,k)] in positives) for i in range(n))
            start_values = tuple(next(t for t in range(self.instance.cycle-self.instance.durations[i]+1)
                                      if self.starts[(i,t)] in positives) for i in range(n))
        return Schedule(station_values, start_values)


def encode(instance: Instance, encoding: str = "staircase") -> Encoded:
    if encoding not in {"staircase", "pairwise"}:
        raise ValueError("encoding must be 'staircase' or 'pairwise'")
    n, m, c = instance.n, instance.stations, instance.cycle
    f = Formula()
    p = f.pool
    a = {(i,t): p.new("active",i,t) for i in range(n) for t in range(c)}
    if encoding == "staircase":
        q = {(i,k): p.new("station_le",i,k) for i in range(n) for k in range(m-1)}
        b = {(i,t): p.new("start_le",i,t) for i in range(n)
             for t in range(c-instance.durations[i])}
        for i in range(n):
            for k in range(m-2):
                f.add(-q[i,k], q[i,k+1])
            for t in range(c-instance.durations[i]-1):
                f.add(-b[i,t], b[i,t+1])

            def le(t):
                if t < 0:
                    return False
                if t >= c-instance.durations[i]:
                    return True
                return b[i,t]

            for t in range(c):
                l, r, act = le(t), le(t-instance.durations[i]), a[i,t]
                f.add(-act, l)
                f.add(-act, -r if type(r) is int else not r)
                f.add((-l if type(l) is int else not l), r, act)

        def neq(i,k):
            if k == 0 and m == 1:
                return []
            if k == 0:
                return [-q[i,0]]
            if k == m-1:
                return [q[i,m-2]]
            return [-q[i,k], q[i,k-1]]

        # station_i <= station_j: if j <= k then i <= k.
        for i, j in instance.precedence:
            for k in range(m-1):
                f.add(-q[j,k], q[i,k])
            # On same station: start_i + duration_i <= start_j.
            # If start_j <= t, then start_i <= t-duration_i.
            for k in range(m):
                guards = neq(i,k) + neq(j,k)
                for t in range(c-instance.durations[j]+1):
                    bj = b.get((j,t), True)
                    bi = b.get((i,t-instance.durations[i]),
                               False if t-instance.durations[i] < 0 else True)
                    f.add(*guards,
                          -bj if type(bj) is int else not bj,
                          bi)

        for i in range(n):
            for j in range(i+1,n):
                for k in range(m):
                    guard = neq(i,k)+neq(j,k)
                    for t in range(c):
                        f.add(-a[i,t],-a[j,t],*guard)
        return Encoded(instance, encoding, f, a, q, b)

    q = {(i,k): p.new("station",i,k) for i in range(n) for k in range(m)}
    b = {(i,t): p.new("start",i,t) for i in range(n)
         for t in range(c-instance.durations[i]+1)}
    for i in range(n):
        f.exactly_one([q[i,k] for k in range(m)], sequential=False)
        f.exactly_one([b[i,t] for t in range(c-instance.durations[i]+1)], sequential=False)
        for t in range(c):
            covering = [b[i,s] for s in range(c-instance.durations[i]+1)
                        if s <= t < s+instance.durations[i]]
            for start in covering:
                f.add(-start,a[i,t])
            f.add(-a[i,t],*covering)
    for i,j in instance.precedence:
        for ki in range(m):
            for kj in range(ki):
                f.add(-q[i,ki],-q[j,kj])
        for k in range(m):
            for si in range(c-instance.durations[i]+1):
                for sj in range(c-instance.durations[j]+1):
                    if si+instance.durations[i] > sj:
                        f.add(-q[i,k],-q[j,k],-b[i,si],-b[j,sj])
    for i in range(n):
        for j in range(i+1,n):
            for k in range(m):
                for t in range(c):
                    f.add(-q[i,k],-q[j,k],-a[i,t],-a[j,t])
    return Encoded(instance, encoding, f, a, q, b)


def atmost_power(encoded: Encoded, bound: int) -> list[list[int]]:
    """Exact global load <= bound at every time, using PBEnc when installed.

    Fallback: minimal-overweight subset clauses, limited to small n. PySAT's
    PBEnc (binary merger) is the production encoder.
    """
    ins = encoded.instance
    if bound < 0:
        return [[]]
    if bound >= ins.peak_upper_bound:
        return []
    if bound < ins.peak_lower_bound:
        return [[]]
    try:
        from pysat.pb import PBEnc, EncType
        use_pysat = True
    except ImportError:
        use_pysat = False
    output = []
    for t in range(ins.cycle):
        lits = [encoded.activities[i,t] for i in range(ins.n)]
        if use_pysat:
            cnf = PBEnc.atmost(lits=lits, weights=list(ins.powers), bound=bound,
                                top_id=encoded.formula.pool.top,
                                encoding=EncType.binmerge)
            encoded.formula.pool.reserve(cnf.nv)
            output.extend(cnf.clauses)
        else:
            if ins.n > 12:
                raise RuntimeError("Install python-sat[pblib] for more than 12 tasks")
            for k in range(1, ins.n+1):
                for comb in combinations(range(ins.n),k):
                    weight = sum(ins.powers[i] for i in comb)
                    if weight > bound and weight-min(ins.powers[i] for i in comb) <= bound:
                        output.append([-lits[i] for i in comb])
    return output


def station_peak_bank(encoded: Encoded) -> tuple[list[int], list[int]]:
    """Linear thresholds for Σ_k max{w_i: task i assigned to station k}.

    For each station and distinct power level l, H[k,l] is forced whenever
    a task with power >=l is assigned there. Weighted costs are differences
    of successive power levels. Only O(m * distinct_power_levels) variables.
    Reverse implications are unnecessary for exact minimization/upper bounds.
    Must be called BEFORE constructing the SAT solver from the base clauses.
    """
    ins, f = encoded.instance, encoded.formula
    levels = sorted(set(ins.powers))
    bits, weights = [], []
    for k in range(ins.stations):
        prev = 0
        last = None
        for level in levels:
            h = f.pool.new("station_peak_ge",k,level)
            bits.append(h)
            weights.append(level-prev)
            if last is not None:
                f.add(-h,last)
            prev,last = level,h
            for i in range(ins.n):
                if ins.powers[i] < level:
                    continue
                if encoded.encoding == "pairwise":
                    guards = [-encoded.stations[i,k]]
                elif ins.stations == 1:
                    guards = []
                elif k == 0:
                    guards = [-encoded.stations[i,0]]
                elif k == ins.stations-1:
                    guards = [encoded.stations[i,k-1]]
                else:
                    guards = [-encoded.stations[i,k],encoded.stations[i,k-1]]
                f.add(*guards,h)
    return bits, weights


def atmost_weighted(encoded: Encoded, lits: list[int], weights: list[int],
                    bound: int, lower_bound: int = 0) -> list[list[int]]:
    if bound < lower_bound:
        return [[]]
    if bound >= sum(weights):
        return []
    try:
        from pysat.pb import PBEnc, EncType
        cnf = PBEnc.atmost(lits=lits,weights=weights,bound=bound,
                            top_id=encoded.formula.pool.top,
                            encoding=EncType.binmerge)
        encoded.formula.pool.reserve(cnf.nv)
        return cnf.clauses
    except ImportError:
        if len(lits) > 12:
            raise RuntimeError("Install python-sat[pblib] for general PB constraints")
        clauses=[]
        for k in range(1,len(lits)+1):
            for comb in combinations(range(len(lits)),k):
                val=sum(weights[i] for i in comb)
                if val>bound and val-min(weights[i] for i in comb)<=bound:
                    clauses.append([-lits[i] for i in comb])
        return clauses
