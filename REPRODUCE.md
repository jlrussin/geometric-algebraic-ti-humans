# Reproducing the human results

Every command runs from the top of the checkout.

## Environment

- **Python.** `uv sync` installs the pinned environment from `uv.lock` (Python
  3.12).
- **R.** R 4.4.1 (the CRAN installer for your platform; on Apple silicon, the
  x86_64 installer `R-4.4.1-x86_64.pkg`, run under Rosetta 2, reproduces
  `results/` exactly) with the package versions pinned in `renv.lock`. Starting
  R in the checkout activates its project library (`.Rprofile`), downloading
  renv 1.2.3 on the first start, and `Rscript -e 'renv::restore()'` installs
  the pinned versions into it; packages without a binary for the platform are
  built from source, which needs C and C++ compilers (on macOS, the Xcode
  Command Line Tools: `xcode-select --install`).
- **Node.js 22**, with no packages, for the trial replays and the experiments'
  tests.

Tested on macOS 26 on Apple silicon. The R results in `results/` were computed
with the x86_64 build of R 4.4.1 (run under Rosetta 2), which reproduces them
exactly. The native arm64 build of R 4.4.1 reaches the same random-effects
structure for every model and every number the paper prints, at its printed
precision, with small differences in the other values. Two counts differ in
`results/experiment2/models.csv`, both in the refits of the Experiment 2
accuracy model that leave out one participant at a time
(`accuracy_leave_one_out`): under arm64 R three refits (without P061, P096 or
P105) fail strict mode, fitting with a warning, a message, a singular fit or a
convergence message (`refits_failing_strict_mode`), and without P096 the p
value of the symbolic distance main effect crosses .05
(`log_distance_crossings`); under x86_64 R both counts are 0.

## Data

The data tables are read from `data/` (or from the directory named by the
environment variable `GEO_ALG_TI_HUMANS_DATA`, which must also hold a copy of
`data/MANIFEST.yaml`). `data/MANIFEST.yaml` records the sha256 digest, rows
and columns of every table, and every command that loads a table checks it
first against the manifest and the columns and types its codebook lists.

The tables cannot be shared publicly under the terms of participants' consent,
so `data/` holds only their codebooks and the manifest. The steps below that
need the tables (trial regeneration, exclusions, models, numbers
and figures) cannot be run; the model estimates, the numbers and the
statistics tables are committed in `results/`.

## Tests

`uv run pytest` runs the Python tests; the tests that need the data tables run
when they are present, and those that need Node.js when it is installed. The
first run downloads the clip-art archive (below) into pytest's cache, so it
needs a network connection. `node --test experiments/*/tests/*.test.js` runs the
experiments' tests. `uv run geo-alg-ti-humans smoke` runs the data
preparation, the summaries and every figure on the synthetic tables in
`tests/synthetic/`.

## Stimulus images

`uv run geo-alg-ti-humans images` downloads the PicturePerfectSet clip-art
archive (17.7 MB), checks its sha256 digest, and crops the 80 images of
Experiment 1 into `experiments/experiment1/media/pps/`, checking each against
`experiments/experiment1/media.sha256`. `--archive <path>` uses a copy of the
archive already on disk.

## Running an experiment locally

`experiments/experiment1/README.md` and `experiments/experiment2/README.md`
say how to start each experiment in a browser and what the downloaded session
file holds.

## Regenerating the trial sequences

`uv run geo-alg-ti-humans regenerate` replays every session of both
experiments from its assignment row with the experiment's own code (Node.js)
and compares the planned trials with the trials table, trial by trial:
Experiment 1, 74 sessions, of which 13 ended before their first practice trial
and have nothing to compare; Experiment 2, 134 sessions, also compared by the
digest of the whole question sequence. It exits with an error on any
difference.

## Exclusions, models and numbers

1. `uv run geo-alg-ti-humans prepare` applies the exclusions, builds the
   participant sets and the response-time frames, prints their counts, and
   writes the inputs of the R models to `analysis/inputs/`.
2. The R models, each script run from the top of the checkout:

   ```bash
   Rscript analysis/experiment1/models.R
   Rscript analysis/experiment2/models.R
   Rscript analysis/experiment2/agree_conflict.R
   Rscript analysis/experiment2/robustness.R
   Rscript analysis/experiment2/manipulation_check.R
   ```

   Each script writes its rows of `results/experiment1/models.csv` or
   `results/experiment2/models.csv`; the two `models.R` scripts also write the
   random effects of their models to `random_effects.csv` in the same folder.
   Each mixed-effects model takes the first random-effects structure, from the
   richest down (a robustness refit starts at the reported one), that fits in
   strict mode: without an error, a warning or message, a singular fit or a
   convergence message. A script stops unless every reported model reaches the
   structure the paper reports. The Experiment 1 script prints the
   structure each model reached; the Experiment 2 scripts print only R's
   package warnings (and, under arm64 R, the refits that fail strict mode)
   when they succeed, except that `agree_conflict.R` also prints how many
   participants each participant-level test leaves out.

   Each row of a `models.csv` is one term of one model or check: `experiment`;
   `model`; `set`, the Experiment 2 participant set (`retained`, the
   participants who pass every exclusion rule, or `all_finishers`, those who
   pass every rule when the one for answering at chance is not applied; empty
   in Experiment 1); `formula` and `rung`, the mixed-effects formula and the
   position of its random-effects structure among the script's structures,
   richest first (empty for a result not computed from a mixed-effects model);
   `term`; `estimate` (for a count, such as the number of refits, the count);
   `std_error`; `df`; `statistic`; `p_value`; and `conf_low` and `conf_high`,
   the bounds of its 95% interval (a Lee bound holds only its own end).
3. `uv run geo-alg-ti-humans numbers` recomputes every number the paper
   prints, in its text and on its figures, about the two experiments'
   participants, trials, statistics and models (all but the participants'
   demographics and the Experiment 2 tests within each wave) from the data tables
   and the model results and writes `results/numbers.csv`, one row per
   number: `id`, `experiment`, `site` (the section or figure of the paper),
   `printed`, `computed`, `source`, and `match` (whether `computed` rounds to
   `printed`). It exits with an error if a number differs.
4. `uv run geo-alg-ti-humans stats-tables` writes `results/stats_tables/`, one
   LaTeX table (a `tabular`, without caption) for each of the paper's main
   mixed-effects models: the six Experiment 1 models and the Experiment 2
   accuracy and response-time models of the retained participants. Each holds the model's fixed effects, the Experiment 2
   distance slopes within condition, the random effects, and the numbers of
   participants and observations, read from `models.csv` and
   `random_effects.csv`.

The `source` column names the code behind each number:
`summaries.<function>:<key>` for a count or descriptive statistic computed by
that function of `geo_alg_ti_humans.summaries`; `R:<model>:<set>:<term>:<column>`
for a value of a `models.csv` (`<set>` is empty in Experiment 1, and an
interaction term contains `:` itself, as in `condition:log_distance`); and
`max(...)`, `min(...)` or `range(...)` of several such values, for a bound the
paper states over several models, or `same(...)`, for one value it states for
several models.

## Figures

`uv run python figures/fig_<topic>.py` (or `uv run geo-alg-ti-humans figure
--name <topic>`) draws a figure from the data tables and writes a PDF at print
size plus a PNG preview to `figures/out/`.

| Topic (`fig_<topic>.py`) | Figure (appendix caption title) | Tables |
|---|---|---|
| `learning` | Learning phase | experiment1 sessions, trials |
| `pairs` | Additional human symbolic-distance results | experiment1 sessions, trials |
| `arbitrage` | Human arbitrage test | experiment1 sessions, trials |
| `participants` | Individual participants in Experiment 1 | experiment1 sessions, trials |
| `participant_slopes` | Individual symbolic-distance slopes in Experiment 1 | experiment1 sessions, trials |
| `robustness` | Experiment 2 results for participants who finished the task | experiment2 sessions, trials, questionnaire |
| `agree_conflict` | Agree and conflict questions | experiment2 sessions, trials, questionnaire |
| `strategies` | Strategies and self-reports | experiment2 sessions, trials, questionnaire |
| `participants_congruent` | Individual participants in the congruent condition of Experiment 2 | experiment2 sessions, trials, questionnaire |
| `participants_shuffled` | Individual participants in the shuffled condition of Experiment 2 | experiment2 sessions, trials, questionnaire |

No script here draws the main-text figures, which combine the human panels
with panels of the other experiments. Their human panels are drawn by
`make_accuracy_by_distance` and `make_rt_by_distance` in
`geo_alg_ti_humans.plots.distance`, from the frames that `figures/_shared.py`
loads. Apart from axis limits, ticks and legends, these are the calls:

```python
from _shared import experiment1_trials, experiment2_frames, retained  # a script in figures/
from geo_alg_ti_humans.plots import distance, style

lines = dict(show_points=False, point_dodge=0.16)
seconds = dict(rt_scale=0.001, ylabel=style.RESPONSE_TIME_LABEL)
# Experiment 1, symbolic distance: the ICL and IWL tests (the default series).
trials = experiment1_trials()
distance.make_accuracy_by_distance(ax_accuracy, trials, **lines)
distance.make_rt_by_distance(ax_rt, trials, **lines, **seconds)
# Experiment 2, content effects: the retained participants, one series per condition.
trials = retained(experiment2_frames()[0])
series = dict(group_col="condition", phases=("congruent", "shuffled"),
              colors=style.CONTEXT_COLORS, labels=style.CONTEXT_LABELS, **lines)
distance.make_accuracy_by_distance(ax_accuracy, trials, **series)
distance.make_rt_by_distance(ax_rt, trials, **series, **seconds, exclude_col="rt_trimmed")
```

## Expected runtime

Measured on an Apple M5 Max (18 cores); the R scripts under x86_64 R 4.4.1.

| Step | Time |
|---|---|
| `renv::restore()`, x86_64 R, empty cache | 12 min, most of it building `stringi` from source |
| `images` | a few seconds, mostly the download |
| `regenerate` | 5 s |
| `prepare`, `numbers`, `stats-tables`, one figure | under 1 s each; the three participant box figures 1.5 s each |
| `smoke` | 2 s |
| `uv run pytest` | 16 s |
| `analysis/experiment1/models.R` | 10-15 s |
| `analysis/experiment2/models.R` | 27 s |
| `analysis/experiment2/agree_conflict.R` | 12 s |
| `analysis/experiment2/robustness.R` | 72 s |
| `analysis/experiment2/manipulation_check.R` | 3 s |
