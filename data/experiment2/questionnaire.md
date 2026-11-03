# Experiment 2: questionnaire

`questionnaire.parquet` has one row per Experiment 2 session that finished, with the answers to
the two fixed-choice questionnaire items the analysis uses. The questionnaire was optional: a
skipped item is null. Rows are sorted by `participant` and `session_index`.

Types are the pandas dtypes that `geo_alg_ti_humans.tables.load` returns.

| Column | Type | Values | Meaning |
|---|---|---|---|
| `participant` | string | `P001` to `P132` | Participant key (see `sessions.md`). |
| `session_index` | Int64 | 1, 2 | The person's session (see `sessions.md`). |
| `condition` | string | `congruent`, `shuffled` | The session's condition. |
| `statements_true` | string | `All of them`, `Most of them`, `About half of them`, `Few of them`, `None of them`, `I don't know`; null if skipped | Answer to "In the main questions, how many of the statements were true of the real world?" (the manipulation check). Choices in the order shown. |
| `knowledge_use` | string | `Never`, `Rarely`, `Sometimes`, `Often`, `Always`; null if skipped | Answer to "How often did you answer from what you know about the real world instead of from the statements?" Choices in the order shown. |
