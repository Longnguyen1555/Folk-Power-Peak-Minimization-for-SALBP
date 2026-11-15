"""Binary WCNF/OPB export; these writers do not invoke external solvers."""

from pathlib import Path

from .results import normalized_objective
from .solvers.maxsat import build_wcnf


def export_instance(
    instance, path, *, formulation="shared", encoding="staircase", objective="peak"
):
    objective = normalized_objective(objective)
    if formulation == "paper":
        if objective not in ("peak", "peak_then_total_energy"):
            raise ValueError(
                "The original paper formulation supports the peak objective"
            )
        from .paper import build_paper_wcnf

        wcnf = build_paper_wcnf(instance)
    elif formulation == "shared":
        _, wcnf = build_wcnf(instance, encoding, objective)
    else:
        raise ValueError(formulation)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".wcnf":
        wcnf.to_file(str(path))
    elif path.suffix.lower() == ".opb":
        terms = []
        for clause, weight in zip(wcnf.soft, wcnf.wght):
            if len(clause) != 1 or clause[0] >= 0:
                raise ValueError("OPB export requires negative unit soft clauses")
            terms.append(f"+{weight} x{-clause[0]}")
        lines = [
            f"* #variable= {wcnf.nv} #constraint= {len(wcnf.hard)}",
            "min: " + " ".join(terms) + ";",
        ]
        for clause in wcnf.hard:
            literals = [f"+1 {'~' if lit < 0 else ''}x{abs(lit)}" for lit in clause]
            lines.append(" ".join(literals) + " >= 1;")
        path.write_text("\n".join(lines) + "\n", encoding="utf8")
    else:
        raise ValueError("Output suffix must be .wcnf or .opb")
    return {
        "path": str(path),
        "formulation": formulation,
        "objective_encoding": "binary",
        "variables": wcnf.nv,
        "hard_clauses": len(wcnf.hard),
        "soft_clauses": len(wcnf.soft),
    }
