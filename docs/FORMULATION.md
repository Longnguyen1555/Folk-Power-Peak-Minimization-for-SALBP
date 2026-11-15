# Model and exactness notes

## SALB3PM

Let tasks `i=0,..,n−1` have duration `d_i∈Z+`, power `w_i∈Z+`, assigned station `k_i∈{0,..,m−1}` and integer start `s_i∈{0,..,c−d_i}`. A precedence arc `(i,j)` implies `k_i ≤ k_j` and, **if** `k_i=k_j`, `s_i+d_i ≤ s_j`. For any two tasks on the same station their execution intervals must be disjoint. At time `t`, `P(t)=Σ_i w_i*[s_i ≤ t < s_i+d_i]`.

Original objective: `min max_{t∈[0,c−1]} P(t)`.

## Staircase thresholds

`Q_i,k ↔ [k_i ≤ k]` has `m−1` variables/task and clauses `¬Q_i,k ∨ Q_i,k+1`. `B_i,t ↔ [s_i ≤ t]` has `c−d_i` variables/task, with corresponding monotonicity clauses. These increasing Boolean sequences encode an integer uniquely (including all-false = greatest value and all-true = smallest value). Thus they need no exactly-one clauses.

Define `A_i,t ↔ B_i,t ∧ ¬B_i,t−d_i`, using `B_i,t=false` for `t<0` and `B_i,t=true` for `t≥c−d_i`. The three Tseitin directions are:

1. `A ⇒ B_i,t`
2. `A ⇒ ¬B_i,t−d_i`
3. `(B_i,t ∧ ¬B_i,t−d_i) ⇒ A`.

This is an **equivalence**, not only the forward direction. Reverse linkage prevents extraneous activity signals from changing objective values.

For an arc `i≺j`, add `¬Q_j,k ∨ Q_i,k` for all station cuts `k`. For equal-station ordering, for every station `k` and successor threshold `t` (including its last forced-true threshold), add

`¬[k_i=k] ∨ ¬[k_j=k] ∨ ¬B_j,t ∨ B_i,t−d_i`.

Here `¬[k_i=k]` is a one- or two-literal clause: for internal stations, `¬Q_i,k ∨ Q_i,k−1`; end stations have a single literal. This enforces `s_i+d_i ≤ s_j` only when the tasks are on the same station. Crucially, a later-station task **may** run concurrently with its predecessor on an earlier station, as permitted by SALB3PM; blindly imposing global `s_i+d_i≤s_j` would be wrong.

For every station `k`, pair `i<j` and time `t`, add

`¬A_i,t ∨ ¬A_j,t ∨ ¬[k_i=k] ∨ ¬[k_j=k]`.

This forbids coincident processing on the same workstation while allowing concurrency across stations.

The reference encoding replaces `Q` and `B` with one-hot variables `X_i,k` and `S_i,t`, uses exactly-one + pairwise AMO and explicit incompatible-choice pairs. The two encodings define the same feasible projected schedules; tests exercise all fixed station/start combinations for a small instance.

## Tightening power using PySAT PBEnc

Multiple and Incremental SAT use a reusable binary objective circuit. With bits `e_j`, define `V = Σ_j 2^j e_j` and `M = Σ_j 2^j`. For every time slot, encode `Σ_i w_i A_i,t + Σ_j 2^j ¬e_j ≤ M` using `PBEnc.atmost` (`EncType.binmerge`). Thus `load(t) ≤ V`. Cap `V` by the valid upper bound. For `station_peak_sum`, use the weighted station-peak bank as the load instead. Build this circuit once per solver, then tighten using binary comparator clauses `V ≤ K`; no new PB auxiliaries are needed for each bound. `K` starts at `best_peak−1` and is replaced by `new_best_peak−1` after an improved model. UNSAT proves the incumbent globally optimal; reaching `max_i w_i` also proves optimality.

- **Multiple SAT:** rebuild feasibility CNF and the objective circuit, then create a *new* SAT solver for each bound. Since `K` strictly decreases, only the latest bound is needed. Encoding rebuild time is included in elapsed time.
- **Incremental SAT:** instantiate the solver and objective circuit once, then permanently append comparator clauses for each stricter bound. Native PySAT retains the CDCL engine and learned state. This follows the uploaded Sudoku project's reusable-counter/permanent-bound idea; Sudoku's Multiple uses binary search with temporary assumptions, which is deliberately not adopted here, following the user's selected semantics. Power weights are represented in binary rather than replicated as totalizer inputs.
- **Paper cuts:** if a SAT model has load `≥ best_peak` at `t`, find an inclusion-minimal active task subset with weight `≥ best_peak`. Ban all its members from being simultaneously active, for **every** time slot. Every schedule improving the incumbent must satisfy that cut. Repetition to UNSAT is exact, though slower than direct PB bounds on some instances.

Binary SAT uses the same binary objective circuit with a comparator for each midpoint. PySAT CaDiCaL uses repeated conflict-budget slices on the same solver to check the deadline, since its interrupt API is unsupported; CaDiCaL195 is the only SAT backend, with no alternate solver or DPLL fallback. A conflict slice is not a hard wall-clock limit: use the supervised subprocess runner for externally enforced cutoffs.

## Binary weighted MaxSAT

Build the same binary objective circuit `load(t) <= V`, with `V = sum_j 2^j e_j`.
The hard CNF contains feasibility, the PB circuit and the upper-bound comparator.
For each bit, add the soft unit clause `not e_j` with weight `2^j`. The MaxSAT cost
is exactly V; minimization makes it equal to the actual global peak. For
`station_peak_sum`, bound the weighted station-capacity bank by V and penalize
the same binary bits. RC2's cost is checked against the decoded schedule.

Only RC2 with CaDiCaL195 is used. Original MSAT-E binary export, including its
reduction rules, lives in `salb3pm/paper.py`; the shared model lives in
`salb3pm/cnf.py`. These are distinct feasibility formulations with the same
SALB3PM objective. Paper export normalizes the lower bound to `max(w_i)`, uses
`upper.bit_length()` bits and explicitly selects Binary Merger. The I/unary
variant has been removed.

## Gurobi MIP

Use one-hot station assignment `x_i,k` and start indicators `y_i,s`, each summing to one. Derive `a_i,t` from the sum of covering start indicators. Enforce station order `Σ_k k x_i,k ≤ Σ_k k x_j,k`. For each precedence arc and station:

`start_i+d_i ≤ start_j + c(2−x_i,k−x_j,k)`.

For station non-overlap, for each task pair, station, and time:

`a_i,t + a_j,t + x_i,k + x_j,k ≤ 3`.

For each time, `Σ_i w_i a_i,t ≤ Pmax`; minimize `Pmax`. This exactly models the same scheduling rules as both SAT encodings. Outputs are validated by an independent Python schedule checker.

## Energy invariant and alternative meaningful objective

With every task executed exactly once, `Σ_t P(t) = Σ_i w_i d_i`. Minimizing this number does **not** distinguish feasible schedules. Accordingly `total_energy` is always computed/reported and its objective has an explicit feasibility-only proof. Likewise `(peak,total_energy)` is equivalent to peak minimization.

A distinct optional objective `station_peak_sum = Σ_k max{w_i : k_i=k}` captures the sum of peak capacities to install per workstation, not total consumed energy. It uses a compact set of weighted thresholds over distinct input power levels. For sorted power levels `0=p_0<p_1<...<p_r`, create `H_k,p_l = [station_peak_k≥p_l]`, force `H_k,p_l` for any assignment of task power ≥`p_l` to station `k`, and weight it by `p_l−p_{l−1}`. The minimal weighted sum is exactly `station_peak_sum`. SAT and RC2 bound this weighted sum by a binary objective V; SAT tightens V and RC2 optimizes its bit costs. Gurobi uses one nonnegative station peak variable per workstation. This objective is **not** claimed to equal total energy or the SALB3PM paper's peak criterion.

## Research protocol and known limitations

Use identical input instances, a fixed machine and independent schedule validation.
SAT and MaxSAT use CaDiCaL195 exclusively; PB clauses use Binary Merger. Gurobi
and CP-SAT retain their native engines and run on one thread/worker. Report
OPTIMAL separately from TIMEOUT with an incumbent. In-process RC2 has only an
advisory time limit; CaDiCaL checks deadlines between conflict-budget slices.
Use the isolated subprocess runner for externally enforced cutoffs.

The source is split into `backends.py`, `results.py` and the `solvers/` package;
`from salb3pm.solvers import solve` remains the public dispatcher. `cnf_clauses`
for descending Multiple/Incremental is cumulative emitted clauses, including
rebuilt base circuits in Multiple. Binary SAT reports the maximum loaded formula
size. Do not compare these statistics as if all were peak memory measurements.
Regenerate historical result files after changing backends or formulations.
