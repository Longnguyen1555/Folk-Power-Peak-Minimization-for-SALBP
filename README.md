# Folk-Power-Peak-Minimization-for-SALBP
Optimizing Power Peaks in Simple Assembly Line Balancing

## Multiple SAT and Incremental SAT

Both methods optimize the maximum power peak of a `.3pm` instance using a
single persistent SAT solver. They follow the search ideas in
[SAT_Sudoku_Solver](https://github.com/Longnguyen1555/SAT_Sudoku_Solver/blob/782e5ae5b0b7cfbe90d14d232bbfbef67f753654/main.py),
adapted to SALB3PM's existing objective and constraints:

- **Multiple SAT** performs binary search on the peak. Each trial bound is
  temporary and activated through `solve(assumptions=...)`, so an UNSAT trial
  can be followed by a larger bound without rebuilding the solver.
- **Incremental SAT** first finds a feasible schedule, then permanently adds
  `peak <= incumbent_peak - 1` and solves again. It stops when the tighter
  bound is UNSAT or the incumbent reaches a proven lower bound.

These methods reuse the original `*-BS-I.py` / `*-BS-E.py` encoding functions,
including task assignment, capacity, start times, precedence, non-overlap,
power constraints, and the optional precedence/long-task reductions. Each run
loads a fresh encoding module to isolate its variable pool and reduction state.
The existing solver files are unchanged.

| Objective | Bound implementation |
| --- | --- |
| I (Inaugural) | Original monotone unary `E[1..ub]`; `-E[k+1]` enforces `peak <= k`. |
| E (Enhanced) | Original binary `E` variables; `PBEnc.leq` encodes the bound. Multiple SAT guards each bound with a fresh assumption selector. |

The Sudoku preference totalizer and greedy clue preferences are not needed:
the original SALB3PM objective variables already represent the power bound.
The lower bound is `max(max(W), ceil(sum(T[j] * W[j]) / c))`. The initial
upper bound is the sum of the largest `min(m, n)` powers, since at most one
task per workstation can execute at a time. A feasible schedule is obtained
before reporting an optimum, even when the bounds coincide.

### Installation

```sh
python -m pip install -r requirements.txt
```

The SAT/PB solvers require PySAT with the `pblib` extra. The dependency range
keeps the PySAT 1.8 PBLib backend used by the original encodings; PySAT 1.9
changes that backend. If a PBLib wheel is unavailable for your Python/platform,
installation requires a C++ build environment. Validation on Windows used
Python 3.9, `python-sat==1.8.dev30`, and `pypblib==0.0.4`.

### Running

Run an entry point directly on Windows or Linux:

```sh
python solvers/SAT_based/Cadical-Multiple-E.py examples/small_example.3pm
python solvers/SAT_based/Cadical-Incremental-E.py examples/small_example.3pm
python solvers/SAT_based/Maplesat-Multiple-I.py examples/small_example.3pm
python solvers/SAT_based/Maplesat-Incremental-I.py examples/small_example.3pm
```

All eight combinations are available:

| Backend | Multiple SAT | Incremental SAT |
| --- | --- | --- |
| CaDiCaL 1.9.5 | `Cadical-Multiple-I.py`, `Cadical-Multiple-E.py` | `Cadical-Incremental-I.py`, `Cadical-Incremental-E.py` |
| MapleSAT | `Maplesat-Multiple-I.py`, `Maplesat-Multiple-E.py` | `Maplesat-Incremental-I.py`, `Maplesat-Incremental-E.py` |

The entry points accept the same reduction flags as the original SAT solvers:
`--precedence_constraint`, `--no-precedence_constraint`,
`--long_task_constraint`, and `--no-long_task_constraint`. Both reductions are
enabled by default. Disabling a reduction still keeps the actual precedence
and scheduling constraints.

On systems with Bash and GNU `timeout`, the existing runner supports the new
methods and applies its existing 7200-second process limit:

```sh
bash scripts/run_sat.sh examples/small_example.3pm cadical-multiple-e
bash scripts/run_sat.sh examples/small_example.3pm cadical-incremental-e
bash scripts/run_sat.sh examples/small_example.3pm maplesat-multiple-i
bash scripts/run_sat.sh examples/small_example.3pm maplesat-incremental-i
```

Omitting the solver name runs all original and new SAT entry points. Direct
Python entry points, like the original SAT scripts, have no internal time limit.

Results preserve the existing `new W`, `Transformation time`, `nb_var`,
`nb_cons`, and `### Benchmark ... OPT ... TotTime ... RealTime ...` markers,
and add an explicit status and SAT call count. Clause/variable counts include
objective bounds added during search. An infeasible instance reports
`INFEASIBLE` without an `OPT` value. Every accepted schedule is checked for
assignment, timing, non-overlap and precedence, and its actual peak is computed.
The sample instance has optimal peak **8**.

### Tests

```sh
python -m unittest discover -s tests -v
```

Tests cover all eight configurations against independent exhaustive scheduling
on small deterministic instances, with reductions enabled/disabled; infeasible
packing, cyclic precedence, zero powers, equal bounds, solver reuse, isolated
repeated runs, temporary-bound relaxation after UNSAT, permanent-bound behavior,
and all command-line entry points. The tests only need the SAT/PB dependencies.
