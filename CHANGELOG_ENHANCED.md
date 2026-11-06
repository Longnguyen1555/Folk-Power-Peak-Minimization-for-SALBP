# Changes relative to the uploaded ORIGINAL repository

This folder was created by unpacking `SALB3PM-Satisfiability_based_complete_methods-main.zip` and retaining all 440+ provided benchmark .3pm files and the original source code structure.

## Preserved upstream components

- All datasets in `benchmarks/` (1993, 2013, round_10_2013 and PsPlib where supplied)
- All 10 original `Cadical-*.py` / `Maplesat-*.py` SAT implementations
- Both original WCNF generators `MSAT-I/E.py` and OPB generators `PBO-I/E.py`
- Original OR-Tools CP-SAT implementation and original LP-reading Gurobi/CPLEX/SCIP tools
- Original README, LICENSE, usage scripts and input convention

## Enhanced integrations

| Location | Change | Backward compatibility |
|---|---|---|
| `solvers/SAT_based/{Cadical,Maplesat}-*.py` | Added optional `--encoding`, `--objective`, `--time-limit` routing into `salb3pm` | No flags = legacy path; explicit flags = new engine |
| `solvers/SAT_based/{MultipleSAT,IncrementalSAT,BinarySAT,StaircasePaperCuts}.py` | New CLI entry points with actual optimization loops | Additive |
| `solvers/ILP/GUROBI-7200s.py` | Direct `.3pm` branch + no-incumbent reporting fix for `.lp` | `.lp` unchanged except error reporting |
| `solvers/ILP/GUROBI-3PM.py` | Direct `.3pm` MIP with optimality status/metric validation | Additive |
| `solvers/CPSAT/CPSAT.py` | Optional `--objective` modern mode + legacy energy reporting | Default objective remains peak |
| `solvers/MaxSAT_based/MSAT-*.py` | Optional `--solve` route to RC2 over new CNF | No flags = legacy `.wcnf` generator |
| `solvers/PB_based/PBO-*.py` | Optional constant `--objective total_power` (forced-true indicator), plus energy report | Peak OPB default unchanged |
| `salb3pm/*` | Validated model, order encoding, PB bounding, exact solvers | New package |
| `scripts/run_sat.sh` | Forward options + selection of new solver entry points | Original names still supported |
| `scripts/encoding_stats.py`, `scripts/experiment_matrix.py` | Reproducible formula statistics, hard wall-time benchmark | Additive |
| `tests/*`, `examples/*`, `experiments/*`, `docs/*` | Validation, small examples, size data, paper-facing documentation | Additive |

## Precise status

- `multiple_sat`: creates a fresh SAT backend at each strictly smaller peak bound; can leverage initial current solution but not learned clauses.
- `incremental_sat`: creates **one** backend, calls solve repeatedly and adds permanent PB-bound clauses (learned clauses retained on a native PySAT CDCL backend).
- `binary_sat`: rebuilds SAT with each midpoint bound; uses SAT/UNSAT to maintain an exact bracket.
- `paper_cuts`: original-paper-inspired conflict-set cuts with a persistent backend.
- Gurobi and CP-SAT solve the same validated discrete SALB3PM semantics through their own MIP/CP models; they do not consume the SAT encoding.
- `total_power` is defined explicitly as discrete integrated power (=total energy), constant across feasible schedules. An honest comparison must not claim reductions in this quantity.

## What is NOT verified in the provided environment

- Native PySAT (CaDiCaL/MapleSAT), RC2 and PBEnc performance: unavailable in the build environment.
- Gurobi/OR-Tools runtime: those dependencies or license were not available.
- Actual 1993/2013 benchmark-family optimality across all instances: no exhaustive run was made.
- E/I objective encoding benchmark comparisons should use the unchanged legacy scripts; staircase routes use the common new bounded PB encoding, not the legacy E/I encoding.
