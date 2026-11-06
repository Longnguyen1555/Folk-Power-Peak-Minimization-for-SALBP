"""Problem model, reference parser, objective metrics, and independent validator."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import re


@dataclass(frozen=True)
class Instance:
    durations: tuple[int, ...]
    powers: tuple[int, ...]
    stations: int
    cycle: int
    precedence: tuple[tuple[int, int], ...] = ()  # zero based, i before j
    name: str = "instance"

    def __post_init__(self):
        n = len(self.durations)
        if n < 1 or len(self.powers) != n or self.stations < 1 or self.cycle < 1:
            raise ValueError("Invalid instance dimensions")
        if any(d < 1 or d > self.cycle for d in self.durations):
            raise ValueError("Each duration must be in [1, cycle]")
        if any(w < 1 for w in self.powers):
            raise ValueError("Power weights must be positive integers")
        if any(not (0 <= i < n and 0 <= j < n and i != j) for i, j in self.precedence):
            raise ValueError("Precedence arcs must connect distinct valid task IDs")
        successors = [[] for _ in range(n)]
        degrees = [0] * n
        for i, j in set(self.precedence):
            successors[i].append(j)
            degrees[j] += 1
        queue = [i for i, d in enumerate(degrees) if d == 0]
        processed = 0
        while queue:
            i = queue.pop()
            processed += 1
            for j in successors[i]:
                degrees[j] -= 1
                if degrees[j] == 0:
                    queue.append(j)
        if processed != n:
            raise ValueError("Precedence graph contains a directed cycle")

    @property
    def n(self) -> int:
        return len(self.durations)

    @property
    def total_energy(self) -> int:
        """sum_t P(t) = sum_i duration_i * power_i (schedule-invariant)."""
        return sum(t * w for t, w in zip(self.durations, self.powers))

    @property
    def total_task_power(self) -> int:
        """Sum of nominal task powers, also independent of the schedule."""
        return sum(self.powers)

    @property
    def peak_lower_bound(self) -> int:
        return max(self.powers)

    @property
    def peak_upper_bound(self) -> int:
        return sum(sorted(self.powers, reverse=True)[:self.stations])


@dataclass(frozen=True)
class Schedule:
    stations: tuple[int, ...]  # zero based
    starts: tuple[int, ...]    # zero based


def validate(instance: Instance, schedule: Schedule) -> dict:
    """Independently recompute every constraint and cost; throws on any invalidity."""
    n, c = instance.n, instance.cycle
    if len(schedule.stations) != n or len(schedule.starts) != n:
        raise ValueError("Schedule length mismatch")
    for i, (k, s, d) in enumerate(zip(schedule.stations, schedule.starts, instance.durations)):
        if not isinstance(k, int) or not 0 <= k < instance.stations:
            raise ValueError(f"Task {i+1} has invalid station {k}")
        if not isinstance(s, int) or not 0 <= s <= c - d:
            raise ValueError(f"Task {i+1} has invalid start {s}")
    for i, j in instance.precedence:
        if schedule.stations[i] > schedule.stations[j]:
            raise ValueError(f"Invalid station precedence: {i+1} -> {j+1}")
        if schedule.stations[i] == schedule.stations[j] and \
           schedule.starts[i] + instance.durations[i] > schedule.starts[j]:
            raise ValueError(f"Invalid same-station precedence: {i+1} -> {j+1}")
    profile = [0] * c
    per_station = [[0] * c for _ in range(instance.stations)]
    for i in range(n):
        for t in range(schedule.starts[i], schedule.starts[i] + instance.durations[i]):
            station = schedule.stations[i]
            if per_station[station][t]:
                raise ValueError(f"Workstation {station+1} overlaps at time {t}")
            per_station[station][t] = instance.powers[i]
            profile[t] += instance.powers[i]
    peak = max(profile)
    energy = sum(profile)
    assert energy == instance.total_energy, "Energy conservation invariant violated"
    return {
        "power_peak": peak,
        "total_energy": energy,
        "total_power": energy,  # alias: discrete time-integrated power (energy)
        "sum_task_power": instance.total_task_power,
        "station_peak_sum": sum(max(p) for p in per_station),
        "power_profile": profile,
        "station_profiles": per_station,
    }


def load_instance(path: str | Path) -> Instance:
    path = Path(path)
    raw = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        durations = tuple(int(t) for t in data["durations"])
        powers = tuple(int(w) for w in data["powers"])
        base = int(data.get("precedence_index_base", 1))
        arcs = tuple((int(i) - base, int(j) - base) for i, j in data.get("precedence", []))
        return Instance(durations, powers, int(data["stations"]), int(data["cycle"]), arcs, path.stem)
    if path.suffix.lower() != ".3pm":
        raise ValueError("Supported input formats are .3pm and .json")
    # Widely used format: n m c; n lines 'duration power'; i,j arcs ended by '-1,-1'.
    lines = [l.strip() for l in raw.splitlines() if l.strip() and not l.lstrip().startswith(("c ", "#", "%"))]
    if not lines:
        raise ValueError("Empty instance")
    n, m, c = [int(x) for x in re.split(r"[\s,]+", lines[0])]
    if len(lines) < 1 + n:
        raise ValueError("Insufficient task rows")
    durations, powers = [], []
    for line in lines[1:1+n]:
        d, w = [int(x) for x in re.split(r"[\s,]+", line)]
        durations.append(d)
        powers.append(w)
    arcs = []
    for line in lines[1+n:]:
        terms = [int(x) for x in re.split(r"[\s,]+", line)]
        if len(terms) != 2:
            raise ValueError(f"Malformed precedence arc: {line}")
        i, j = terms
        if i == j == -1:
            break
        arcs.append((i-1, j-1))
    return Instance(tuple(durations), tuple(powers), m, c, tuple(arcs), path.stem)
