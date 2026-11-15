# Configurable SAT / MaxSAT matrix

Run from the repository root in Bash or Git Bash:

```bash
PYTHON=python bash scripts/run_matrix.sh
```

The defaults in [matrix_1993.json](../configs/matrix_1993.json) are:

| Setting | Default |
|---|---|
| Dataset | all 130 `.3pm` files under `benchmarks/1993` |
| Methods | Multiple SAT, Incremental SAT, binary MaxSAT |
| Encodings | pairwise, staircase |
| SAT oracle | CaDiCaL195; MaxSAT uses RC2/CaDiCaL195 |
| Objective | peak |
| Time limit | 30 seconds per subprocess |
| Repetitions | 1 |
| Runs | 130 x 3 x 2 = 780 |

This uses the local 130-instance set, without applying the earlier paper97 checks.
The launcher does not start automatically when the source is edited.

Edit the JSON to change `datasets`, `methods`, `encodings`, `time_limit`, `repeat`,
`objective`, `out` or `resume`. Dataset entries may be directories, files or quoted
glob patterns. Paths are relative to the repository root when using the launcher.
On Linux use `PYTHON=python3`, or select a virtualenv interpreter explicitly.

```bash
# Preview the full matrix without running or writing results.
PYTHON=python bash scripts/run_matrix.sh --dry-run

# Override selected fields without editing the JSON.
PYTHON=python bash scripts/run_matrix.sh \
  --datasets benchmarks/2013 \
  --methods multiple_sat incremental_sat maxsat \
  --encodings staircase --time-limit 60 \
  --out experiments/matrix_2013_60s.csv

# Load another configuration file.
PYTHON=python bash scripts/run_matrix.sh configs/my_matrix.json

# Equivalent Python command, also usable in PowerShell.
python -u scripts/experiment_matrix.py --config configs/matrix_1993.json
```

The console prints these columns for every completed run:

```text
Instance          Method          Encoding  Run  Runtime(s)  Variables  Clauses  Constraints  Status
```

- **Runtime:** wall-clock seconds measured by the parent, including interpreter
  startup, input/encoding, and solving. Hard termination occurs at the configured
  budget without startup grace; process cleanup may add a small observed delay.
- **Variables:** highest allocated variable ID in the input CNF/objective circuit,
  or the number of variables in a native model.
- **Constraints:** input PB/MIP/CP constraints for native models (Clauses is N/A).
- **Clauses:** maximum simultaneously loaded input-clause count for a SAT solver,
  rather than all clauses emitted over Multiple's repeated rebuilds. Incremental
  includes its accumulated permanent bound clauses. MaxSAT includes hard and soft
  input clauses. Learned clauses and RC2's internal optimization counters are not
  included in these input-formula statistics.
- **Status:** SAT for completed optimal feasible runs, UNSAT for infeasible input
  instances, Timeout if the budget expires. The UNSAT bound proving an incumbent
  optimal does not make the original instance UNSAT. Environment/runtime failures
  remain Error, with their cause in `message`.

The CSV stores `runtime_s`, `variables`, `clauses`, `status`, plus raw
`solver_status`, `optimality_proven`, incumbent `peak`, backend and proof. This
preserves the distinction between a valid incumbent and a certified optimum.
Raw solve JSON still retains the legacy `cnf_clauses` counter and now additionally
provides `cnf_peak_clauses`; the matrix uses the latter.

The child publishes input-formula statistics during optimization. A killed run
retains the latest available counts and incumbent objective. If it times out
before encoding publishes statistics, Variables/Clauses display N/A and the CSV
cells are empty; these are not fabricated zero counts. Full incumbent schedules
are not recovered from a killed child.

The default output is `experiments/matrix_1993_sat_maxsat_30s.csv`. Each row is
flushed immediately. Re-running the same command with `resume=true` skips
recorded combinations, including recorded timeouts. Use a new output file after
changing solver code/data or to repeat a timed-out run. Earlier CSV schemas are
not silently converted or overwritten. Do not run concurrent writers to one CSV.
