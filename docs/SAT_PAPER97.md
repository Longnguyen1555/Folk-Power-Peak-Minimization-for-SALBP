# SAT matrix for the 97-instance ICTAI 2024 dataset

The current `benchmarks/1993` contains 130 instances with different parameters.
It is not the paper's 97-instance test set. No arbitrary subset is selected.
Provide the original 97 `.3pm` files in a separate directory, retaining instance
names, durations, powers, station/cycle parameters and precedence relations.

From the repository root, run:

```bash
bash scripts/run_sat_paper97.sh /path/to/original_97_instances 3600 1
```

The configuration matrix is:

| Method | Pairwise | Staircase |
|---|---|---|
| Multiple SAT | yes | yes |
| Incremental SAT | yes | yes |
| Binary SAT | yes | yes |

All use CaDiCaL195, binary objective circuits and objective `peak`.
One repetition gives **97 x 3 x 2 = 582 runs**. Three repetitions give 1,746.
Each run has a 3,600-second subprocess budget including startup. Worst-case sequential duration for
one repetition is approximately 582 hours, so start with a short pilot if needed.

Optional parameters:

```bash
# Use an installed Python/venv; record the original source URL/archive.
PYTHON=python PAPER97_SOURCE='original dataset URL or archive ID' \
  bash scripts/run_sat_paper97.sh /path/to/original_97_instances 3600 3 experiments/sat97.csv

# Short pilot on the same complete matrix, stored separately.
bash scripts/run_sat_paper97.sh /path/to/original_97_instances 60 1 experiments/sat97_pilot.csv
```

The launcher checks exactly 97 uniquely named files and the nine `(n,m,c)`
records published in Table II, then writes a SHA-256 manifest alongside the CSV.
These checks catch the known 130-instance mismatch but cannot authenticate all
random power weights: retain the original dataset source as provenance. Files
with renamed or changed published parameters are rejected.

Results are flushed after every completed run. Re-running the same command
skips recorded runs and continues missing combinations. A killed subprocess is
recorded as Timeout with the latest published counts/peak when available. Interrupting the whole
runner leaves the active combination unrecorded and it will run again on resume.
Do not run two processes writing the same CSV concurrently. Use a new output
path after changing solver code or the dataset.

The equivalent underlying matrix command is:

```bash
python3 -u scripts/experiment_matrix.py \
  --manifest experiments/sat_paper97_3600s_r1.instances.json \
  --methods multiple_sat incremental_sat binary_sat \
  --encodings pairwise staircase \
  --objective peak --time-limit 3600 --repeat 1 --resume \
  --out experiments/sat_paper97_3600s_r1.csv
```

The supplied repository does not currently include an authenticated 97-instance
dataset. The launcher intentionally stops rather than benchmark an unrelated
set under the paper's name. Creating this command does not start the long run.

## Checked original SALBP links

The user-supplied links were checked on 2026-11-14, including the ZIP contents:

- [Scholl 1993](https://assembly-line-balancing.de/salbp/benchmark-data-sets-1993/):
  `SALBP-data-sets.zip` contains 27 files: 25 `.IN2` precedence-graph/task-time
  files, a README and a spreadsheet of SALBP configurations. It does not supply
  the 97 converted `.3pm` files or their generated task powers.
- [Otto et al. 2013](https://assembly-line-balancing.de/salbp/benchmark-data-sets-2013/):
  `SALBP_benchmark.zip` contains nested dataset ZIPs and descriptive spreadsheets.
  The small `n=20` ZIP contains 525 `.alb` files. A sample includes number of
  tasks, cycle time, order strength, task times and precedence, without task powers.

The ICTAI paper derives SALB3PM from the 1993 source and generates task powers
from U(5,50). The source data alone do not recover the exact random powers or the
complete 97-instance selection. Do not invent a seed or select the first 97 files.
The author's current public SALB3PM-Datasets repository also has the different
130-instance 1993 set; its checked history does not contain the 97-instance set.

Downloaded archive hashes (under `tmp/data_sources/`):

```text
SALBP-data-sets.zip  cf7a5f89e034dee8fe67b305c37399920926dd174f409b96c189653ed35bb78c
SALBP_benchmark.zip  379a419ff000aab62b12662f6224978f5fc875967ac5944b6a7d09d4555417cd
```
