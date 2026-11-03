"""Exclusion rules in order, participant sets, and the response-time frames."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml

from geo_alg_ti_humans import prepare, tables


def _rows(n: int, **columns) -> pd.DataFrame:
    """``n`` rows; a list gives one value per row, anything else is repeated."""
    return pd.DataFrame({k: v if isinstance(v, list) else [v] * n for k, v in columns.items()})


def _values(series: pd.Series) -> list:
    """The values of ``series`` with every null as None."""
    return [None if pd.isna(v) else v for v in series]


def _session_rows(sessions: pd.DataFrame, key: str, *, frame) -> list:
    """``key`` of each row of ``frame`` in the order of ``sessions``' session keys."""
    out = frame.set_index(list(tables.SESSION_KEY))[key]
    return [out.loc[(p, i)] for p, i in zip(sessions["participant"], sessions["session_index"])]


# Experiment 1

def _sessions1(*rows) -> pd.DataFrame:
    """Sessions from (participant, session_index, assignment_id, overrides) tuples."""
    out = []
    for participant, index, assignment, overrides in rows:
        out.append({"participant": participant, "session_index": index,
                    "assignment_id": assignment, "is_completed": True,
                    "failed_comprehension": False, "n_saved_rows": 300, **overrides})
    return pd.DataFrame(out)


def _trials1(participant: str, session_index: int = 1) -> pd.DataFrame:
    """Ten correct learning trials, ten ICL and ten arbitrage trials on alternating sides."""
    sides = ["left", "right"] * 5
    df = pd.concat([
        _rows(10, phase="learning", response=sides),
        _rows(10, phase="icl_test", response=sides),
        _rows(10, phase="arbitrage_test", response=sides),
    ], ignore_index=True)
    return df.assign(participant=participant, session_index=session_index,
                     trial_index=range(len(df)), is_correct=True, is_timed_out=False, rt=1000.0)


def _time_out(df: pd.DataFrame, mask) -> pd.DataFrame:
    df = df.copy()
    df.loc[mask, ["is_correct", "is_timed_out", "rt", "response"]] = [False, True, np.nan, None]
    return df


def _reasons1(sessions: pd.DataFrame, trials: pd.DataFrame) -> list:
    return _values(prepare.exclusions_experiment1(sessions, trials)["reason"])


def test_binomial_upper_tail_is_exact():
    """P(X >= k) for X ~ Binomial(n, 1/2), computed exactly."""
    assert prepare.binomial_upper_tail(0, 10) == 1.0
    assert prepare.binomial_upper_tail(10, 10) == 1 / 1024
    assert prepare.binomial_upper_tail(9, 10) == 11 / 1024


def test_binomial_cutoffs_of_record():
    """The smallest k with P(X >= k) < .05 is 31 for n = 48 and 30 for n = 47."""
    for n, cutoff in ((48, 31), (47, 30)):
        assert prepare.binomial_upper_tail(cutoff, n) < 0.05
        assert prepare.binomial_upper_tail(cutoff - 1, n) >= 0.05


def test_experiment1_rules_apply_in_order_and_the_first_match_wins():
    """A session that matches several rules is counted under the earliest one."""
    def low_accuracy(df):
        return df.assign(is_correct=~((df["phase"] == "learning") & (df["trial_index"] >= 5)))

    def fast_icl(df):
        return df.assign(rt=df["rt"].where(df["phase"] != "icl_test", 300.0))

    def biased(df):
        return df.assign(response=df["response"].where(df["phase"] != "icl_test", "left"))

    def timeouts(df):
        return _time_out(df, (df["phase"] == "learning") & (df["trial_index"] < 3))

    sessions = _sessions1(
        ("P001", 1, 0, {"is_completed": False, "failed_comprehension": None}),
        ("P002", 1, 1, {"failed_comprehension": True}),
        ("P003", 1, 2, {}), ("P004", 1, 3, {}), ("P005", 1, 4, {}), ("P006", 1, 5, {}),
        ("P006", 2, 6, {"n_saved_rows": 50}), ("P007", 1, 7, {}),
    )
    trials = pd.concat([
        low_accuracy(_trials1("P001")),
        fast_icl(_trials1("P002")),
        biased(timeouts(low_accuracy(_trials1("P003")))),
        biased(fast_icl(_trials1("P004"))),
        biased(timeouts(_trials1("P005"))),
        biased(_trials1("P006")),
        biased(_trials1("P006", 2)),
        _trials1("P007"),
    ], ignore_index=True)
    assert _reasons1(sessions, trials) == [
        "not_completed", "failed_comprehension", "low_learning_accuracy", "fast_icl_responses",
        "learning_timeouts", "response_bias", "response_bias", None]
    # Rule 7 decides only when nothing earlier does.
    trials = trials[~((trials["participant"] == "P006") & (trials["session_index"] == 2))]
    assert _reasons1(sessions, trials)[6] == "repeat"


def test_experiment1_second_half_starts_at_row_n_over_2_by_trial_index():
    """Learning accuracy is taken over rows ``n // 2`` onward after sorting by ``trial_index``."""
    sessions = _sessions1(("P001", 1, 0, {}))
    # Five learning trials stored in reverse trial order: by trial_index the outcomes are
    # wrong, wrong, right, right, wrong, so rows 2-4 score 2 of 3 (kept). Unsorted rows, or a
    # second half starting at row 3, would score below 0.60.
    trials = _trials1("P001")
    trials = trials[trials["phase"] != "learning"]
    learning = _rows(5, phase="learning", trial_index=[4, 3, 2, 1, 0],
                     is_correct=[False, True, True, False, False], response="left")
    learning = learning.assign(participant="P001", session_index=1, is_timed_out=False, rt=1000.0)
    trials = pd.concat([learning, trials.assign(trial_index=trials["trial_index"] + 10)])
    assert _reasons1(sessions, trials) == [None]
    flipped = trials.assign(is_correct=trials["is_correct"].where(
        trials["trial_index"] != 2, False))
    assert _reasons1(sessions, flipped) == ["low_learning_accuracy"]


def test_experiment1_learning_timeouts_count_as_incorrect():
    """A timed-out learning trial counts against second-half accuracy."""
    sessions = _sessions1(("P001", 1, 0, {}))
    trials = _trials1("P001")
    second = (trials["phase"] == "learning") & (trials["trial_index"] >= 5)
    trials.loc[second & (trials["trial_index"] == 7), "is_correct"] = False
    # Two timeouts among the five: 2 of 5 correct, below 0.60 (2 of 3 without the timeouts).
    trials = _time_out(trials, second & trials["trial_index"].isin([8, 9]))
    assert _reasons1(sessions, trials) == ["low_learning_accuracy"]


def test_experiment1_response_bias_ignores_the_iwl_test():
    """Bias is checked in the ICL and arbitrage tests only, over answered responses."""
    def responses(df, phase, sides):
        df = df.copy()
        df.loc[df["phase"] == phase, "response"] = sides
        return df

    iwl = _rows(10, phase="iwl_test", response="left", trial_index=list(range(30, 40)))
    many_icl = _rows(20, phase="icl_test", response=["left"] * 19 + ["right"],
                     trial_index=list(range(40, 60)))
    p4 = _trials1("P004")
    p5 = _trials1("P005")
    p5 = pd.concat([p5, p5[p5["phase"] == "icl_test"].head(2).assign(trial_index=[30, 31])])
    p5 = _time_out(responses(p5, "icl_test", "left"), p5["trial_index"].isin([30, 31]))
    trials = pd.concat([
        pd.concat([_trials1("P001"), iwl.assign(participant="P001", session_index=1)]),
        responses(_trials1("P002"), "icl_test", "left"),
        responses(_trials1("P003"), "arbitrage_test", "right"),
        pd.concat([p4[p4["phase"] != "icl_test"],
                   many_icl.assign(participant="P004", session_index=1)]),
        p5,
    ], ignore_index=True).fillna({"is_correct": True, "is_timed_out": False, "rt": 1000.0})
    sessions = _sessions1(*((f"P00{i}", 1, i, {}) for i in range(1, 6)))
    # P004 answers 19 of 20 ICL questions on the left (95%, not more); P005 answers 10 of 10 on
    # the left and times out twice, which would be 10 of 12 over all its rows.
    assert _reasons1(sessions, trials) == [None, "response_bias", "response_bias", None,
                                           "response_bias"]


def test_experiment1_repeat_keeps_most_saved_rows_then_lowest_assignment():
    """Of a person's sessions, the one with the most saved rows is kept; ties go to the lowest
    ``assignment_id``."""
    sessions = _sessions1(
        ("P001", 1, 5, {"n_saved_rows": 100}), ("P001", 2, 4, {"n_saved_rows": 300}),
        ("P001", 3, 3, {"n_saved_rows": 300}), ("P002", 1, 9, {"n_saved_rows": 10}),
    )
    trials = _trials1("P000").iloc[:0]
    assert _reasons1(sessions, trials) == ["repeat", "repeat", None, None]


# Experiment 2

def _sessions2(*rows) -> pd.DataFrame:
    """Sessions from (participant, session_index, assignment_id, overrides) tuples."""
    out = []
    for participant, index, assignment, overrides in rows:
        out.append({"participant": participant, "session_index": index,
                    "assignment_id": assignment, "condition": "shuffled", "is_completed": True,
                    "n_saved_rows": 100, **overrides})
    return pd.DataFrame(out)


def _questions(participant: str, n: int = 48, *, correct: int | None = None,
               real_world: int | None = None, left: int | None = None, fast: int = 0,
               timeouts: int = 0, fast_rt: float = 300.0, session_index: int = 1):
    """``n`` questions: the first ``timeouts`` timed out; of the answered ones, the first
    ``correct`` correct, the first ``real_world`` consistent with the real-world order, the first
    ``left`` on the left (default: alternating), the first ``fast`` at ``fast_rt`` ms."""
    k = n - timeouts
    correct = k if correct is None else correct
    real_world = k if real_world is None else real_world
    sides = (["left"] * left + ["right"] * (k - left) if left is not None
             else ["left", "right"] * (k // 2) + ["left"] * (k % 2))
    answered = _rows(k, is_timed_out=False,
                     is_correct=[i < correct for i in range(k)],
                     is_real_world_consistent=[i < real_world for i in range(k)],
                     response_side=sides, rt=[fast_rt if i < fast else 2000.0 for i in range(k)])
    timed_out = _rows(timeouts, is_timed_out=True, is_correct=False,
                      is_real_world_consistent=None, response_side=None, rt=np.nan)
    df = pd.concat([timed_out, answered], ignore_index=True)
    return df.assign(participant=participant, session_index=session_index,
                     question_number=range(1, n + 1))


def _reasons2(sessions, trials, participant_set="retained") -> list:
    return _values(prepare.exclusions_experiment2(sessions, trials, participant_set)["reason"])


def test_experiment2_random_responder_needs_both_tests_at_chance():
    """A participant at chance by the statements but not by the real-world order is kept."""
    cases = {"P001": (24, 48), "P002": (24, 24), "P003": (31, 24), "P004": (30, 30),
             "P005": (48, 24)}
    sessions = _sessions2(*((p, 1, i, {}) for i, p in enumerate(cases)))
    trials = pd.concat([_questions(p, correct=c, real_world=r) for p, (c, r) in cases.items()],
                       ignore_index=True)
    assert _reasons2(sessions, trials) == [None, "random_responder", None, "random_responder",
                                           None]


def test_experiment2_same_key_and_fast_thresholds_are_inclusive():
    """Exactly 80% on one key, or exactly 25% of answers under 500 ms, excludes."""
    sessions = _sessions2(*((f"P00{i}", 1, i, {}) for i in range(1, 7)))
    trials = pd.concat([
        _questions("P001", 50, left=40),                  # 80% left
        _questions("P002", 50, left=39),                  # 78%
        _questions("P003", 40, fast=10),                  # 25% under 500 ms
        _questions("P004", 40, fast=9),                   # 22.5%
        _questions("P005", 40, fast=10, fast_rt=500.0),   # 500 ms is not under 500 ms
        _questions("P006", 48, timeouts=8, left=32),      # 80% of the answered questions
    ], ignore_index=True)
    assert _reasons2(sessions, trials) == ["same_key", None, "fast_responses", None, None,
                                           "same_key"]


def test_experiment2_repeat_tiebreaks_rows_then_assignment_then_session_index():
    """The repeat rule breaks ties by saved rows, then ``assignment_id``, then ``session_index``."""
    # Listed out of session order, so that the order of the rows cannot break the tie.
    sessions = _sessions2(
        ("P001", 1, 9, {"n_saved_rows": 50}), ("P001", 3, 7, {"n_saved_rows": 50}),
        ("P001", 2, 7, {"n_saved_rows": 50}), ("P001", 4, 8, {"n_saved_rows": 40}),
        ("P002", 1, 1, {"n_saved_rows": 5}),
    )
    trials = _questions("P000").iloc[:0]
    assert _reasons2(sessions, trials) == ["repeat", "repeat", None, "repeat", None]


def test_all_finishers_skip_only_the_random_responder_rule():
    """The two participant sets differ only in the random-responder rule."""
    sessions = _sessions2(("P001", 1, 1, {"is_completed": False}), ("P002", 1, 2, {}),
                          ("P003", 1, 3, {}), ("P004", 1, 4, {}))
    trials = pd.concat([
        _questions("P001", 10),
        _questions("P002", correct=24, real_world=24),
        _questions("P003", correct=24, real_world=24, left=48),
        _questions("P004"),
    ], ignore_index=True)
    sets = prepare.participant_sets_experiment2(sessions, trials)
    assert list(sets) == list(prepare.PARTICIPANT_SETS)
    assert _reasons2(sessions, trials, "retained") == [
        "not_completed", "random_responder", "random_responder", None]
    assert _reasons2(sessions, trials, "all_finishers") == [
        "not_completed", None, "same_key", None]
    retained, finishers = sets["retained"], sets["all_finishers"]
    assert retained.drop(columns="reason").equals(finishers.drop(columns="reason"))
    with pytest.raises(ValueError):
        prepare.exclusions_experiment2(sessions, trials, "everyone")


# Response-time frames

def _trial(phase, *, correct=True, timed_out=False, rt=1000.0, session_index=1):
    return {"participant": "P001", "session_index": session_index, "phase": phase,
            "is_correct": correct and not timed_out, "is_timed_out": timed_out,
            "rt": np.nan if timed_out else rt}


def test_rt_frame_experiment1_models_passes_arbitrage_through():
    """Incorrect arbitrage trials stay in the model frame; incorrect ICL and IWL trials do not."""
    rows = pd.DataFrame([
        _trial("practice_query_only"), _trial("learning"), _trial("learning", correct=False),
        _trial("icl_test"), _trial("icl_test", correct=False), _trial("icl_test", timed_out=True),
        _trial("iwl_test", correct=False), _trial("arbitrage_test", correct=False),
        _trial("arbitrage_test", timed_out=True),
    ])
    frame = prepare.rt_frame_experiment1_models(rows)
    assert frame.index.tolist() == [1, 3, 7, 8]
    assert np.allclose(frame["log_rt"].iloc[:3], math.log(1000.0))
    assert math.isnan(frame["log_rt"].iloc[3])
    assert not frame["rt_trimmed"].any() and frame["rt_trimmed"].notna().all()


def test_rt_frame_experiment1_models_keeps_rows_with_undefined_z():
    """A row whose z score is undefined (one row in its group) is not flagged."""
    rows = pd.DataFrame(
        [_trial("learning") for _ in range(20)] + [_trial("learning", rt=1e6)]
        + [_trial("icl_test")]                          # alone in its phase
        + [_trial("iwl_test") for _ in range(3)])       # no spread: z is 0 / 0
    frame = prepare.rt_frame_experiment1_models(rows)
    assert len(frame) == len(rows)
    assert frame["rt_trimmed"].tolist() == [False] * 20 + [True] + [False] * 4


def test_outliers_use_the_sample_sd():
    """z divides by the SD with ddof 1: the slowest row here has z = 2.92 (3.05 with ddof 0)."""
    log_offsets = [-0.1] * 6 + [0.1] * 5 + [0.8]
    rows = pd.DataFrame([_trial("learning", rt=1000.0 * math.exp(v)) for v in log_offsets])
    assert not prepare.rt_frame_experiment1_models(rows)["rt_trimmed"].any()
    assert not prepare.rt_trimmed_experiment2(rows)["rt_trimmed"].any()


def test_rt_frame_experiment1_figures_keeps_correct_answered_trials_without_outlier_removal():
    """Timeouts and errors are dropped outside the arbitrage test; no outlier is removed."""
    rows = pd.DataFrame(
        [_trial("learning") for _ in range(20)] + [_trial("learning", rt=1e6)]
        + [_trial("learning", timed_out=True), _trial("icl_test", correct=False),
           _trial("arbitrage_test", correct=False), _trial("arbitrage_test", timed_out=True),
           _trial("practice_single_hop")])
    frame = prepare.rt_frame_experiment1_figures(rows)
    assert frame.index.tolist() == [*range(21), 23]
    assert frame["rt"].tolist() == [1000.0] * 20 + [1e6, 1000.0]
    assert list(frame.columns) == list(rows.columns)


def test_rt_trimmed_experiment2_uses_all_answered_questions():
    """z is computed over correct and incorrect answered questions alike."""
    rows = pd.DataFrame(
        [_trial("main", correct=False) for _ in range(20)] + [_trial("main", rt=1e6)]
        + [_trial("main", timed_out=True)])
    frame = prepare.rt_trimmed_experiment2(rows)
    # Over the correct questions alone the slow answer would be alone, with no z.
    assert frame["rt_trimmed"].tolist() == [False] * 20 + [True, False]
    assert frame["rt_trimmed"].notna().all() and math.isnan(frame["log_rt"].iloc[-1])
    assert frame["log_rt"].iloc[20] == pytest.approx(math.log(1e6))
    # Each session is its own group: the same answers split over two sessions flag nothing.
    split = rows.assign(session_index=[1] * 20 + [2, 2])
    assert not prepare.rt_trimmed_experiment2(split)["rt_trimmed"].any()
    unknown = pd.array([None] + [False] * 21, dtype="boolean")
    with pytest.raises(ValueError, match="is_timed_out has nulls"):
        prepare.rt_trimmed_experiment2(rows.assign(is_timed_out=unknown))


def test_as_bool_refuses_a_null():
    """A boolean column converts as it is; a null raises, naming the caller and the column."""
    values = pd.Series([True, False], dtype="boolean", name="is_correct")
    assert prepare.as_bool(values, "f").tolist() == [True, False]
    with pytest.raises(ValueError, match="^f: is_correct has nulls$"):
        prepare.as_bool(pd.Series([True, None], dtype="boolean", name="is_correct"), "f")


def test_rt_kept_experiment2_keeps_answered_correct_unflagged_questions():
    """An outlier, an incorrect answer and a timeout are left out; a null flag raises."""
    rows = pd.DataFrame(
        [_trial("main") for _ in range(20)]
        + [_trial("main", rt=1e6), _trial("main", correct=False), _trial("main", timed_out=True)])
    frame = prepare.rt_trimmed_experiment2(rows)
    assert prepare.rt_kept_experiment2(frame).tolist() == [True] * 20 + [False] * 3
    unknown = pd.array([None] + [True] * 22, dtype="boolean")
    with pytest.raises(ValueError, match="is_correct has nulls"):
        prepare.rt_kept_experiment2(frame.assign(is_correct=unknown))


# The inputs to the R models

def _table(df: pd.DataFrame, experiment: str, table: str) -> pd.DataFrame:
    """``df`` with the table's columns in order and dtype; a column it lacks is null."""
    schema = tables.SCHEMAS[(experiment, table)]
    df = df.reset_index(drop=True)
    return pd.DataFrame({c: (df[c] if c in df else pd.Series([None] * len(df))).astype(t)
                         for c, t in schema.items()})


def _write_tables(root, frames) -> None:
    manifest = {}
    for (experiment, table), df in frames.items():
        path = root / experiment / f"{table}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        _table(df, experiment, table).to_parquet(path, index=False)
        manifest[f"{experiment}/{table}.parquet"] = tables._entry(path)
    (root / tables.MANIFEST).write_text(yaml.safe_dump(manifest))


def _input_columns(experiment, table, extra=()):
    return [*tables.SCHEMAS[(experiment, table)], *extra]


R_INPUT_COLUMNS = {
    "experiment1/exclusions": ["participant", "session_index", "assignment_id", "reason"],
    "experiment1/trials": _input_columns("experiment1", "trials"),
    "experiment1/rt": _input_columns("experiment1", "trials", ["log_rt"]),
    "experiment2/sessions": _input_columns(
        "experiment2", "sessions",
        ["reason_retained", "reason_all_finishers", "retained", "all_finishers"]),
    "experiment2/trials": _input_columns("experiment2", "trials", ["retained", "all_finishers"]),
    "experiment2/questionnaire": _input_columns("experiment2", "questionnaire",
                                                ["retained", "all_finishers"]),
}


def _check_inputs(paths, out_dir, rows) -> dict:
    """Assert the files, columns and row counts of the R inputs; return them read back."""
    assert set(paths) == set(R_INPUT_COLUMNS)
    read = {}
    for name, columns in R_INPUT_COLUMNS.items():
        assert paths[name] == out_dir / f"{name}.parquet"
        meta = pq.read_metadata(paths[name])
        assert meta.schema.names == columns, name
        assert meta.num_rows == rows[name], name
        read[name] = pd.read_parquet(paths[name])
    for name in ("experiment2/sessions", "experiment2/trials", "experiment2/questionnaire"):
        schema = pq.read_schema(paths[name])
        assert all(str(schema.field(c).type) == "bool" for c in prepare.PARTICIPANT_SETS)
    return read


def test_write_r_inputs_on_synthetic_tables(tmp_path):
    """The R inputs of two small synthetic experiments: kept sessions, unflagged rows, sets."""
    e1_sessions = _sessions1(("P001", 1, 0, {}),
                             ("P002", 1, 1, {"is_completed": False,
                                             "failed_comprehension": None}))
    e1_sessions = e1_sessions.assign(test_order="icl,iwl,arbitrage", start_order=[1, 2])
    practice = _rows(2, phase="practice_query_only", response="left", trial_index=[-2, -1])
    iwl = _rows(4, phase="iwl_test", response="left", trial_index=[30, 31, 32, 33])
    e1_trials = pd.concat([practice, _trials1("P001"), iwl]).assign(
        participant="P001", session_index=1, assignment_id=0,
        is_correct=lambda d: d["trial_index"] != 12, is_timed_out=False, rt=1000.0,
        is_retry=False)
    e2_sessions = _sessions2(("P001", 1, 0, {"condition": "congruent"}), ("P002", 1, 1, {}),
                             ("P003", 1, 2, {"is_completed": False}))
    e2_trials = pd.concat([_questions("P001", 6), _questions("P002", 6, correct=3,
                                                             real_world=3),
                           _questions("P003", 2)], ignore_index=True)
    questionnaire = _rows(2, participant=["P001", "P002"], session_index=1,
                          condition=["congruent", "shuffled"], statements_true="All of them")
    _write_tables(tmp_path / "data", {
        ("experiment1", "sessions"): e1_sessions, ("experiment1", "trials"): e1_trials,
        ("experiment2", "sessions"): e2_sessions, ("experiment2", "trials"): e2_trials,
        ("experiment2", "questionnaire"): questionnaire,
    })
    out_dir = tmp_path / "inputs"
    paths = prepare.write_r_inputs(out_dir, root=tmp_path / "data")
    read = _check_inputs(paths, out_dir, {
        "experiment1/exclusions": 2, "experiment1/trials": 34, "experiment1/rt": 33,
        "experiment2/sessions": 3, "experiment2/trials": 14, "experiment2/questionnaire": 2,
    })
    assert _values(read["experiment1/exclusions"]["reason"]) == [None, "not_completed"]
    assert (read["experiment1/rt"]["trial_index"] != 12).all()
    sessions = read["experiment2/sessions"]
    assert _values(sessions["reason_retained"]) == [None, "random_responder", "not_completed"]
    assert _values(sessions["reason_all_finishers"]) == [None, None, "not_completed"]
    assert sessions["retained"].tolist() == [True, False, False]
    assert sessions["all_finishers"].tolist() == [True, True, False]
    trials = read["experiment2/trials"]
    assert _session_rows(sessions, "retained", frame=trials.drop_duplicates(
        list(tables.SESSION_KEY))) == [True, False, False]
    assert read["experiment2/questionnaire"]["all_finishers"].all()


def test_prepare_on_the_committed_synthetic_tables(synthetic_root, tmp_path):
    """Exclusions, participant sets and R inputs of ``tests/synthetic/``, as its sessions were made.

    Experiment 1 drops an unfinished session, a failed comprehension check and a session without
    trials, and keeps seven people with 100 learning and 120 test trials each. Experiment 2 drops
    an unfinished session and, from the retained participants, the one who answered at random.
    """
    def excluded(out):
        rows = out[out["reason"].notna()]
        return set(zip(rows["participant"], rows["session_index"], rows["reason"]))

    sessions1 = tables.load("sessions", "experiment1", root=synthetic_root)
    trials1 = tables.load("trials", "experiment1", root=synthetic_root)
    exclusions = prepare.exclusions_experiment1(sessions1, trials1)
    assert excluded(exclusions) == {("P003", 1, "not_completed"),
                                    ("P004", 1, "failed_comprehension"),
                                    ("P005", 1, "not_completed")}
    sessions2 = tables.load("sessions", "experiment2", root=synthetic_root)
    trials2 = tables.load("trials", "experiment2", root=synthetic_root)
    sets = prepare.participant_sets_experiment2(sessions2, trials2)
    assert excluded(sets["retained"]) == {("P011", 1, "random_responder"),
                                          ("P012", 1, "not_completed")}
    assert excluded(sets["all_finishers"]) == {("P012", 1, "not_completed")}

    paths = prepare.write_r_inputs(tmp_path, root=synthetic_root)
    # Of the 1,540 rows, 1,406 are correct and answered or in the arbitrage test; 7 are outliers.
    read = _check_inputs(paths, tmp_path, {
        "experiment1/exclusions": len(sessions1), "experiment1/trials": 7 * 220,
        "experiment1/rt": 1399,
        "experiment2/sessions": len(sessions2), "experiment2/trials": len(trials2),
        "experiment2/questionnaire": 12,
    })
    # Experiment 1's rows run by session start, then trial.
    starts = sessions1.set_index(list(tables.SESSION_KEY))["start_order"]
    for name in ("experiment1/trials", "experiment1/rt"):
        rows = read[name]
        order = pd.DataFrame({
            "start": starts.reindex(pd.MultiIndex.from_frame(
                rows[list(tables.SESSION_KEY)])).to_numpy(),
            "trial": rows["trial_index"].to_numpy()})
        assert order.equals(order.sort_values(["start", "trial"], ignore_index=True)), name
    sessions = read["experiment2/sessions"]
    assert sessions.groupby("condition")["retained"].sum().to_dict() == {
        "congruent": 6, "shuffled": 5}
    assert sessions.groupby("condition")["all_finishers"].sum().to_dict() == {
        "congruent": 6, "shuffled": 6}


def test_write_r_inputs_of_record(data_root, tmp_path):
    """The R inputs carry the data tables' columns and the counts in the data tables."""
    paths = prepare.write_r_inputs(tmp_path, root=data_root)
    read = _check_inputs(paths, tmp_path, {
        "experiment1/exclusions": 74, "experiment1/trials": 8800, "experiment1/rt": 7528,
        "experiment2/sessions": 134, "experiment2/trials": 5747,
        "experiment2/questionnaire": 118,
    })
    rt = read["experiment1/rt"]["phase"].value_counts()
    assert (rt["icl_test"], rt["iwl_test"]) == (1251, 1223)
    # The models read Experiment 1's rows by session start, then trial.
    start_order = tables.load("sessions", "experiment1", root=data_root).set_index(
        list(tables.SESSION_KEY))["start_order"]
    for name in ("experiment1/trials", "experiment1/rt"):
        rows = read[name]
        order = pd.DataFrame({
            "start": start_order.reindex(pd.MultiIndex.from_frame(
                rows[list(tables.SESSION_KEY)])).to_numpy(),
            "trial": rows["trial_index"].to_numpy()})
        assert order["start"].notna().all()
        assert order.equals(order.sort_values(["start", "trial"], ignore_index=True)), name
        assert not order.duplicated().any()
    sessions = read["experiment2/sessions"]
    for name, kept in (("retained", {"congruent": 49, "shuffled": 50}),
                       ("all_finishers", {"congruent": 49, "shuffled": 66})):
        assert sessions.groupby("condition")[name].sum().to_dict() == kept
        assert (sessions[name] == sessions[f"reason_{name}"].isna()).all()
    assert read["experiment2/trials"]["retained"].sum() == 4752


# Counts in the data tables

def test_experiment1_exclusions_of_record(data_root):
    """74 sessions of 65 people; 16 not completed, 17 failed comprehension, 1 low learning
    accuracy; no other rule decides; 40 sessions kept, one per person."""
    sessions = tables.load("sessions", "experiment1", root=data_root)
    trials = tables.load("trials", "experiment1", root=data_root)
    out = prepare.exclusions_experiment1(sessions, trials)
    assert len(out) == 74 and out["participant"].nunique() == 65
    counts = out["reason"].value_counts().to_dict()
    assert counts == {"not_completed": 16, "failed_comprehension": 17, "low_learning_accuracy": 1}
    kept = out[out["reason"].isna()]
    assert len(kept) == 40 and kept["participant"].is_unique


def test_experiment1_kept_person_keys_follow_assignment_order(data_root):
    """Among kept sessions, sorting by ``participant`` sorts by ``assignment_id``."""
    sessions = tables.load("sessions", "experiment1", root=data_root)
    trials = tables.load("trials", "experiment1", root=data_root)
    out = prepare.exclusions_experiment1(sessions, trials)
    kept = out[out["reason"].isna()]
    by_key = kept.sort_values("participant")["assignment_id"].to_list()
    assert by_key == sorted(by_key)


def test_experiment2_sets_of_record(data_root):
    """Per set and condition, the reasons and the kept counts in the data tables."""
    sessions = tables.load("sessions", "experiment2", root=data_root)
    trials = tables.load("trials", "experiment2", root=data_root)
    assert len(sessions) == 134 and sessions["participant"].nunique() == 132
    expected = {
        "retained": {
            ("congruent", "not_completed"): 3, ("shuffled", "not_completed"): 13,
            ("congruent", "random_responder"): 1, ("shuffled", "random_responder"): 17,
            ("shuffled", "fast_responses"): 1,
            ("congruent", None): 49, ("shuffled", None): 50,
        },
        "all_finishers": {
            ("congruent", "not_completed"): 3, ("shuffled", "not_completed"): 13,
            ("congruent", "same_key"): 1, ("shuffled", "same_key"): 1,
            ("shuffled", "fast_responses"): 1,
            ("congruent", None): 49, ("shuffled", None): 66,
        },
    }
    sets = prepare.participant_sets_experiment2(sessions, trials)
    for name, counts in expected.items():
        out = sets[name]
        got = out.fillna({"reason": "kept"}).groupby(["condition", "reason"]).size().to_dict()
        assert got == {(c, r or "kept"): n for (c, r), n in counts.items()}, name
    # The same sessions as the record, by assignment, not only the same counts.
    excluded = {
        ("retained", "random_responder"): {
            ("congruent", 261), *(("shuffled", a) for a in (
                65, 70, 73, 82, 91, 98, 101, 103, 139, 140, 167, 183, 188, 209, 233, 246, 253))},
        ("retained", "fast_responses"): {("shuffled", 227)},
        ("all_finishers", "same_key"): {("congruent", 261), ("shuffled", 91)},
        ("all_finishers", "fast_responses"): {("shuffled", 227)},
    }
    for (name, reason), want in excluded.items():
        rows = sets[name][sets[name]["reason"] == reason]
        assert set(zip(rows["condition"], rows["assignment_id"])) == want, (name, reason)


def test_experiment1_rt_model_frame_counts_of_record(data_root):
    """8,800 rows; 7,555 after the filter; 27 outliers flagged (18, 1, 3, 5 by phase); 7,528."""
    sessions = tables.load("sessions", "experiment1", root=data_root)
    trials = tables.load("trials", "experiment1", root=data_root)
    out = prepare.exclusions_experiment1(sessions, trials)
    kept = out.loc[out["reason"].isna(), ["participant", "session_index"]]
    rows = trials.merge(kept, on=["participant", "session_index"])
    assert (~rows["phase"].str.startswith("practice")).sum() == 8800
    frame = prepare.rt_frame_experiment1_models(rows)
    flagged = frame["rt_trimmed"].astype(bool)
    assert len(frame) == 7555 and (~flagged).sum() == 7528
    by_phase = frame[flagged].groupby("phase").size().to_dict()
    assert by_phase == {"learning": 18, "icl_test": 1, "iwl_test": 3, "arbitrage_test": 5}


def test_experiment2_rt_trimmed_counts_of_record(data_root):
    """Retained: 26 of 4,732 flagged, 20 of them correct, 3,990 correct rows kept; all finishers:
    31 of 5,493, 23, 4,383."""
    sessions = tables.load("sessions", "experiment2", root=data_root)
    trials = tables.load("trials", "experiment2", root=data_root)
    sets = prepare.participant_sets_experiment2(sessions, trials)
    expected = {  # answered questions, outliers flagged, correct flagged, correct unflagged rows
        "retained": (4732, {"congruent": 16, "shuffled": 10}, {"congruent": 15, "shuffled": 5},
                     {"congruent": 2233, "shuffled": 1757}),
        "all_finishers": (5493, 31, 23, 4383),
    }
    for name, (n_answered, n_flagged, n_flagged_correct, n_kept) in expected.items():
        keep = sets[name].loc[sets[name]["reason"].isna(), ["participant", "session_index"]]
        rows = trials.merge(keep, on=["participant", "session_index"])
        frame = prepare.rt_trimmed_experiment2(rows)
        answered = frame[~frame["is_timed_out"].astype(bool)]
        flagged = answered[answered["rt_trimmed"].astype(bool)]
        flagged_correct = flagged[flagged["is_correct"].astype(bool)]
        kept = answered[answered["is_correct"].astype(bool) & ~answered["rt_trimmed"].astype(bool)]
        assert len(answered) == n_answered, name
        if isinstance(n_flagged, dict):
            assert flagged.groupby("condition").size().to_dict() == n_flagged
            assert flagged_correct.groupby("condition").size().to_dict() == n_flagged_correct
            assert kept.groupby("condition").size().to_dict() == n_kept
        else:
            assert (len(flagged), len(flagged_correct), len(kept)) == (
                n_flagged, n_flagged_correct, n_kept), name
