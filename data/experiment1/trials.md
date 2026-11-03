# Experiment 1: trials

`trials.parquet` has one row per task trial saved by any Experiment 1 session: the practice
trials (retry blocks included), the learning phase and the ICL, IWL and arbitrage tests. Rows are
sorted by `participant`, `session_index` and `trial_index`.

Items are clip-art images named as in `experiments/experiment1/js/stimuli.js`. Ranks count from 1,
the item the aliens preferred most. Clues are the row of image pairs below the query; each pair
shows two adjacent items of a chain. Types are the pandas dtypes that
`geo_alg_ti_humans.tables.load` returns; `string`, `Int64` and `boolean` columns hold null where a
value does not apply.

| Column | Type | Values | Meaning |
|---|---|---|---|
| `participant` | string | `P001` to `P065` | Participant key (see `sessions.md`). |
| `session_index` | Int64 | 1, 2, ... | The person's session (see `sessions.md`). |
| `assignment_id` | Int64 | 0-199 | The session's assignment row (see `sessions.md`). |
| `phase` | string | `practice_query_only`, `practice_single_hop`, `practice_multihop`, `learning`, `icl_test`, `iwl_test`, `arbitrage_test` | Part of the session: the three practice blocks (the query alone; clues with one-step queries; clues with multistep queries), the learning phase, and the three tests. |
| `is_retry` | boolean | true, false | A trial of a practice retry block: five newly generated trials run after a practice block below 70% accuracy; a second retry repeats the same five. |
| `trial_index` | Int64 | 0 or more | Position of the trial among all the screens of the session; increases within a session. |
| `symbolic_distance` | Int64 | 1-6 | Distance between the two queried items in the ordering that ranks them: the absolute difference of `query_left_rank` and `query_right_rank`. |
| `query_left` | string | item name | Image shown on the left of the query (key F). |
| `query_right` | string | item name | Image shown on the right of the query (key J). |
| `query_left_rank` | Int64 | 1-7 | Rank of the left image in the trained ordering (learning phase, IWL and arbitrage tests), the novel ordering (ICL test) or the practice ordering (1-3 in query-only practice). |
| `query_right_rank` | Int64 | 1-7 | Rank of the right image, as for `query_left_rank`. |
| `context_display` | string | `shown`, `masked`; null in query-only practice | Whether the clues were shown or masked by featureless gray boxes (IWL test and one in ten learning trials). Query-only practice showed no clues. |
| `intervening_distractors` | Int64 | 0-2; null if `context_display` is not `shown` | Number of distractors displayed in the chain between the two queried items. Learning trials query adjacent items with 0, 1 or 2 intervening distractors; practice and test trials have none. |
| `n_context_pairs` | Int64 | 0, 5-8 | Number of clue pairs in the row (0 in query-only practice). |
| `displayed_chain` | string | JSON list of item names | The chain the clues show, most preferred first as the clues rank them (in the arbitrage test, the reverse of the trained ordering), distractors included and with `swap_distractor` in the place of `swapped_item`. When the clues were masked, the chain behind the gray boxes: a random arrangement of the trained items and distractors, drawn for each trial. An empty list in query-only practice. |
| `display_slots` | string | JSON list of objects | One object per clue pair, in chain order: `pair_index` (the pair's position in the row on screen, 0 = leftmost), `top_item` and `bottom_item` (the images above and below), `top_is_higher` (the top image ranks above the bottom one in the chain; true on every trial), `top_is_distractor` and `bottom_is_distractor` (the image is a distractor, `swap_distractor` included). An empty list in query-only practice. |
| `inserted_distractors` | string | JSON list of item names | The distractors inserted into the chain on this trial, not counting `swap_distractor`. |
| `swapped_item` | string | item name; null except on learning trials with the clues shown | The main item, not queried, that `swap_distractor` replaced in one of its clue pairs. Unless the item is at an end of the chain, it still appears in its other pair. |
| `swap_distractor` | string | item name; null when `swapped_item` is null | The distractor that replaced `swapped_item`. |
| `icl_ordering` | Int64 | 0-4; null outside the ICL test | Which of the five novel orderings the ICL trial used. |
| `icl_consistent_side` | string | `left`, `right`; null outside the ICL and arbitrage tests | The answer the clues imply. In the arbitrage test the clues reverse the trained ordering, so this side is the opposite of the trained answer. |
| `response` | string | `left`, `right`; null on a timeout | The side chosen (F = left, J = right). |
| `rt` | float64 | milliseconds; NaN on a timeout | Response time from the onset of the query. |
| `is_correct` | boolean | true, false | The response chose the higher-ranked image; false on a timeout. In the arbitrage test: the response followed the trained ordering. |
| `is_timed_out` | boolean | true, false | No response within 60 s. |
| `is_icl_consistent` | boolean | true, false; null outside the arbitrage test | The arbitrage response followed the clues. |
| `is_iwl_consistent` | boolean | true, false; null outside the arbitrage test | The arbitrage response followed the trained ordering; the complement of `is_icl_consistent` on answered trials (both are false on a timed-out trial). |
