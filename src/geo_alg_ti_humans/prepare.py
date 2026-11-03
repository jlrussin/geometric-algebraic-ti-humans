"""Exclusions, participant sets, response-time frames, and the inputs to the R models.

Every rule is applied as it was run for the paper, in the order below; a session excluded by
several rules is counted under the first one it matches. "Answered" means not timed out.

Experiment 1, per session:
  1. ``not_completed``: the session did not finish.
  2. ``failed_comprehension``: the participant used up the comprehension-check attempts.
  3. ``low_learning_accuracy``: accuracy below 0.60 over the second half of the learning trials
     (rows sorted by ``trial_index``, the second half starting at row ``n // 2``; timeouts
     count as incorrect).
  4. ``fast_icl_responses``: median ICL-test response time below 400 ms (answered trials).
  5. ``learning_timeouts``: more than 20% of the learning trials timed out.
  6. ``response_bias``: more than 95% of the answered responses on one side, in the ICL test
     or in the arbitrage test.
  7. ``repeat``: a person's other sessions; the session with the most saved rows is kept, ties
     going to the lowest ``assignment_id``.

Experiment 2, per session:
  1. ``not_completed``: the session did not finish.
  2. ``repeat``: a person's other sessions; the session with the most saved rows is kept, then
     the lowest ``assignment_id``, then the lowest ``session_index``.
  3. ``random_responder``: with n answered main questions, the exact one-sided binomial test
     P(X >= k | n, 1/2) is at least .05 both for k = answers correct by the statements and for
     k = answers consistent with the real-world order.
  4. ``same_key``: the most-pressed key on at least 80% of the answered questions.
  5. ``fast_responses``: at least 25% of the answered questions answered in under 500 ms.

The ``retained`` participants pass every rule; ``all_finishers`` pass every rule except
``random_responder``.

Response-time outliers are flagged in a boolean ``rt_trimmed`` (the R input keeps only the
unflagged rows): the natural log of the response time is z-scored within each session (and, in
Experiment 1, phase) with the SD taken with ddof 1, and ``|z| > 3`` flags a row. A row whose z
is undefined (alone in its group, or without a response time) is not flagged.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from geo_alg_ti_humans import tables

REASONS_EXPERIMENT1 = (
    "not_completed",
    "failed_comprehension",
    "low_learning_accuracy",
    "fast_icl_responses",
    "learning_timeouts",
    "response_bias",
    "repeat",
)
REASONS_EXPERIMENT2 = ("not_completed", "repeat", "random_responder", "same_key", "fast_responses")
PARTICIPANT_SETS = ("retained", "all_finishers")

# Experiment 1 rules.
_MIN_LEARNING_ACCURACY = 0.60       # second half of the learning trials
_MIN_ICL_MEDIAN_RT_MS = 400.0
_MAX_LEARNING_TIMEOUT_SHARE = 0.20
_MAX_RESPONSE_BIAS = 0.95
_BIAS_PHASES = ("icl_test", "arbitrage_test")
# Experiment 2 rules.
_CHANCE_ALPHA = 0.05
_MIN_SAME_KEY_SHARE = 0.80
_FAST_RT_MS = 500.0
_MIN_FAST_SHARE = 0.25
# Response-time outliers: |z| of log response time above this.
_OUTLIER_Z = 3.0

# The learning phase and the three tests of Experiment 1.
TASK_PHASES = ("learning", "icl_test", "iwl_test", "arbitrage_test")
_ARBITRAGE_PHASE = "arbitrage_test"

_KEY = list(tables.SESSION_KEY)


def binomial_upper_tail(k: int, n: int) -> float:
    """Exact P(X >= k) for X ~ Binomial(n, 1/2)."""
    return sum(math.comb(n, i) for i in range(max(k, 0), n + 1)) / 2**n


def _flag(series: pd.Series) -> pd.Series:
    """A boolean column as plain booleans, a null counting as false."""
    return series.fillna(False).astype(bool)


def as_bool(series: pd.Series, fname: str) -> pd.Series:
    """A boolean column as plain booleans; raises, naming ``fname``, if it has nulls."""
    if series.isna().any():
        raise ValueError(f"{fname}: {series.name} has nulls")
    return series.astype(bool)


def _on_sessions(sessions: pd.DataFrame, per_session: pd.Series) -> np.ndarray:
    """A boolean per session (indexed by the session key) aligned to the rows of ``sessions``;
    a session without a value is false."""
    index = pd.MultiIndex.from_frame(sessions[_KEY])
    if per_session.empty:
        return np.zeros(len(sessions), dtype=bool)
    return per_session.astype(bool).reindex(index, fill_value=False).to_numpy()


def _share(hits: pd.Series, rows: pd.DataFrame) -> pd.Series:
    """Per session, the share of ``rows`` where ``hits`` is true."""
    return hits.astype(float).groupby([rows[c] for c in _KEY]).mean()


def _repeats(sessions: pd.DataFrame, tiebreak: Sequence[str]) -> np.ndarray:
    """Whether each session is a person's other session: the kept one has the most saved rows,
    then the lowest value of each ``tiebreak`` column in turn."""
    order = sessions.sort_values(
        ["participant", "n_saved_rows", *tiebreak],
        ascending=[True, False, *([True] * len(tiebreak))], kind="stable")
    kept = order.drop_duplicates("participant").index
    return ~sessions.index.isin(kept)


def _first_reasons(sessions: pd.DataFrame, flags: Mapping[str, np.ndarray],
                   reasons: Sequence[str], columns: Sequence[str]) -> pd.DataFrame:
    """One row per session with the first of ``reasons`` whose flag is set (null if none)."""
    reason = pd.Series(pd.NA, index=sessions.index, dtype="string")
    for name in reasons:
        reason = reason.mask(reason.isna() & flags[name], name)
    out = sessions[list(columns)].assign(reason=reason)
    return out.reset_index(drop=True)


def exclusions_experiment1(sessions: pd.DataFrame, trials: pd.DataFrame) -> pd.DataFrame:
    """One row per session: ``participant``, ``session_index``, ``assignment_id``, ``reason``.

    ``reason`` is the first rule of ``REASONS_EXPERIMENT1`` the session matches, null when the
    session is kept.
    """
    learning = trials[trials["phase"] == "learning"].sort_values(
        [*_KEY, "trial_index"], kind="stable")
    by_session = learning.groupby(_KEY, sort=False)
    second = learning[by_session.cumcount() >= by_session["phase"].transform("size") // 2]
    icl = trials[(trials["phase"] == "icl_test") & trials["rt"].notna()]
    biased = np.zeros(len(sessions), dtype=bool)
    for phase in _BIAS_PHASES:
        sides = trials[(trials["phase"] == phase) & trials["response"].isin(["left", "right"])]
        left = _share(sides["response"] == "left", sides)
        biased |= _on_sessions(sessions, np.maximum(left, 1.0 - left) > _MAX_RESPONSE_BIAS)
    flags = {
        "not_completed": ~_flag(sessions["is_completed"]).to_numpy(),
        "failed_comprehension": _flag(sessions["failed_comprehension"]).to_numpy(),
        "low_learning_accuracy": _on_sessions(
            sessions, _share(_flag(second["is_correct"]), second) < _MIN_LEARNING_ACCURACY),
        "fast_icl_responses": _on_sessions(
            sessions, icl.groupby(_KEY)["rt"].median() < _MIN_ICL_MEDIAN_RT_MS),
        "learning_timeouts": _on_sessions(
            sessions,
            _share(_flag(learning["is_timed_out"]), learning) > _MAX_LEARNING_TIMEOUT_SHARE),
        "response_bias": biased,
        "repeat": _repeats(sessions, ["assignment_id"]),
    }
    return _first_reasons(sessions, flags, REASONS_EXPERIMENT1,
                          [*_KEY, "assignment_id"])


def _at_chance(answered: pd.DataFrame, sessions_with_rows: pd.Index) -> pd.Series:
    """Per session with saved questions: neither the answers correct by the statements nor the
    answers consistent with the real-world order beat chance (``_CHANCE_ALPHA``)."""
    groups = [answered[c] for c in _KEY]
    counts = pd.DataFrame({
        "n": answered.groupby(groups).size(),
        "k_statements": _flag(answered["is_correct"]).groupby(groups).sum(),
        "k_real_world": _flag(answered["is_real_world_consistent"]).groupby(groups).sum(),
    }).reindex(sessions_with_rows, fill_value=0)
    return pd.Series(
        [binomial_upper_tail(int(r.k_statements), int(r.n)) >= _CHANCE_ALPHA
         and binomial_upper_tail(int(r.k_real_world), int(r.n)) >= _CHANCE_ALPHA
         for r in counts.itertuples()],
        index=counts.index, dtype=bool)


def exclusions_experiment2(
    sessions: pd.DataFrame, trials: pd.DataFrame, participant_set: str
) -> pd.DataFrame:
    """One row per session: ``participant``, ``session_index``, ``assignment_id``,
    ``condition``, ``reason``.

    ``reason`` is the first rule of ``REASONS_EXPERIMENT2`` the session matches under
    ``participant_set`` (``retained`` or ``all_finishers``), null when the session is kept.
    Rules 3-5 apply to sessions that saved at least one question.
    """
    if participant_set not in PARTICIPANT_SETS:
        raise ValueError(f"participant_set must be one of {PARTICIPANT_SETS}, "
                         f"not {participant_set!r}")
    sessions_with_rows = pd.MultiIndex.from_frame(trials[_KEY].drop_duplicates())
    answered = trials[~_flag(trials["is_timed_out"])]
    keys = answered[answered["response_side"].notna()]
    key_counts = keys.groupby([*_KEY, "response_side"]).size()
    same_key_share = (key_counts.groupby(level=_KEY).max()
                      / key_counts.groupby(level=_KEY).sum())
    timed = answered[answered["rt"].notna()]
    reasons = [r for r in REASONS_EXPERIMENT2
               if participant_set == "retained" or r != "random_responder"]
    flags = {
        "not_completed": ~_flag(sessions["is_completed"]).to_numpy(),
        "repeat": _repeats(sessions, ["assignment_id", "session_index"]),
        "random_responder": _on_sessions(sessions, _at_chance(answered, sessions_with_rows)),
        "same_key": _on_sessions(sessions, same_key_share >= _MIN_SAME_KEY_SHARE),
        "fast_responses": _on_sessions(
            sessions, _share(timed["rt"] < _FAST_RT_MS, timed) >= _MIN_FAST_SHARE),
    }
    return _first_reasons(sessions, flags, reasons,
                          [*_KEY, "assignment_id", "condition"])


def participant_sets_experiment2(
    sessions: pd.DataFrame, trials: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """``exclusions_experiment2`` for each of ``PARTICIPANT_SETS``, keyed by set name."""
    return {name: exclusions_experiment2(sessions, trials, name) for name in PARTICIPANT_SETS}


def _log_rt(rt: pd.Series, answered: pd.Series) -> pd.Series:
    """The natural log of the response time on answered rows with a positive time, else NaN."""
    rt = rt.astype(float)
    return np.log(rt.where(answered & (rt > 0)))


def _outliers(log_rt: pd.Series, by: pd.DataFrame) -> pd.Series:
    """``|z| > _OUTLIER_Z``, z of ``log_rt`` within the groups of ``by`` (SD with ddof 1), as
    a non-null boolean; rows without a log response time or with an undefined z are false."""
    ok = log_rt.notna()
    grouped = log_rt[ok].groupby([by.loc[ok, c] for c in by.columns])
    z = (log_rt[ok] - grouped.transform("mean")) / grouped.transform("std", ddof=1)
    flags = pd.Series(False, index=log_rt.index)
    flags[ok] = (z.abs() > _OUTLIER_Z).to_numpy()
    return flags.astype("boolean")


def rt_frame_experiment1_models(trials: pd.DataFrame) -> pd.DataFrame:
    """The Experiment 1 response-time rows for the mixed-effects models, with outliers flagged.

    ``trials`` are the kept sessions' rows; practice rows are dropped, leaving the learning and
    test rows. Timed-out and incorrect trials are dropped except in the arbitrage test, which
    passes through whole. ``log_rt`` is the natural log of ``rt``, and the boolean
    ``rt_trimmed`` flags outliers, ``|z| > 3`` with z computed from ``log_rt`` within each
    session and phase (one session per kept participant) with SD ddof 1; a row whose z is
    undefined (an arbitrage timeout, or a row alone in its group) is not flagged. The models
    use the unflagged rows. Counts in the data tables: 8,800 learning and test rows, 7,555 after the
    filter, 27 flagged (learning 18 of 3,477, ICL test 1 of 1,252, IWL test 3 of 1,226,
    arbitrage test 5 of 1,600), leaving 7,528.
    """
    rows = trials[trials["phase"].isin(TASK_PHASES)]
    answered = ~_flag(rows["is_timed_out"])
    rows = rows.assign(log_rt=_log_rt(rows["rt"], answered))
    rows = rows[(rows["phase"] == _ARBITRAGE_PHASE) | (answered & _flag(rows["is_correct"]))]
    return rows.assign(rt_trimmed=_outliers(rows["log_rt"], rows[[*_KEY, "phase"]]))


def rt_frame_experiment1_figures(trials: pd.DataFrame) -> pd.DataFrame:
    """The Experiment 1 response-time rows the figures use: in ms, without outlier removal.

    ``trials`` are the kept sessions' rows; practice rows and rows without a response time are
    dropped. Timed-out trials are dropped and only correct trials are kept, except in the
    arbitrage test, where both response classes are kept and split by the figures. The panels
    apply the same filter to the rows they are given, then take participant medians and the
    mean and standard error across participants. The response times the paper reports
    (``summaries``) come from this frame.
    """
    rows = trials[trials["phase"].isin(TASK_PHASES)]
    answered = ~_flag(rows["is_timed_out"]) & rows["rt"].notna()
    keep = answered & ((rows["phase"] == _ARBITRAGE_PHASE) | _flag(rows["is_correct"]))
    return rows[keep]


def rt_trimmed_experiment2(trials: pd.DataFrame) -> pd.DataFrame:
    """``trials`` with ``log_rt`` and the boolean ``rt_trimmed``, which flags outliers for figures.

    z is computed from ``log_rt`` over all answered main questions (correct and incorrect)
    within each session (one session per participant in either participant set), with SD
    ddof 1, and ``rt_trimmed`` flags ``|z| > 3``; it is false on
    timed-out questions, whose ``log_rt`` is NaN. The panels then keep answered, correct,
    unflagged questions (``rt_kept_experiment2``). Counts in the data tables: retained, 26 of
    4,732 answered questions flagged (16 congruent, 10 shuffled), 20 of them correct (15 and 5),
    so the panels keep 3,990 of the 4,010 correct questions (2,233 and 1,757); all finishers, 31
    of 5,493 flagged, 23 of them correct, keeping 4,383 of 4,406. The models remove outliers by
    a different rule, inside R: z over the correct answered questions only. Raises if
    ``is_timed_out`` has nulls.
    """
    log_rt = _log_rt(trials["rt"], ~as_bool(trials["is_timed_out"], "rt_trimmed_experiment2"))
    return trials.assign(log_rt=log_rt, rt_trimmed=_outliers(log_rt, trials[_KEY]))


def rt_kept_experiment2(trials: pd.DataFrame) -> pd.Series:
    """Whether each question of ``rt_trimmed_experiment2`` enters the response-time figures and
    summaries: answered, correct and not flagged. Raises if a flag column has nulls."""
    timed_out, correct, flagged = (as_bool(trials[c], "rt_kept_experiment2")
                                   for c in ("is_timed_out", "is_correct", "rt_trimmed"))
    return ~timed_out & correct & ~flagged


def _in_kept_sessions(df: pd.DataFrame, exclusions: pd.DataFrame) -> np.ndarray:
    """Whether each row of ``df`` belongs to a session that ``exclusions`` keeps."""
    keys = pd.MultiIndex.from_frame(exclusions.loc[exclusions["reason"].isna(), _KEY])
    return pd.MultiIndex.from_frame(df[_KEY]).isin(keys)


def kept_rows(df: pd.DataFrame, exclusions: pd.DataFrame) -> pd.DataFrame:
    """The rows of ``df`` (any table with the session key) from the sessions an exclusion frame
    keeps (``reason`` null), in the order of ``df``."""
    return df[_in_kept_sessions(df, exclusions)]


def _write(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_parquet(path, index=False)
    return path


def load_experiment1(
    root: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Experiment 1's ``sessions`` and ``trials`` tables under ``root`` (``tables.load``) and
    their ``exclusions_experiment1``."""
    sessions = tables.load("sessions", "experiment1", root)
    trials = tables.load("trials", "experiment1", root)
    return sessions, trials, exclusions_experiment1(sessions, trials)


def load_experiment2(
    root: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    """Experiment 2's ``sessions``, ``trials`` and ``questionnaire`` tables under ``root``
    (``tables.load``) and their ``participant_sets_experiment2``."""
    sessions = tables.load("sessions", "experiment2", root)
    trials = tables.load("trials", "experiment2", root)
    questionnaire = tables.load("questionnaire", "experiment2", root)
    return sessions, trials, questionnaire, participant_sets_experiment2(sessions, trials)


def write_r_inputs(
    out_dir: Path, root: Path | None = None, *,
    experiment1: tuple | None = None, experiment2: tuple | None = None,
) -> dict[str, Path]:
    """Write the tables the R models read into ``out_dir`` and return their paths by name.

    Experiment 1 (``experiment1/``): ``exclusions`` (``exclusions_experiment1``), ``trials``
    (the kept sessions' learning and test rows; the accuracy models count timeouts as
    incorrect) and ``rt`` (the unflagged rows of ``rt_frame_experiment1_models``, with
    ``log_rt``). Experiment 2 (``experiment2/``): ``sessions`` with each participant set's
    ``reason_<set>`` and boolean ``<set>``, and ``trials`` and ``questionnaire`` with the
    boolean ``<set>`` of each row's session; the models' own outlier removal happens in R.
    Names are ``<experiment>/<table>``; columns and values are the data tables' own. Rows are
    in table order, except Experiment 1's ``trials`` and ``rt``: by the session's
    ``start_order``, then ``trial_index``, the order that reproduces the reported model results.
    ``experiment1`` and ``experiment2`` are what ``load_experiment1`` and ``load_experiment2``
    return; each is loaded from ``root`` when not given.
    """
    out_dir = Path(out_dir)
    paths = {}

    sessions, trials, exclusions = (
        experiment1 if experiment1 is not None else load_experiment1(root))
    kept = kept_rows(trials, exclusions)
    kept = kept[kept["phase"].isin(TASK_PHASES)]
    # Both model inputs are sorted by session start, then trial (the response-time rows keep this
    # order): the models' standard errors and degrees of freedom depend slightly on row order.
    start_order = sessions.set_index(_KEY)["start_order"]
    kept = kept.assign(start_order=start_order.reindex(
        pd.MultiIndex.from_frame(kept[_KEY])).array).sort_values(
        ["start_order", "trial_index"], kind="stable")
    rt = rt_frame_experiment1_models(kept)
    frames = {
        "exclusions": exclusions,
        "trials": kept[trials.columns],
        "rt": rt.loc[~_flag(rt["rt_trimmed"]), [*trials.columns, "log_rt"]],
    }
    for name, df in frames.items():
        paths[f"experiment1/{name}"] = _write(df, out_dir / "experiment1" / f"{name}.parquet")

    sessions, trials, questionnaire, sets = (
        experiment2 if experiment2 is not None else load_experiment2(root))
    sessions = sessions.reset_index(drop=True)
    for name, exclusions in sets.items():
        sessions[f"reason_{name}"] = exclusions["reason"].array
    for name, exclusions in sets.items():
        sessions[name] = pd.array(exclusions["reason"].isna().to_numpy(), dtype="boolean")
    frames = {"sessions": sessions}
    for table, df in (("trials", trials), ("questionnaire", questionnaire)):
        frames[table] = df.assign(**{
            name: pd.array(_in_kept_sessions(df, exclusions), dtype="boolean")
            for name, exclusions in sets.items()})
    for name, df in frames.items():
        paths[f"experiment2/{name}"] = _write(df, out_dir / "experiment2" / f"{name}.parquet")
    return paths
