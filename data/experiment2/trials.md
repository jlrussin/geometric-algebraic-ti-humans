# Experiment 2: trials

`trials.parquet` has one row per question saved by any Experiment 2 session (there was no
practice). Rows are sorted by `participant`, `session_index` and `question_number`.

Animals are named as in `experiments/experiment2/data/item_tables.json`. The eight statements of a
question order nine animals by weight; the answers are the two queried animals, shown side by
side. Types are the pandas dtypes that `geo_alg_ti_humans.tables.load` returns; `string`, `Int64`
and `boolean` columns hold null where a value does not apply.

| Column | Type | Values | Meaning |
|---|---|---|---|
| `participant` | string | `P001` to `P132` | Participant key (see `sessions.md`). |
| `session_index` | Int64 | 1, 2 | The person's session (see `sessions.md`). |
| `assignment_id` | Int64 | 0-999 | The session's assignment row (see `sessions.md`). |
| `condition` | string | `congruent`, `shuffled` | The session's condition. |
| `question_number` | Int64 | 1-48 | Position of the question in the session. |
| `block` | Int64 | 1-4 | Block of 12 questions; a break followed each of the first three. |
| `symbolic_distance` | Int64 | 1-6 | Number of statements linking the two queried animals in the ordering the statements give. |
| `real_world_distance` | Int64 | 1-6 | Distance between the two queried animals in the real-world order of the nine animals shown. Equal to `symbolic_distance` in the congruent condition. |
| `question_type` | string | `agree`, `conflict` | Whether the statements' answer agrees with the real-world order. Always `agree` in the congruent condition. |
| `item_pair` | string | two animal names | The two queried animals in alphabetical order, joined by a vertical bar. |
| `query_left` | string | animal name | The answer shown on the left (key F). |
| `query_right` | string | animal name | The answer shown on the right (key J). |
| `correct_answer` | string | `left`, `right` | Side of the heavier animal according to the statements. |
| `real_world_answer` | string | `left`, `right` | Side of the animal that is heavier in the real world. |
| `response_side` | string | `left`, `right`; null on a timeout | The side chosen (F = left, J = right). |
| `rt` | float64 | milliseconds; NaN on a timeout | Response time from the onset of the question. |
| `is_timed_out` | boolean | true, false | No answer within 50 s. |
| `is_correct` | boolean | true, false | The answer was the statements' answer (`response_side` equals `correct_answer`); false on a timeout. |
| `is_real_world_consistent` | boolean | true, false; null on a timeout | The answer was the animal that is heavier in the real world. |
| `statements_text` | string | JSON list of 8 strings | The eight statements, in the order of their lines on screen. |
| `context_ordering` | string | JSON list of 9 animal names | The ordering the statements give, from the lightest to the heaviest animal. |
