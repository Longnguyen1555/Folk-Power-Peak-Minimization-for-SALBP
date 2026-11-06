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

For each `t`, encode `Σ_i w_i A_i,t ≤ K` using `PBEnc.atmost` (`EncType.binmerge`), with fresh auxiliary IDs. `K` starts at `best_peak−1` and is replaced by `new_best_peak−1` after an improved model. The strict cut is complete: UNSAT proves the incumbent is globally optimal since every improving schedule would satisfy all inherited feasibility constraints and the tested bound. `max_i w_i` is an unconditional lower bound; attaining it also proves optimality.

- **Multiple SAT:** solve each decision instance using a *new* SAT solver. Since `K` strictly decreases, the new bound implies all earlier peak bounds, so it is safe to build the new solver from base CNF plus the latest bound.
- **Incremental SAT:** instantiate the solver once, then append PB clauses for each stricter bound. Unique auxiliary IDs avoid variable aliasing. Native PySAT retains the CDCL engine and learned state; the offline fallback retains clauses but is NOT CDCL.
- **Paper cuts:** if a SAT model has load `≥ best_peak` at `t`, find an inclusion-minimal active task subset with weight `≥ best_peak`. Ban all its members from being simultaneously active, for **every** time slot. Every schedule improving the incumbent must satisfy that cut. Repetition to UNSAT is exact, though slower than direct PB bounds on some instances.

## Weighted MaxSAT peak formulation

With valid upper bound `U = sum of m largest task power values`, use unary Booleans `z_l` for levels `l=1,..,U`. Add soft `¬z_l` (unit cost), monotonic hard clauses `z_{l+1}⇒z_l`, and for each time `t` a hard PB inequality:

`Σ_i w_i A_i,t + Σ_{l=1}^U ¬z_l ≤ U`.

This is algebraically equivalent to `P(t)≤Σ_l z_l`. The minimum MaxSAT cost `Σ_l z_l` equals the optimal global power peak. RC2's reported cost is independently checked against the decoded schedule's actual peak. This is a (potentially sizable) **unary** peak formulation; the research contributions here are primarily the staircase feasibility representation and two SAT search workflows, not a new binary MaxSAT encoding.

## Gurobi MIP

Use one-hot station assignment `x_i,k` and start indicators `y_i,s`, each summing to one. Derive `a_i,t` from the sum of covering start indicators. Enforce station order `Σ_k k x_i,k ≤ Σ_k k x_j,k`. For each precedence arc and station:

`start_i+d_i ≤ start_j + c(2−x_i,k−x_j,k)`.

For station non-overlap, for each task pair, station, and time:

`a_i,t + a_j,t + x_i,k + x_j,k ≤ 3`.

For each time, `Σ_i w_i a_i,t ≤ Pmax`; minimize `Pmax`. This exactly models the same scheduling rules as both SAT encodings. Outputs are validated by an independent Python schedule checker.

## Energy invariant and alternative meaningful objective

With every task executed exactly once, `Σ_t P(t) = Σ_i w_i d_i`. Minimizing this number does **not** distinguish feasible schedules. Accordingly `total_energy` is always computed/reported and its objective has an explicit feasibility-only proof. Likewise `(peak,total_energy)` is equivalent to peak minimization.

A distinct optional objective `station_peak_sum = Σ_k max{w_i : k_i=k}` captures the sum of peak capacities to install per workstation, not total consumed energy. It uses a compact set of weighted thresholds over distinct input power levels. For sorted power levels `0=p_0<p_1<...<p_r`, create `H_k,p_l = [station_peak_k≥p_l]`, force `H_k,p_l` for any assignment of task power ≥`p_l` to station `k`, and penalize `H_k,p_l` by `p_l−p_{l−1}`. Then the minimal weighted sum is exactly `station_peak_sum`. The SAT variants add `PBEnc.atmost` on this weighted sum, RC2 optimizes the weighted soft negative thresholds, and Gurobi uses one nonnegative station peak variable per workstation. This objective is **not** claimed to equal total energy or the SALB3PM paper's peak criterion.

## Research protocol and known limitations

All methods must use identical `.3pm` inputs, same hardware and wall-clock cap, and an independent schedule validator. Report `OPTIMAL` separately from `TIMEOUT` with incumbent. Match results only when they are proved; report clause counts, variables, solver calls, time and memory if measured. Compare both SAT methods under each encoding and contrast against RC2/Gurobi only when actually installed and executed. The included DPLL fallback serves tiny smoke tests, not performance claims. An automatic hard cutoff is not guaranteed for RC2 under the current API wrapper. This version is based on the user-uploaded original archive, whose 430 benchmark .3pm files and original solver entry points were inspected/preserved. A new PySAT/Gurobi runtime environment remains necessary for a full performance reproduction.
