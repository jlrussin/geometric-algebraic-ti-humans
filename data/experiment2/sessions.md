# Experiment 2: sessions

`sessions.parquet` has one row per session of Experiment 2, including sessions that did not
finish. Rows are sorted by `participant` and `session_index`; `trials.parquet` and
`questionnaire.parquet` join on these two columns.

Types are the pandas dtypes that `geo_alg_ti_humans.tables.load` returns. `string`, `Int64` and
`boolean` columns hold null where a value does not apply.

| Column | Type | Values | Meaning |
|---|---|---|---|
| `participant` | string | `P001` to `P132` | Pseudonymous participant key, one per person. People are numbered in the order in which their primary session started: the session with the most saved rows (ties: the lowest `assignment_id`, then the earliest start). |
| `session_index` | Int64 | 1, 2 | The person's sessions numbered by start time (1 = earliest). |
| `assignment_id` | Int64 | 0-999 | Row of `experiments/experiment2/data/assignments.json` that the session ran. It sets the condition and seeds the generation of the session's questions. A reloaded page kept its row, so two sessions of one person can share it. |
| `condition` | string | `congruent`, `shuffled` | The session's condition: statements all congruent with the real-world order (congruent), or each question's statements giving its own reordering of the animals (shuffled). |
| `wave` | Int64 | 1, 2 | Data-collection wave in which the session started. |
| `allocation_round` | Int64 | 1, 2; null in wave 1 | Round of the second wave: in round 1 rows of the assignment table were skipped to assign mostly shuffled participants, in round 2 only congruent ones. |
| `is_completed` | boolean | true, false | The session reached its final screen. |
| `n_saved_rows` | Int64 | 0 or more | Number of records the session saved, one per screen of any kind (consent, instructions, questions, breaks, questionnaire). Chooses a person's primary session. |
| `n_main_questions` | Int64 | 0-48 | Number of questions the session saved: its rows in `trials.parquet`. |
| `schedule_sha256` | string | 64 hexadecimal digits | sha256 digest of the session's schedule of questions, which the experiment generates from `assignment_id` and the condition; regenerating the schedule reproduces this digest. |
