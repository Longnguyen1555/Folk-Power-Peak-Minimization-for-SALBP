# Full solver matrix

Run from the repository root in Bash / Git Bash:

```bash
python -m pip install -r requirements.txt -r requirements-exact.txt
python scripts/install_roundingsat.py
PYTHON=python bash scripts/run_matrix_all.sh --dry-run
PYTHON=python bash scripts/run_matrix_all.sh
```

The separate configuration [matrix_all_1993.json](../configs/matrix_all_1993.json)
runs all 130 local 1993 instances with a **30-second hard wall-clock budget per run**.

| Methods | Encodings | Runs per instance |
|---|---|---:|
| Multiple SAT, Incremental SAT, Binary SAT, Paper Cuts, MaxSAT, PB | pairwise and staircase | 12 |
| CPLEX MIP, Gurobi MIP, OR-Tools CP-SAT | native | 3 |
| Total | | 15 |

There are **1,950 runs**, written immediately to
`experiments/matrix_all_1993_30s.csv`. SAT uses CaDiCaL195; MaxSAT uses RC2 with
CaDiCaL195. PB uses RoundingSAT on OPB with binary objective bits and native
weighted inequalities. CPLEX and Gurobi share the same time-indexed MIP model.
Native models run once per instance because the SAT precedence encoding does not
apply to them. The original focused matrix remains available in `run_matrix.sh`.

Edit the JSON to change dataset, methods, encodings, objective, time limit,
repetitions, output path or resume behavior. CLI options override the JSON:

```bash
# Only the three added families.
PYTHON=python bash scripts/run_matrix_all.sh \
  --methods cplex gurobi pb --time-limit 60 \
  --out experiments/cplex_gurobi_pb_60s.csv

# A different dataset/configuration.
PYTHON=python bash scripts/run_matrix_all.sh configs/my_matrix.json

# PowerShell equivalent, without Bash.
python -u scripts/experiment_matrix.py --config configs/matrix_all_1993.json
```

CPLEX and Gurobi need suitable licenses for larger models. Community/restricted
licenses may solve small examples but reject benchmark models. Missing engines,
license errors and invalid output are recorded as **Error**, never UNSAT or a
replacement solver. `ROUNDINGSAT_BIN` can select an existing RoundingSAT binary;
otherwise PATH and `tools/roundingsat` are searched. The installer downloads an
official platform binary and records its URL and SHA-256 in `SOURCE.json`.

Console and CSV include Runtime, Variables, Clauses, Constraints and Status.
Clauses are input CNF/WCNF counts for SAT/MaxSAT; native MIP/CP/PB models show N/A
in that column and report their input constraints separately. Native counts are
not directly comparable to CNF counts. Runtime includes startup and model build.
SAT denotes a completed optimum; Timeout incumbents are not certified. Raw status,
proof and `optimality_proven` remain in the CSV. Counts published before a timeout
are retained. The runner terminates descendant processes, including RoundingSAT.

Re-running resumes existing rows, including Timeout/Error rows. Use a new output
path after changing code/data or to retry failures. Earlier CSV schemas require a
new output path. Do not run multiple writers against the same CSV.
