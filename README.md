# Power Peak Minimization for SALBP

Exact comparison of Multiple SAT, Incremental SAT, Binary SAT, paper cuts,
binary MaxSAT, native PB/RoundingSAT, CPLEX MIP, Gurobi MIP and OR-Tools CP-SAT on the same `.3pm` instances.
All SAT calls use **PySAT CaDiCaL195**. MaxSAT uses **RC2 with CaDiCaL195**.
There is no automatic switch to another SAT backend.

## Install and run

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-enhanced.txt
python -m salb3pm solve examples/small_example.3pm --method incremental_sat
python -m salb3pm solve examples/small_example.3pm --method multiple_sat
python -m salb3pm solve examples/small_example.3pm --method maxsat
python -m pytest
```

Gurobi needs `gurobipy` and a working license. Gurobi and CP-SAT retain their
native engines; CaDiCaL is the sole SAT oracle, not a replacement for MIP/CP.

## Source layout

For the full configurable matrix (including CPLEX, Gurobi and PB), see
[RUN_MATRIX_ALL.md](docs/RUN_MATRIX_ALL.md):

```bash
python -m pip install -r requirements-exact.txt
python scripts/install_roundingsat.py
PYTHON=python bash scripts/run_matrix_all.sh --dry-run
PYTHON=python bash scripts/run_matrix_all.sh
```

```text
salb3pm/
  cli.py               solve / benchmark / encoding-stats / export
  model.py             instance parser and independent schedule validator
  cnf.py               pairwise/staircase feasibility and binary PB objective
  backends.py          CaDiCaL195 lifecycle and deadline polling
  results.py           objective names and shared result schema
  paper.py             original MSAT-E binary formulation and reduction rules
  export.py            binary WCNF / OPB writers
  solvers/
    __init__.py        public solve() dispatcher
    sat.py             Multiple, Incremental, binary search and paper cuts
    maxsat.py          binary weighted RC2 / CaDiCaL
    mip.py             shared time-indexed MIP formulation
    gurobi.py          Gurobi adapter
    cplex.py           CPLEX adapter
    pb.py              native OPB / RoundingSAT adapter
    cpsat.py           direct .3pm CP-SAT model
solvers/               CLI shortcuts and external .lp adapters, grouped by family
scripts/               isolated benchmark runner and encoding statistics
tests/                 correctness, solver lifecycle, CLI and export checks
benchmarks/            original benchmark inputs
```

`from salb3pm.solvers import solve` remains the public Python API. The old
monolithic `salb3pm/solvers.py` is replaced by the package above. MapleSAT,
inaugural/unary I variants, duplicate E/I SAT implementations, the DPLL fallback
and the selectable `--solver` option have been removed. Use the four named SAT
shortcuts in `solvers/SAT_based/` instead of the old `Cadical-*` scripts.

## Methods and encodings

- `multiple_sat`: rebuild the full CNF and create a fresh solver at each strictly smaller bound.
- `incremental_sat`: build one CNF/objective circuit and permanently append tighter-bound clauses.
- `binary_sat`: binary search, with a fresh solver for each midpoint decision.
- `paper_cuts`: repeatedly forbid overload task sets on one persistent solver.
- `maxsat`: minimize weighted binary objective bits with RC2/CaDiCaL.
- `pb`: native weighted OPB optimization with RoundingSAT.
- `gurobi`, `cplex`, `cpsat`: native mathematical models, reported with `encoding=native`.

`--encoding pairwise|staircase` selects the feasibility/precedence representation.
Both are retained for comparisons. **Binary** describes the objective bits and
is separate from this choice. PB constraints use Binary Merger. Internally,
PySAT RC2 may create its own cardinality counters; these are not alternate
SALB3PM objective formulations.

The default objective is `peak`. `total_energy` is schedule invariant, so its
optimization reduces to feasibility. `station_peak_sum` is a separate capacity
objective, not consumed energy. See [the formulation](docs/FORMULATION.md).

## Binary export

```powershell
python -m salb3pm export examples/small_example.3pm output/shared.wcnf
python -m salb3pm export examples/small_example.3pm output/paper.wcnf --formulation paper
python -m salb3pm export examples/small_example.3pm output/paper.opb --formulation paper
```

`shared` uses the common pairwise/staircase formulation. `paper` retains the
original MSAT-E feasibility constraints and reduction rules, with Binary Merger,
`max(w_i)` as lower bound and the minimum binary bit count. OPB translates the
same hard CNF clauses and binary bit costs; it is not a separate native-PB model.
`MSAT-E.py` and `PBO-E.py` are export-only shortcuts taking input and output paths.
Use `RC2-SALB3PM.py` or `--method maxsat` to solve the shared binary model.

## Reproducible experiments

The default focused matrix uses `benchmarks/1993` (130 instances), Multiple SAT,
Incremental SAT and binary MaxSAT, each with pairwise/staircase and a 30-second
limit: **780 runs**. Edit [matrix_1993.json](configs/matrix_1993.json), or override
its options on the CLI. See [RUN_MATRIX.md](docs/RUN_MATRIX.md) for output definitions.

```bash
PYTHON=python bash scripts/run_matrix.sh --dry-run
PYTHON=python bash scripts/run_matrix.sh
```

Console/CSV output includes Runtime, Variables, Clauses and SAT/UNSAT/Timeout,
with the raw optimization status and proof retained separately in CSV.

For the focused three-SAT matrix on a separately supplied original 97-instance
dataset, see [SAT_PAPER97.md](docs/SAT_PAPER97.md):

```bash
bash scripts/run_sat_paper97.sh /path/to/original_97_instances 3600 1
```

```powershell
python scripts/experiment_matrix.py "examples/*.3pm" --time-limit 30 --out experiments/current.csv
python scripts/encoding_stats.py "examples/*.3pm" --out experiments/current_sizes.csv
```

The isolated runner enforces an external timeout including process startup,
without extra startup grace. In-process RC2 has only an advisory limit. CaDiCaL polls deadlines
between conflict-budget slices, so it also needs external supervision for hard
cutoffs. Gurobi and CP-SAT use one thread/worker. Existing historical results were
produced by earlier implementations and should be regenerated after this refactor.
See [the experiment protocol](docs/EXPERIMENT_PROTOCOL.md).
