# geometric-algebraic-ti-humans

Human experiments for the paper *Geometric and algebraic inference in humans
and neural networks*.

## What this is

The paper's two human experiments as participants ran them and the code
that recomputes every number the paper reports about them and draws their
figures. The de-identified data tables are not in the repository (see Data).

- **Experiment 1.** Participants learned one ordering of seven images from
  feedback, then were tested on novel orderings shown in full (ICL test), on
  the trained images with the display masked (IWL test), and on the trained
  images under a reversed display (arbitrage test).
- **Experiment 2.** Participants judged which of two animals was heavier
  according to eight statements that ordered nine animals by weight; between
  participants, the statements were all congruent with the animals' real-world
  ordering (congruent) or followed a shuffled ordering (shuffled).

## Install

`uv sync` ([uv](https://docs.astral.sh/uv/)) installs the pinned Python 3.12
environment from `uv.lock`. The models need R 4.4.1 with the packages pinned
in `renv.lock`, and the trial replays and the experiments' tests need Node.js
22. `REPRODUCE.md` gives the details and the tested platforms.

## Quickstart

`uv run geo-alg-ti-humans smoke` runs the data preparation, the summaries and
every figure on small synthetic tables in a few seconds.

## Repository layout

`experiments/` the two experiments; `data/` the codebooks and manifest of
the data tables; `src/geo_alg_ti_humans/` the package (stimulus images,
tables, data preparation, summaries, trial regeneration, panels); `analysis/`
the R models; `results/` the committed model estimates, numbers and
statistics tables; `figures/` one script per figure; `tests/` the test suite
and its synthetic tables.

## Experiments

`experiments/experiment1/` and `experiments/experiment2/` run locally in a
browser as participants ran them, without the recruitment and data storage
services; at the end of a session the browser downloads its data as a JSON
file. Each folder's README says how to start it and what its files are.
Experiment 1's 80 images, like the images in the paper's task displays, come
from the PicturePerfectSet (Saryazdi, Bannon, Rodrigues, Klammer, & Chambers,
2018, *Behavior Research Methods*, 50, 2498-2510,
https://doi.org/10.3758/s13428-018-1028-5), which its authors offer for free
download, asking that the article be cited. The images are not distributed
here: `uv run geo-alg-ti-humans images` downloads the set's archive, checks
it, and crops them.

## Data

The data are one Parquet table per experiment and kind of record (sessions,
trials, and for Experiment 2 the questionnaire), read from
`data/experiment1/` and `data/experiment2/`. Each table has a codebook there
(`<table>.md`) describing its columns. The tables hold every session,
including those that did not finish or were excluded; participants are
identified by a pseudonymous key. `data/MANIFEST.yaml` records the sha256
digest, rows and columns of every table, and loading a table checks them.

The tables cannot be shared publicly under the terms of participants' consent,
so `data/` holds only their codebooks and the manifest, and the tests that need
the tables are skipped. The model estimates, numbers and statistics
tables are committed in `results/`, and `smoke` (see Quickstart) runs on
synthetic tables.

## Results

`geo-alg-ti-humans prepare` applies the exclusions and writes the inputs of
the R models in `analysis/`, which write `results/experiment1/models.csv`
and `results/experiment2/models.csv` (the two `models.R` scripts also write
their models' random effects to `random_effects.csv` beside them).
`geo-alg-ti-humans numbers` writes `results/numbers.csv`: one row per number
the paper prints, in its text and on its figures, about the two experiments'
participants, trials, statistics and models (all but the participants'
demographics and the Experiment 2 tests within each wave), with the section or
figure of the paper where it appears, the printed and the recomputed value,
the code that computes it, and whether the two agree.
`geo-alg-ti-humans stats-tables` writes `results/stats_tables/`: a LaTeX
table of each of the paper's main mixed-effects models (the six Experiment 1
models and the Experiment 2 accuracy and response-time models of the retained
participants).

## Figures

`figures/fig_<topic>.py` draws one appendix figure from the data tables:
`learning`, `pairs`, `arbitrage`, `participants` and `participant_slopes` for
Experiment 1; `robustness`, `agree_conflict`, `strategies`,
`participants_congruent` and `participants_shuffled` for Experiment 2.
`participants`, `participants_congruent` and `participants_shuffled` show each
participant's own accuracy and response time by symbolic distance;
`participant_slopes` plots each participant's IWL test slope against their ICL
test slope. The human panels of the main-text figures are drawn by
`geo_alg_ti_humans.plots.distance` (`REPRODUCE.md` says how).

## Reproducing the paper

See `REPRODUCE.md`.

## Related repositories

Code for the paper's other experiments:

- Transformers: https://github.com/jlrussin/geometric-algebraic-ti-transformers
- Large language models: https://github.com/joonhwakim/geometric-algebraic-ti-llms

## Citation

Russin, J., Kim, J., Pavlick, E., & Frank, M. J. (2026). Geometric and algebraic
inference in humans and neural networks. arXiv:2611.00387.
https://arxiv.org/abs/2611.00387

See `CITATION.cff`.

## License

MIT, for the code. The norm values in the Experiment 2 item tables remain
under their sources' terms (`experiments/experiment2/README.md`). The Inter
font in `experiments/experiment2/fonts/` is under the SIL Open Font License
(`OFL.txt`).

**Development notes.** This code was developed with substantial assistance
from AI coding tools (Claude Code), used for drafting code, tests,
documentation, and analysis scripts. The human authors designed the
experiments, specified and reviewed all code, and are responsible for its
correctness.
