# Experiment 1: sessions

`sessions.parquet` has one row per session of Experiment 1, including sessions that did not
finish and sessions that ended after a failed comprehension check. Rows are sorted by
`participant` and `session_index`; `trials.parquet` joins on these two columns.

Types are the pandas dtypes that `geo_alg_ti_humans.tables.load` returns. `string`, `Int64` and
`boolean` columns hold null where a value does not apply.

| Column | Type | Values | Meaning |
|---|---|---|---|
| `participant` | string | `P001` to `P065` | Pseudonymous participant key, one per person. People are numbered in the order of the `assignment_id` of their primary session: the session with the most saved rows (ties: the lowest `assignment_id`). |
| `session_index` | Int64 | 1, 2, ... | The person's sessions numbered by start time (1 = earliest). |
| `assignment_id` | Int64 | 0-199 | Row of `experiments/experiment1/data/assignments.json` that the session ran. It sets the test order and seeds the session's random number generator, which assigns the stimuli and builds the trial sequence. Unique per session. |
| `start_order` | Int64 | 1-74 | Position of the session among all sessions of Experiment 1 in the order they started (1 = first). The mixed-effects models read their trials in this order, then by `trial_index`; the order of the rows changes their standard errors and degrees of freedom slightly. |
| `test_order` | string | `icl,iwl,arbitrage`, `iwl,icl,arbitrage` | Order of the three test blocks; the arbitrage test always came last. |
| `is_completed` | boolean | true, false | The session reached its final screen. Also true for a session that ended after a failed comprehension check (`failed_comprehension`). |
| `failed_comprehension` | boolean | true, false; null if the session did not finish | The session ended because a comprehension check was failed on both attempts. |
| `n_saved_rows` | Int64 | 0 or more | Number of records the session saved, one per screen of any kind (consent, instructions, comprehension questions, practice, learning and test trials, breaks, questionnaire). Chooses a person's primary session. |
| `stream_offset` | Int64 | 11, 17, 19; null if the session saved no practice, learning or test trial | Number of values drawn from the session's seeded random number generator between the assignment of the stimuli and the building of the practice trials, while the page preloaded images, connected to its data store and saved the session record. Replaying `assignment_id` with this many draws skipped regenerates the session's trials. |
