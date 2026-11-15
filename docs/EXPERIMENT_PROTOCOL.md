# Experiment protocol

Compare Multiple SAT, Incremental SAT, Binary SAT, paper cuts, binary MaxSAT,
Gurobi and CP-SAT on identical `.3pm` instances. SAT and RC2 use CaDiCaL195;
PB clauses use Binary Merger. Retain pairwise/staircase feasibility ablations.
Original MSAT-E binary exports are a separate baseline from the shared CNF.
The current backend policy follows the user's CaDiCaL-only choice, so it does
not reproduce EvalMaxSAT performance tables from the paper.

## Running

The focused default is now `configs/matrix_1993.json`: all local 1993 instances,
Multiple/Incremental/MaxSAT x pairwise/staircase, 30 seconds. Run
`PYTHON=python bash scripts/run_matrix.sh`; add `--dry-run` to inspect the grid.
See [RUN_MATRIX.md](RUN_MATRIX.md) for configuration and result fields.

```powershell
python scripts/experiment_matrix.py "benchmarks/1993/MERTENS-*.3pm" --time-limit 3600 --repeat 3 --out experiments/current.csv
python scripts/encoding_stats.py "benchmarks/1993/MERTENS-*.3pm" --out experiments/current_sizes.csv
```

Use the isolated runner for hard termination: its subprocess cap is the requested
time including startup, without extra grace. Direct CLI/benchmark calls do not
provide a hard cutoff for RC2. CaDiCaL checks deadlines between conflict-budget
slices, which also cannot guarantee immediate wall-clock termination. When a
subprocess is killed, the latest published counts and incumbent peak are retained;
the full incumbent schedule is not recovered.
Gurobi and CP-SAT use one thread/worker and retain their native engines.

## Recording and comparing

Record machine/OS/RAM, Python, PySAT, CaDiCaL, PBLib, OR-Tools and Gurobi versions,
license limits, repository commit and dataset provenance. Use at least three
repetitions under the same resource limits. Verify all schedules independently;
separate OPTIMAL, INFEASIBLE, TIMEOUT and UNAVAILABLE. A feasible timeout result
is not proof of optimality. In-process elapsed time includes encoding; subprocess
wall time also includes interpreter startup.

Record objective, value, elapsed time, solver calls/instances, backend and proof.
CSV `clauses` is now the maximum loaded input-formula count, from the new
`cnf_peak_clauses` field; MaxSAT includes hard and soft clauses. Raw JSON's legacy
`cnf_clauses` counter is cumulative for Multiple/Incremental and is not directly
comparable to maximum loaded size. Measure process memory separately; these
counts exclude learned clauses and RC2 internal counters. Base encoding statistics do
not include objective clauses. Native models use encoding=native.

Report solved-to-optimal counts, shared-optima runtime comparisons, timeout rates
and PAR-2 with a stated cutoff. Preserve unresolved runs and license failures.
Total energy is schedule invariant; station_peak_sum is installed station capacity,
not consumed energy. Existing CSVs and audit notes describe earlier code versions
and cannot establish current solver performance. Regenerate them before reporting.
The original benchmark files and UPSTREAM_MANIFEST.json remain provenance records;
the manifest describes the uploaded original tree, not today's refactored sources.
