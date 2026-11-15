"""Solver-neutral time-indexed MIP, shared by CPLEX and Gurobi."""

from dataclasses import dataclass

from ..model import Schedule


def linear(*parts):
    terms = {}
    for scale, expression in parts:
        for variable, coefficient in expression.items():
            terms[variable] = terms.get(variable, 0) + scale * coefficient
    return {
        variable: coefficient for variable, coefficient in terms.items() if coefficient
    }


@dataclass
class Variable:
    name: str
    kind: str
    lower: int
    upper: int
    cost: int = 0


class TimeIndexedMIP:
    def __init__(self, instance, objective):
        self.instance, self.objective = instance, objective
        self.variables = []
        self.offset = instance.total_energy if objective == "total_energy" else 0
        n, m, c = instance.n, instance.stations, instance.cycle
        self.x = {
            (i, k): self.add(f"x_{i}_{k}", "B", 0, 1)
            for i in range(n)
            for k in range(m)
        }
        self.y = {
            (i, s): self.add(f"y_{i}_{s}", "B", 0, 1)
            for i in range(n)
            for s in range(c - instance.durations[i] + 1)
        }
        self.starts = [
            {self.y[i, s]: s for s in range(c - instance.durations[i] + 1) if s}
            for i in range(n)
        ]
        self.station = [{self.x[i, k]: k for k in range(m) if k} for i in range(n)]
        self.active = {
            (i, t): {
                self.y[i, s]: 1
                for s in range(c - instance.durations[i] + 1)
                if s <= t < s + instance.durations[i]
            }
            for i in range(n)
            for t in range(c)
        }
        self.peak = self.add(
            "power_peak",
            "I",
            instance.peak_lower_bound,
            instance.peak_upper_bound,
            int(objective not in ("total_energy", "station_peak_sum")),
        )
        self.station_peaks = (
            [
                self.add(f"station_peak_{k}", "C", 0, max(instance.powers), 1)
                for k in range(m)
            ]
            if objective == "station_peak_sum"
            else []
        )

    def add(self, name, kind, lower, upper, cost=0):
        index = len(self.variables)
        self.variables.append(Variable(name, kind, lower, upper, cost))
        return index

    def rows(self):
        ins = self.instance
        n, m, c = ins.n, ins.stations, ins.cycle
        for i in range(n):
            yield {self.x[i, k]: 1 for k in range(m)}, "E", 1
            yield {self.y[i, s]: 1 for s in range(c - ins.durations[i] + 1)}, "E", 1
        for i, j in ins.precedence:
            yield linear((1, self.station[i]), (-1, self.station[j])), "L", 0
            for k in range(m):
                yield linear(
                    (1, self.starts[i]),
                    (-1, self.starts[j]),
                    (c, {self.x[i, k]: 1, self.x[j, k]: 1}),
                ), "L", 2 * c - ins.durations[i]
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(m):
                    for t in range(c):
                        yield linear(
                            (1, self.active[i, t]),
                            (1, self.active[j, t]),
                            (1, {self.x[i, k]: 1, self.x[j, k]: 1}),
                        ), "L", 3
        for t in range(c):
            yield linear(
                *[(ins.powers[i], self.active[i, t]) for i in range(n)],
                (-1, {self.peak: 1}),
            ), "L", 0
        for k, peak in enumerate(self.station_peaks):
            for i in range(n):
                yield {self.x[i, k]: ins.powers[i], peak: -1}, "L", 0

    def decode(self, values):
        ins = self.instance
        return Schedule(
            tuple(
                max(range(ins.stations), key=lambda k: values[self.x[i, k]])
                for i in range(ins.n)
            ),
            tuple(
                round(
                    sum(
                        coefficient * values[index]
                        for index, coefficient in start.items()
                    )
                )
                for start in self.starts
            ),
        )
