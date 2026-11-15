"""The sole SAT oracle: PySAT CaDiCaL195. No implicit backend fallback."""

import time

CADICAL = "cadical195"


class SATBackend:
    def __init__(self, clauses):
        from pysat.solvers import Solver

        self.solver = Solver(name=CADICAL, bootstrap_with=clauses)
        self.name = "pysat:" + CADICAL

    def solve(self, deadline):
        # CaDiCaL does not implement PySAT's interrupt API. Keep its learned
        # state across budget slices and check the deadline between slices.
        # A slice is not a hard wall-clock limit; benchmarks use subprocesses.
        try:
            while time.monotonic() < deadline:
                self.solver.conf_budget(1000)
                answer = self.solver.solve_limited()
                if answer is not None:
                    return answer
            return None
        finally:
            self.solver.conf_budget(-1)

    def get_model(self):
        return self.solver.get_model()

    def add_clauses(self, clauses):
        self.solver.append_formula(clauses)

    def close(self):
        self.solver.delete()
