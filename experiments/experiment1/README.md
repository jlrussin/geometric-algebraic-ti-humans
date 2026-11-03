# Experiment 1

Does the same person show a symbolic distance effect when queried on an ordering they learned,
and the reverse effect when queried on novel orderings given in context? Participants learned
one ordering of seven images from feedback, then were tested on novel orderings shown in full
(ICL test), on the trained images with the display masked (IWL test), and on the trained images
under a reversed display (arbitrage test). The paper's Methods and Extended methods (both under
"Human experiments", "Experiment 1") describe the design.

This folder is the experiment as participants ran it, without the recruitment and data storage
services; the session is saved to a local file instead.

## Running it

From the top of the repository:

```bash
uv run geo-alg-ti-humans images     # the 80 images, into experiments/experiment1/media/pps/
python3 -m http.server 8000 --directory experiments/experiment1
```

Then open `http://localhost:8000/?assignment=N` to run assignment `N`, a row of
`data/assignments.json` (0-199; any other value stops with an error), or
`http://localhost:8000/` for a random row. The row sets the order of the ICL and IWL tests (the
arbitrage test is last) and seeds the random number generator that assigns the images and
builds every trial, so a row always gives the same trials. The page loads jsPsych from unpkg.com
and its font from Google Fonts, so it needs an internet connection, and a window of at least
1024 x 700 pixels. When participants were recruited, a session was estimated to take about 60
minutes.

The tests also run from the top of the repository:

```bash
node --test experiments/experiment1/tests/*.test.js
```

## Files

| File | Contents |
|---|---|
| `index.html` | The page; it loads jsPsych 8.2.3 and its plugins. |
| `js/experiment.js` | Start-up and timeline. |
| `js/config.js` | Every setting. |
| `js/stimuli.js` | The 80 images, their pairwise similarity, and their assignment to roles. |
| `js/trial-logic.js`, `js/utils.js` | The trials of practice, learning and tests. |
| `js/trials.js` | The timeline nodes. |
| `js/display.js` | The task display and its jsPsych plugin. |
| `js/instructions.js`, `js/comprehension-questions.js`, `js/questionnaire.js`, `js/help.js`, `js/consent.js` | Most of the text participants read (the remaining screens are in `js/trials.js`, `js/experiment.js` and `js/display.js`, which writes the feedback). |
| `js/save.js` | The session record and its download. |
| `js/assignments.js`, `js/mode.js` | The assignment row and the `?assignment=` parameter. |
| `js/seeded-rng.js` | The seeded random number generator. |
| `styles/` | The stylesheets. |
| `data/assignments.json` | The 200 assignment rows (`assignment_id`, `test_block_order`). |
| `media.sha256` | The digests of the 80 images (`media/` itself is not in the repository). |
| `replay.mjs` | Rebuilds a session's trials in Node (used by `geo-alg-ti-humans regenerate`). |
| `tests/` | Node tests of the trial plan and the design constants. |

## The saved file

At the end of the session (or after a comprehension check failed twice) the page downloads
`experiment1_aNNN_<start time>.json`. It holds the session fields (the assignment, the test
order, the stimuli, the configuration, the browser, times, attempts at the comprehension checks
and practice blocks, help-button use) and `trials`, one row per screen (the instruction pages of
a block share one row). Practice, learning and test rows (phases `practice_query`,
`practice_singlehop`, `practice_multihop`, their retry blocks `*_extra`, `training`, `test_icl`,
`test_iwl`, `test_arbitrage`) hold the trial as shown (queried items and their ranks, the
displayed chain and pair row, distractors) and the response. The codebooks in the repository's
top-level `data/experiment1/` describe the tables built from these records.

`stream_offset` is 0 in a local session. The sessions that were run saved their data over the
network while starting, and that code drew 11, 17 or 19 values from the same random number
generator after the stimuli were assigned, which shifted every later trial. The data tables
record each session's offset, and
`node experiments/experiment1/replay.mjs --assignment-id N --stream-offset K` rebuilds that
session's trials.
