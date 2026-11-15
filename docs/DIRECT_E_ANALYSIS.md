# Direct-E applicability to SALB3PM

Read-only analysis, 2026-11-14. Reference branch `journal-compact-objectives`,
commit `6cc100c5be92775a086e44baf952c4ba2f7dd002` in
[Business-Meeting-Scheduling-Problem](https://github.com/Longnguyen1555/Business-Meeting-Scheduling-Problem/tree/6cc100c5be92775a086e44baf952c4ba2f7dd002).
No production encoder or solver was changed for this analysis.

## What Direct-E means in the reference

`src/Main.py` labels the graph factor G as `Direct-E` for `precedence_graph=direct`,
and `DistanceClosure-E*` otherwise. `src/B2B_Instance.py` selects the input edges
with unit distance for Direct-E; the other branch selects every reachable pair
with its longest path distance. This is independent of pairwise versus sparse
suffix encoding P, and also independent of the objective-compactness factor C.
The domain-filter graph F is a separate choice: Filter-E and Filter-E* do not
mean the same thing as the graph selected for CNF emission.

## Current SALB3PM already uses the input graph

Both pairwise and staircase branches in `salb3pm/cnf.py` iterate directly over
`instance.precedence`. `model.py` checks acyclicity but does not replace those
edges by closure. Thus the defining Direct-E choice is already present in both
encodings and is shared by Multiple SAT, Incremental SAT and RC2 MaxSAT.
Turning on a flag named Direct-E would not create a new algorithmic cell.
The current binary objective circuit is a different layer and is unaffected.

## Exactness and the important semantic difference

B2B's precedence is global and unit-duration: `time(i)+1 <= time(j)`.
SALB3PM's precedence is instead:

1. `station(i) <= station(j)`;
2. only if the stations coincide, `start(i)+duration(i) <= start(j)`.

For a path `i -> k -> j`, station inequalities imply `station(i) <= station(j)`.
If the endpoints have equal station, all intermediate stations must also equal
that station. The path then implies the endpoint temporal order, with the sum of
processing durations along the path. Consequently direct-edge constraints
already imply the ordinary endpoint precedence of every reachable pair.

Do not copy B2B's global `start(i)+path_distance <= start(j)` constraint. For three
tasks of duration 2, cycle 2, stations `(0,1,2)` and chain `0 -> 1 -> 2`, starts
`(0,0,0)` form a valid SALB3PM schedule. A global time-distance constraint would
incorrectly reject it. A future weighted closure would need guarded same-station
conditions and processing-time distances; unit edge counts do not express those
processing-time bounds. Closure is redundant for feasibility, though selected
valid implied constraints may help SAT propagation and must be benchmarked.

## Current 1993 graph audit

| Quantity | Measured value |
|---|---:|
| Instances | 130 |
| Input edges, also unique input edges | 4,480 |
| Reachable pairs in strict transitive closure | 53,450 |
| Edges after exact DAG transitive reduction | 4,440 |
| Instances with removable edges | 20 |

The affected instances are all ten GUNTHER and all ten LUTZ2 variants.
Transitive reduction removes 40/4,480 edges, approximately 0.89% overall. These
are graph counts, not measured CNF or runtime reductions. Direct-E avoids a much
larger closure relative to a hypothetical closure baseline, but the existing
implementation is already using Direct-E.
In the current shared encoder, station/start/activity variables are allocated
independently of the edge list and precedence clauses introduce no per-edge
auxiliary variables. Graph reduction therefore targets precedence clauses;
it does not itself reduce those variable families or the binary objective bits.

The graph audit checks that reduction preserves reachability on all 130 inputs.
It additionally exhaustively compares schedule feasibility before/after reduction
on three small cases, including a case with predecessors running concurrently
on distinct stations. Reproduce with `python tmp/direct_e_graph_audit.py`;
per-instance evidence is in `tmp/direct_e_graph_audit.json`.

## Recommended next experiment

Preserve the present direct-input graph as baseline. If implementing graph
reduction, call it `transitive_reduction`, rather than relabel it Direct-E.
Keep graph selection independent from pairwise/staircase and objective encoding.
Start with the 20 affected instances: 20 x 3 methods x 2 encodings x 2 graph
choices = 240 runs at the same 30-second limit. Check peak optima, independent
schedule validity, input CNF counts, runtime and timeout rate. No runtime gain
has been measured yet, and the small edge reduction makes it a modest candidate.

Larger opportunities suggested by the B2B design are exact reduced domains,
demand-driven threshold states and shared sparse precedence predicates. They
need SALB3PM-specific proofs because assignment/start domains interact with
activity and same-station non-overlap. They should be evaluated as separate
factors, without changing the binary objective or the incumbent baseline.
