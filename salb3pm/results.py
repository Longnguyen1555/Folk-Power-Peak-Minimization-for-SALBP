"""Shared result schema, objective names, and independent validation."""

from dataclasses import dataclass, asdict
from typing import Optional
from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path
import time
from .model import Schedule, validate

METHODS = (
    "multiple_sat",
    "incremental_sat",
    "binary_sat",
    "paper_cuts",
    "maxsat",
    "gurobi",
    "cplex",
    "pb",
    "cpsat",
)
OBJECTIVES = (
    "peak",
    "total_energy",
    "total_power",
    "peak_then_total_energy",
    "peak_then_total_power",
    "station_peak_sum",
)
_progress_path = ContextVar("solver_progress_path", default=None)


@contextmanager
def progress_output(filename):
    """Optional atomic telemetry for a supervising process; no solver changes."""
    token = _progress_path.set(Path(filename) if filename else None)
    try:
        yield
    finally:
        _progress_path.reset(token)


def publish(result):
    path = _progress_path.get()
    if path is None:
        return
    data = {
        key: getattr(result, key)
        for key in (
            "status",
            "elapsed_s",
            "iterations",
            "solver_instances",
            "cnf_vars",
            "cnf_clauses",
            "cnf_peak_clauses",
            "model_variables",
            "model_constraints",
            "backend",
            "proof",
            "message",
        )
    }
    data["metrics"] = {
        key: value
        for key, value in (result.metrics or {}).items()
        if key in ("power_peak", "total_energy", "station_peak_sum")
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data), encoding="utf8")
    temporary.replace(path)


def normalized_objective(objective):
    return {
        "total_power": "total_energy",
        "peak_then_total_power": "peak_then_total_energy",
    }.get(objective, objective)


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
    cnf_peak_clauses: Optional[int] = None
    model_variables: Optional[int] = None
    model_constraints: Optional[int] = None
    message: str = ""

    def as_dict(self):
        v = asdict(self)
        if self.schedule is not None:
            v["schedule"] = {
                "stations": [x + 1 for x in self.schedule.stations],
                "starts": list(self.schedule.starts),
            }
        return v


def _finish(result, start):
    result.elapsed_s = round(time.monotonic() - start, 6)
    publish(result)
    return result


def _record(result, instance, schedule):
    metrics = validate(instance, schedule)
    metric_name = (
        "station_peak_sum" if result.objective == "station_peak_sum" else "power_peak"
    )
    if result.metrics is None or metrics[metric_name] < result.metrics[metric_name]:
        result.schedule = schedule
        result.metrics = metrics
        publish(result)
