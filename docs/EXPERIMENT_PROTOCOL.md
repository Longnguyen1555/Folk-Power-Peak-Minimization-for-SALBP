# Experimental protocol for Assignment 2

This implementation is a starting point for a scientific report, not evidence of large-instance performance. The course requirements ask for SAT/MaxSAT, PySAT pseudo-Boolean encoding, comparison to exact mathematical solvers such as Gurobi, experiments with large benchmark instances, and transparent GitHub/data availability.

## Questions / ablations

1. For fixed method and instance, does staircase vs pairwise reduce **base feasibility** CNF variables/clauses? Does that yield lower wall-clock time, peak RSS, and timeout rate after objective PB clauses are included?
2. For fixed staircase encoding and PB encoding, does persistent incremental SAT improve time relative to independent SAT calls (same solver, version, phase heuristic, seed and wall-clock limit)?
3. How do `paper_cuts`, RC2 MaxSAT and Gurobi compare in time, solution value, and number of instances *proved optimal* under the same budget?
4. Are all `total_energy` values identical across feasible schedules, as guaranteed mathematically? Do `station_peak_sum` and global peak trade off on selected instances? **Do not** call station peak sum total energy.

## Benchmark design

Use at least three sizes/families from recognized SALB3PM datasets, including benchmark `.3pm` files. Fix and record the source commit/hash of every dataset; preserve original energy weights rather than regenerate silently. Before solving, check that `m`, `c`, and each `d_i` are valid, that the precedence DAG is well formed, and that the instance is not trivially infeasible.

For each instance/solver, run at least three repetitions on the same isolated machine; record CPU model, operating system, RAM, PySAT, CDCL backends, RC2, Gurobi and Python versions, Gurobi academic/commercial license availability, random seeds, and all solver options. A wall-clock cap of 3,600 s (or instructor-agreed budget) should be applied consistently. The current RC2 wrapper has **advisory only** wall-time limit; for enforceable research-level RC2 timeouts invoke each solver in a supervised subprocess with an OS-level timeout (and preserve partial results if possible).

Use `python scripts/experiment_matrix.py 'benchmarks/1993/MERTENS-*.3pm' --time-limit 3600 --repeat 3` for capped per-process runs. `python scripts/encoding_stats.py` generates size-only ablations without solving. Each run must be verified by the independent validator, and mismatched objective values investigated before analysis.

Record: `status` (OPTIMAL / TIMEOUT / INFEASIBLE / UNAVAILABLE), incumbent `peak`, invariant `total_energy`, optional `station_peak_sum`, elapsed time, iterations, counts of CNF variables/clauses, and hardware metadata. The current `cnf_clauses` in repeated SAT searches is the **cumulative clauses emitted** (not necessarily peak loaded CNF size); `cnf_vars` is the maximum allocated ID. For fair formula-size comparison report base CNF and largest/current solver CNF separately using extended instrumentation.

## Research reporting

Prepare a table of solved-to-optimal counts by family, median runtime on shared optima, PAR-2 with timeouts, CNF variable/constraint counts, and memory use if measured with an external process monitor. Plot **paired** staircase/pairwise ratios, with the same instance, solver and bound strategy on both sides. Do not interpret a small sample or two reference examples as statistically representative. Include a `Data Availability` paragraph with the uploaded base archive SHA-256 from `UPSTREAM_MANIFEST.json`, benchmark source and the eventual public Git commit. The base repository was directly inspected in this version; the separate Sudoku reference repository was not fetched in this environment.

## Local smoke results (NOT a speed benchmark)

Environment: this file-authoring environment had no `python-sat` or `gurobipy`. The SAT workflows were run using the educational DPLL fallback, not CaDiCaL/Glucose. The two textbook instances have certified objective values `10` (Py 2024 example) and `9` (ICTAI example) across staircase and pairwise. Base CNF size:

| Example | Encoding | Boolean variables | CNF clauses |
|---|---|---:|---:|
| Py 2024 (4 tasks) | pairwise | 43 | 254 |
| Py 2024 (4 tasks) | staircase | 35 | 168 |
| ICTAI 2024 (4 tasks) | pairwise | 44 | 277 |
| ICTAI 2024 (4 tasks) | staircase | 36 | 173 |

`experiments/smoke_comparison.csv` contains run-level fallback outputs for transparency; **do not include its timings as published SAT/Gurobi comparisons**.
