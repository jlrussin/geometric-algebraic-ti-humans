# Experiment 2

Does the symbolic distance effect of reasoning from given statements depend on whether the
statements agree with what people know about the world? Each of 48 questions shows eight
statements that order nine animals by weight and asks which of two animals is heavier according
to the statements; between participants, the statements are all congruent with the animals'
real-world ordering (congruent) or follow a shuffled ordering (shuffled). The paper's Methods
and Extended methods (both under "Human experiments", "Experiment 2") describe the design.

This folder is the experiment as participants ran it, without the recruitment and data storage
services; the session is saved to a local file instead.

## Running it

From the top of the repository:

```bash
python3 -m http.server 8000 --directory experiments/experiment2
```

Then open `http://localhost:8000/?assignment=N` to run assignment `N`, a row of
`data/assignments.json` (0-999: it sets the condition and seeds the session's questions; any
other value stops with an error), or `http://localhost:8000/` for a random row. The page loads
jsPsych from unpkg.com, so it needs an internet connection, and a window of at least 1024 x 700
pixels. At the end of the session the browser downloads the session's data as a JSON file; the
last screen gives its name and a link that downloads it again. When participants were
recruited, a session was estimated to take about 25 minutes.

The tests also run from the top of the repository:

```bash
node --test experiments/experiment2/tests/*.test.js
```

## Files

| File | Contents |
|---|---|
| `index.html` | The page. |
| `js/experiment.js` | Start-up and timeline. |
| `js/trial-logic.js` | Every question of a session, generated from its assignment row (also runs in Node). |
| `js/config.js` | The configuration and its checks. |
| `js/copy.js` | Every word participants read, except the closing screen of a local session and the start-up fallback (`js/experiment.js`, `index.html`). |
| `js/save.js` | The session's data document and its download. |
| `js/assignments.js`, `js/mode.js` | The assignment row and the `?assignment=` parameter. |
| `js/item-tables.js` | Loads the item tables. |
| `js/instructions.js`, `js/questionnaire.js`, `js/trials.js` | The instruction pages, the questionnaire and the other screens. |
| `js/question-trial-plugin.js`, `js/continue-screen-plugin.js` | jsPsych plugins: the question screen and the screens that Space ends. |
| `js/seeded-rng.js` | Seeded random streams. |
| `styles/experiment.css`, `fonts/` | Styles and the Inter font (SIL Open Font License, `fonts/OFL.txt`). |
| `data/assignments.json` | The 1,000 assignment rows (`assignment_id`, `condition`): the two conditions in randomly ordered pairs. |
| `data/item_tables.json` | The item tables: the questions use the animals by weight, the instruction example the everyday objects by size. |
| `replay.mjs` | Rebuilds a session's questions in Node (used by `geo-alg-ti-humans regenerate`). |
| `tests/` | Node tests. |

## The downloaded data

`<date>_<time>Z_<condition>_a<assignment_id>_<token>.json` (the `assignment_id` padded to three
digits, e.g. `a007`) holds one object:

- `assignment_id`, `condition`, `file_prefix` (the file name), `start_time_iso` (consent),
  `end_time_iso`, `total_duration_ms`, `consent_given`, `is_completed`, `total_task_trials`;
- `config`: the configuration of `js/config.js`;
- `schedule_sha256`: the sha256 digest of the session's questions, which `replay.mjs` rebuilds
  from `assignment_id` and `condition`; `balance_exactness` and `generation_stats` describe how
  they were generated; `item_table_version` and `item_table_hash`, the `table_version` and
  `source_hash` of `data/item_tables.json` (`source_hash` identifies the source the tables were
  built from, not the file itself); `prng_seed`;
- `browser_metadata`: browser, operating system, window and screen size;
- `trials`: one row per screen from the browser check to the questionnaire (`phase`
  `browser_check`, `consent`, `fullscreen`, `instructions`, `main_intro`, `main` (one row per
  question), `break`, `questionnaire_intro`, `questionnaire`); the instruction pages share one
  row. A question row holds the
  question as shown (the record that `js/trial-logic.js` builds), the response and its timing,
  and whether the answer agreed with the statements (`is_correct`) and with the real-world
  order (`is_knowledge_consistent`). The codebooks in the repository's top-level
  `data/experiment2/` describe the tables built from these records.

## Item tables

`data/item_tables.json` holds the animals (`animal_weight`, the questions) and the everyday
objects (`object_size`, the instruction example). Each domain's `slot_tables["9"]` lists nine
slots in increasing `magnitude` (log10 grams for the animals, log10 cm for the objects); a
question takes one `eligible` item from each slot, so the slots give the real-world order. An
item's `norms` are values from published sources, which `norm_sources` lists for each domain:

- `mass_log10_g`: body mass (log10 grams), the median over PanTHERIA (Jones et al., 2009;
  CC BY 4.0), EltonTraits 1.0 (Wilman et al., 2014; CC0) and AnAge (de Magalhães et al., 2024;
  CC BY 3.0). It is the animals' `magnitude`, except for the insects (flag
  `magnitude_estimated`), whose typical adult masses were entered by hand. Published masses of
  common species of the six insects the questions use are in AnimalTraits (Herberstein et al.,
  2022; ant, grasshopper and dragonfly), Lee et al. (2018; mosquito), Bunchu et al. (2014; fly)
  and Herman (1988; butterfly).
- `grand_weight_z`: rated weight (mean z score) from Grand et al. (2022), released without a
  license.
- `things_size`, `things_size_sd`: rated size (mean and SD) from THINGSplus (Stoinski et al.,
  2024; THINGS: Hebart et al., 2019; CC BY). The objects' `magnitude` is `things_size`
  converted to log10 cm by a linear fit to the measured sizes of Konkle and Oliva (2011),
  which `konkle_log10_cm` holds where available.

These values remain under their sources' terms.

- Bunchu, N., Piangjai, S., Sukontason, K. L., & Sukontason, K. (2014). Survival to starvation
  of the house fly, Musca domestica L. and blow fly, Chrysomya megacephala (F.).
  https://he01.tci-thaijo.org/index.php/CMMJ-MedCMJ/article/view/87364
- de Magalhães, J. P., et al. (2024). Human Ageing Genomic Resources: updates on key databases
  in ageing research. https://doi.org/10.1093/nar/gkad927
- Grand, G., Blank, I. A., Pereira, F., & Fedorenko, E. (2022). Semantic projection recovers
  rich human knowledge of multiple object features from word embeddings.
  https://doi.org/10.1038/s41562-022-01316-8
- Hebart, M. N., Dickter, A. H., Kidder, A., Kwok, W. Y., Corriveau, A., Van Wicklin, C., &
  Baker, C. I. (2019). THINGS: A database of 1,854 object concepts and more than 26,000
  naturalistic object images. https://doi.org/10.1371/journal.pone.0223792
- Herberstein, M. E., McLean, D. J., Lowe, E., et al. (2022). AnimalTraits - a curated animal
  trait database for body mass, metabolic rate and brain size.
  https://doi.org/10.1038/s41597-022-01364-9
- Herman, W. S. (1988). Body weight and wing length changes in Minnesota populations of the
  monarch butterfly. https://images.peabody.yale.edu/lepsoc/jls/1980s/1988/1988-42(1)32-Herman.pdf
- Jones, K. E., Bielby, J., Cardillo, M., et al. (2009). PanTHERIA: a species-level database of
  life history, ecology, and geography of extant and recently extinct mammals.
  https://doi.org/10.1890/08-1494.1
- Konkle, T., & Oliva, A. (2011). Canonical visual size for real-world objects.
  https://doi.org/10.1037/a0020413
- Lee, J., Choi, D. B., Liu, F., Grieco, J. P., & Achee, N. L. (2018). Effect of the topical
  repellent para-menthane-3,8-diol on blood feeding behavior and fecundity of the dengue virus
  vector Aedes aegypti. https://doi.org/10.3390/insects9020060
- Stoinski, L. M., Perkuhn, J., & Hebart, M. N. (2024). THINGSplus: New norms and metadata for
  the THINGS database of 1854 object concepts and 26,107 natural object images.
  https://doi.org/10.3758/s13428-023-02110-8
- Wilman, H., Belmaker, J., Simpson, J., de la Rosa, C., Rivadeneira, M. M., & Jetz, W. (2014).
  EltonTraits 1.0: Species-level foraging attributes of the world's birds and mammals.
  https://doi.org/10.1890/13-1917.1
