"""Descriptive statistics: participant means, rank correlation, each participant's own estimates,
and the paper's numbers.

``participant_mean_sem`` is the averaging rule of every human panel: aggregate within each
participant first (mean accuracy or median response time per participant and x value), then
take the mean and standard error across participants. Participants are the only averaged axis.
The participant figures draw the first step alone, with each participant's own uncertainty
over their trials (``participant_accuracy_by_distance``, ``participant_rt_by_distance``,
``participant_slopes_experiment1``).
"""

from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from geo_alg_ti_humans import REPO_ROOT, prepare, tables


def participant_mean_sem(
    df: pd.DataFrame,
    *,
    x_col: str,
    value_col: str,
    participant_col: str = "participant",
    agg: str = "mean",
):
    """Per-participant aggregate, then mean and standard error across participants.

    Step 1 pivots to x values by participants with ``agg`` ("mean" for accuracy, "median" for
    response time). Step 2 averages across participants, skipping missing values; the standard
    error uses ddof 1.

    Returns ``(summary, wide)``: ``summary`` has the columns ``[x_col, value_mean, value_sem,
    n_participants]``; ``wide`` is the per-participant table (index = x values, columns =
    participants) for drawing individual points.
    """
    work = df[[x_col, participant_col]].copy()
    work["_value"] = df[value_col].astype(float)
    wide = work.pivot_table(index=x_col, columns=participant_col, values="_value", aggfunc=agg)
    summary = pd.DataFrame({
        x_col: wide.index.to_numpy(),
        "value_mean": wide.mean(axis=1).to_numpy(),
        "value_sem": wide.sem(axis=1).to_numpy(),
        "n_participants": wide.notna().sum(axis=1).to_numpy(),
    })
    return summary, wide


def spearman_rho(x, y) -> float:
    """Spearman's rank correlation: Pearson's r on average ranks.

    Pairs with a missing value on either axis are dropped. NaN when fewer than two pairs remain
    or when either axis has no rank variance at all (every value tied), where a correlation is
    undefined rather than zero.
    """
    xs = pd.Series(np.asarray(x, dtype=float))
    ys = pd.Series(np.asarray(y, dtype=float))
    ok = xs.notna() & ys.notna()
    xs, ys = xs[ok], ys[ok]
    if len(xs) < 2:
        return float("nan")
    rx = xs.rank(method="average").to_numpy()
    ry = ys.rank(method="average").to_numpy()
    if rx.std() == 0.0 or ry.std() == 0.0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def _distance_coef(log_rt, distance, trial) -> float:
    """The distance coefficient of the least-squares fit ``log_rt ~ 1 + distance + trial``."""
    X = np.column_stack([np.ones(len(log_rt)), np.asarray(distance, float),
                         np.asarray(trial, float)])
    beta, *_ = np.linalg.lstsq(X, np.asarray(log_rt, float), rcond=None)
    return float(beta[1])


# A participant's response-time measures need at least this many kept questions.
_MIN_RT_QUESTIONS = 4


def participant_rt_measures(trials: pd.DataFrame) -> pd.DataFrame:
    """One row per Experiment 2 participant, from answered, correct questions not flagged outliers.

    ``trials`` are main questions with ``log_rt`` and ``rt_trimmed``
    (``prepare.rt_trimmed_experiment2``). Columns: ``participant``, ``condition``,
    ``n_questions``, ``median_rt_s`` (the median response time in seconds), ``distance_coef``
    (``b``, the symbolic distance coefficient of the least-squares fit
    ``log_rt ~ 1 + symbolic_distance + question_number``) and ``rt_slope_pct``
    (``100 * (exp(b) - 1)``, the percent change in response time per unit of symbolic distance).

    Raises if a flag column has nulls, if a participant carries two conditions, if a kept
    question has no response time, or if a participant has fewer than four kept questions or
    fewer than two distinct distances among them: no participant is dropped silently.
    """
    fname = "participant_rt_measures"
    keep = trials[prepare.rt_kept_experiment2(trials)]
    conds = trials.groupby("participant")["condition"].agg(["nunique", "first"])
    if (conds["nunique"] != 1).any():
        raise ValueError(f"{fname}: participants without exactly one condition: "
                         f"{sorted(conds.index[conds['nunique'] != 1])}")
    if keep["rt"].isna().any() or keep["log_rt"].isna().any():
        raise ValueError(f"{fname}: an answered question has no response time")
    kept_by_participant = dict(tuple(keep.groupby("participant", sort=False)))
    rows = []
    for participant, condition in conds["first"].items():
        sub = kept_by_participant.get(participant, keep.iloc[:0])
        distances = sub["symbolic_distance"]
        if len(sub) < _MIN_RT_QUESTIONS or distances.nunique() < 2:
            raise ValueError(f"{fname}: participant {participant} has {len(sub)} kept "
                             f"questions over {distances.nunique()} distances")
        b = _distance_coef(sub["log_rt"], distances, sub["question_number"])
        rows.append({
            "participant": participant,
            "condition": condition,
            "n_questions": int(len(sub)),
            "median_rt_s": float(sub["rt"].median() * 0.001),
            "distance_coef": b,
            "rt_slope_pct": float(100.0 * (np.exp(b) - 1.0)),
        })
    return pd.DataFrame(rows)


# Each participant's own estimates
#
# The participant figures draw one participant at a time, so their uncertainty is over that
# participant's trials: a 68% Wilson interval for a proportion (``z`` = 1, the binomial
# counterpart of a band of one standard error) and the bootstrap standard deviation for a median
# or a slope. Every bootstrap takes one seeded generator per call and draws from it in sorted
# order of participant, series and distance, so the same inputs give the same values.

def wilson_interval(k, n, *, z: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """The Wilson score interval of ``k`` successes in ``n`` trials, elementwise.

    ``z`` = 1 gives the 68% interval. Returns ``(low, high)``; raises if a count of trials is
    not positive or ``k`` falls outside 0 to ``n``.
    """
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    if (n <= 0).any() or (k < 0).any() or (k > n).any():
        raise ValueError("wilson_interval: needs 0 <= k <= n and n > 0")
    p = k / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    half = z * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return center - half, center + half


def bootstrap_sd_median(values, *, n_boot: int, rng: np.random.Generator) -> float:
    """The standard deviation (ddof 1) of the median over ``n_boot`` resamples of ``values``.

    A single value has no spread and gives 0 without drawing from ``rng``; no values raises.
    """
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        raise ValueError("bootstrap_sd_median: no values")
    if x.size == 1:
        return 0.0
    idx = rng.integers(0, x.size, size=(n_boot, x.size))
    return float(np.median(x[idx], axis=1).std(ddof=1))


def _answered_correct(trials: pd.DataFrame, fname: str) -> pd.Series:
    """True on the trials answered in time and correctly; raises if a flag has nulls."""
    return (prepare.as_bool(trials["is_correct"], fname)
            & ~prepare.as_bool(trials["is_timed_out"], fname))


def participant_accuracy_by_distance(
    trials: pd.DataFrame, *, series_col: str, distance_col: str = "symbolic_distance",
    participant_col: str = "participant", z: float = 1.0,
) -> pd.DataFrame:
    """Each participant's accuracy at each symbolic distance, per series, with its Wilson interval.

    A trial that ran out of time counts as incorrect. One row per participant, series and
    distance with trials, in sorted order: the key columns, ``n_trials``, ``n_correct``,
    ``value`` (the proportion correct), ``low`` and ``high``.
    """
    correct = _answered_correct(trials, "participant_accuracy_by_distance")
    keys = [participant_col, series_col, distance_col]
    work = trials[keys].assign(_correct=correct.astype(int))
    out = (work.groupby(keys, sort=True, observed=True)["_correct"]
           .agg(n_trials="count", n_correct="sum").reset_index())
    out["value"] = out["n_correct"] / out["n_trials"]
    out["low"], out["high"] = wilson_interval(out["n_correct"], out["n_trials"], z=z)
    return out


def participant_rt_by_distance(
    trials: pd.DataFrame, *, series_col: str, distance_col: str = "symbolic_distance",
    participant_col: str = "participant", exclude_col: str | None = None,
    n_boot: int = 1000, seed: int = 0,
) -> pd.DataFrame:
    """Each participant's median response time at each symbolic distance, per series, in seconds.

    Uses the answered, correct trials with a response time, as the response-time panels do;
    ``exclude_col`` names a boolean column without nulls whose true rows are dropped first (the
    outlier flag ``rt_trimmed``). One row per participant, series and distance with such trials,
    in sorted order: the key columns, ``n_trials``, ``value`` (the median), ``sd`` (the bootstrap
    standard deviation of the median, ``bootstrap_sd_median``; 0 on a single trial), ``low`` and
    ``high`` (``value`` minus and plus ``sd``). A distance without such trials has no row.
    """
    fname = "participant_rt_by_distance"
    keep = _answered_correct(trials, fname) & trials["rt"].notna()
    if exclude_col is not None:
        keep &= ~prepare.as_bool(trials[exclude_col], fname)
    keys = [participant_col, series_col, distance_col]
    rows = trials.loc[keep, keys].assign(_rt_s=trials.loc[keep, "rt"].astype(float) * 0.001)
    rng = np.random.default_rng(seed)
    records = []
    for key, group in rows.groupby(keys, sort=True, observed=True):
        x = group["_rt_s"].to_numpy()
        median = float(np.median(x))
        sd = bootstrap_sd_median(x, n_boot=n_boot, rng=rng)
        records.append({**dict(zip(keys, key)), "n_trials": int(x.size), "value": median,
                        "sd": sd, "low": median - sd, "high": median + sd})
    columns = [*keys, "n_trials", "value", "sd", "low", "high"]
    return pd.DataFrame(records, columns=columns)


def _ols_slope(distance: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The least-squares slope of ``y`` on ``distance`` along the last axis."""
    d = distance - distance.mean(axis=-1, keepdims=True)
    return (d * (y - y.mean(axis=-1, keepdims=True))).sum(axis=-1) / (d * d).sum(axis=-1)


def _slope_and_sd(distance, y, *, n_boot: int, rng: np.random.Generator,
                  transform=None) -> tuple[float, float]:
    """The slope of ``y`` on ``distance`` and its bootstrap standard deviation (ddof 1).

    Each resample draws, with replacement, as many trials at each distance as were observed
    there, so every resample keeps the observed distances. ``transform`` maps a slope to the
    reported scale before the spread is taken.
    """
    distance = np.asarray(distance, dtype=float)
    y = np.asarray(y, dtype=float)
    groups = [np.flatnonzero(distance == v) for v in np.unique(distance)]
    idx = np.concatenate(
        [g[rng.integers(0, g.size, size=(n_boot, g.size))] for g in groups], axis=1)
    estimate, replicates = _ols_slope(distance, y), _ols_slope(distance[idx], y[idx])
    if transform is not None:
        estimate, replicates = transform(estimate), transform(replicates)
    return float(estimate), float(np.std(replicates, ddof=1))


def _percent_per_unit(b):
    return 100.0 * (np.exp(b) - 1.0)


def participant_slopes_experiment1(
    trials: pd.DataFrame, *, tests: tuple[str, ...] = ("icl_test", "iwl_test"),
    n_boot: int = 1000, seed: int = 0,
) -> pd.DataFrame:
    """Each Experiment 1 participant's symbolic-distance slopes on each test, with their spread.

    ``trials`` are the kept participants' trials (``experiment1_trials``). Per participant and
    test: ``accuracy_slope``, the least-squares slope of correct (1) or not (0; a timeout is
    incorrect) on symbolic distance, over every trial; ``rt_slope_pct``, ``100 * (exp(b) - 1)``
    with ``b`` the slope of the natural log of the response time on symbolic distance, over the
    answered, correct trials of ``prepare.rt_frame_experiment1_figures`` (no outlier removal,
    as in the response-time panels; the Experiment 1 models have no trial term, so neither does
    this fit). Each slope's ``_sd`` column is its bootstrap standard deviation (``n_boot``
    resamples, trials resampled within each distance). Also ``n_trials`` and ``n_rt_trials``.
    Raises if a participant has fewer than two distances on either measure of a test.
    """
    fname = "participant_slopes_experiment1"
    rows = trials[trials["phase"].isin(tests)]
    rows = rows.assign(_correct=_answered_correct(rows, fname).astype(float))
    rt_rows = prepare.rt_frame_experiment1_figures(rows)
    rt_by_key = dict(tuple(rt_rows.groupby(["participant", "phase"], sort=True, observed=True)))
    rng = np.random.default_rng(seed)
    records = []
    for (participant, test), group in rows.groupby(["participant", "phase"], sort=True,
                                                   observed=True):
        rt = rt_by_key.get((participant, test), rt_rows.iloc[:0])
        for name, sub in (("trials", group), ("answered, correct trials", rt)):
            if sub["symbolic_distance"].nunique() < 2:
                raise ValueError(f"{fname}: participant {participant} has {name} at fewer than "
                                 f"two distances on the {test}")
        accuracy, accuracy_sd = _slope_and_sd(
            group["symbolic_distance"], group["_correct"], n_boot=n_boot, rng=rng)
        slope_pct, slope_pct_sd = _slope_and_sd(
            rt["symbolic_distance"], np.log(rt["rt"].astype(float)), n_boot=n_boot, rng=rng,
            transform=_percent_per_unit)
        records.append({"participant": participant, "phase": test,
                        "n_trials": int(len(group)), "n_rt_trials": int(len(rt)),
                        "accuracy_slope": accuracy, "accuracy_slope_sd": accuracy_sd,
                        "rt_slope_pct": slope_pct, "rt_slope_pct_sd": slope_pct_sd})
    return pd.DataFrame(records)


# The paper's numbers
#
# Each function below returns named values computed from the data tables through the exclusions
# and response-time frames of ``prepare``. A key ending in ``_pct`` is a percentage, in ``_s``
# a time in seconds; a pair is a range (lowest, highest). Accuracy counts a timeout as incorrect.

_CONDITIONS = ("congruent", "shuffled")
_LEARNING_BIN = 20          # trials per bin of the learning curves
_TESTS = ("icl_test", "iwl_test")
_STATEMENTS_ITEM = "statements_true"
_KNOWLEDGE_ITEM = "knowledge_use"
_OTHER_KNOWLEDGE_ANSWERS = ("Sometimes", "Often", "Always")    # besides "Never" and "Rarely"
_CONTEXT_FOLLOWER_SHARE = 0.9   # arbitrage: at least this share of context-consistent responses
# A slope within this distance of zero is zero: the least-squares slope of a flat line comes out
# as a floating-point remainder (``plots.participants.make_slope_scatter`` counts a point this
# close to zero, its default ``edge_tol``, on the edge of its shaded region).
_FLAT_SLOPE = 1e-9

_KEY = list(tables.SESSION_KEY)


def _people(exclusions: pd.DataFrame) -> pd.DataFrame:
    """One row per person, from their last session, with ``reason`` null when any of the
    person's sessions is kept: a person excluded in every session is counted under the reason
    of their last session."""
    last = exclusions.sort_values(_KEY).groupby("participant").tail(1)
    kept = set(exclusions.loc[exclusions["reason"].isna(), "participant"])
    return last.assign(reason=last["reason"].where(~last["participant"].isin(kept)))


def _means(rows: pd.DataFrame, x_col: str, value_col: str, agg: str = "mean") -> pd.Series:
    """``participant_mean_sem``'s mean across participants, indexed by x value."""
    summary, _ = participant_mean_sem(rows, x_col=x_col, value_col=value_col, agg=agg)
    return summary.set_index(x_col)["value_mean"]


def _at(series: pd.Series, label) -> float:
    """``series[label]``, or NaN when the label is missing."""
    return float(series.reindex([label]).iloc[0])


def _span(series: pd.Series, labels) -> tuple[float, float]:
    """The lowest and highest of ``series`` at ``labels``; NaN when any label is missing."""
    values = series.reindex(list(labels))
    return (values.min(skipna=False), values.max(skipna=False))


def _rt_seconds(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.assign(rt_s=rows["rt"].astype(float) * 0.001)


def _signs(slopes: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """1, -1 or 0 for each slope, 0 within ``_FLAT_SLOPE`` of zero."""
    return ((slopes > _FLAT_SLOPE).astype(int) - (slopes < -_FLAT_SLOPE).astype(int))


def counts_experiment1(sessions: pd.DataFrame, trials: pd.DataFrame, *,
                       exclusions: pd.DataFrame | None = None) -> dict:
    """Experiment 1 participants, exclusions and response-time trial counts.

    ``people``, ``kept``, and the people excluded under each reason; ``<test>_trials`` (ICL and
    IWL test trials of the kept participants), ``<test>_rt_trials`` (correct, answered),
    ``<test>_rt_outliers`` and ``<test>_rt_trials_kept`` (after outlier removal), and the same
    over both tests without the prefix, with ``rt_outlier_pct``. ``exclusions`` is
    ``prepare.exclusions_experiment1`` of the tables, computed when not given.
    """
    if exclusions is None:
        exclusions = prepare.exclusions_experiment1(sessions, trials)
    people = _people(exclusions)
    values = {"people": len(people), "kept": int(people["reason"].isna().sum())}
    for reason in prepare.REASONS_EXPERIMENT1:
        values[reason] = int((people["reason"] == reason).sum())
    kept = prepare.kept_rows(trials, exclusions)
    frame = prepare.rt_frame_experiment1_models(kept)
    frame = frame[frame["phase"].isin(_TESTS)]
    flagged = frame["rt_trimmed"].astype(bool)
    for test in _TESTS:
        name = test.removesuffix("_test")
        in_test = frame["phase"] == test
        values[f"{name}_trials"] = int((kept["phase"] == test).sum())
        values[f"{name}_rt_trials"] = int(in_test.sum())
        values[f"{name}_rt_outliers"] = int((in_test & flagged).sum())
        values[f"{name}_rt_trials_kept"] = int((in_test & ~flagged).sum())
    values.update({
        "rt_trials": len(frame),
        "rt_outliers": int(flagged.sum()),
        "rt_outlier_pct": 100.0 * flagged.sum() / len(frame),
        "rt_trials_kept": int((~flagged).sum()),
    })
    return values


def descriptives_experiment1(sessions: pd.DataFrame, trials: pd.DataFrame, *,
                             exclusions: pd.DataFrame | None = None) -> dict:
    """Experiment 1 learning curves, per-pair response times, participant slopes and the
    arbitrage test.

    Learning (``learning_accuracy_masked_<bin>_pct``): accuracy in percent with the context
    masked, in the first and last 20-trial bin. Pairs: the ICL test's response time averaged
    over the six adjacent pairs and on the longest pair, and the range of the IWL test's
    per-pair response times. Slopes (``participant_slopes_experiment1``): the participants with
    slopes, those whose accuracy slope is positive on the IWL test and negative on the ICL test,
    and those whose response-time slope is positive on the ICL test (a slope within
    ``_FLAT_SLOPE`` of zero is neither). Arbitrage: the percentage of context-consistent
    responses, the participants choosing them on at least 90% of their trials, and the
    participants tested. A bin or pair value is the mean across participants of each
    participant's accuracy or median response time (correct, answered trials;
    ``prepare.rt_frame_experiment1_figures``); the arbitrage percentage is the mean of each
    participant's share of context-consistent responses over all their arbitrage trials (a
    timeout counts as not context-consistent). ``exclusions`` is as in ``counts_experiment1``.
    """
    if exclusions is None:
        exclusions = prepare.exclusions_experiment1(sessions, trials)
    kept = prepare.kept_rows(trials, exclusions)
    learning = kept[kept["phase"] == "learning"].sort_values([*_KEY, "trial_index"],
                                                             kind="stable")
    learning = learning.assign(bin=learning.groupby(_KEY).cumcount() // _LEARNING_BIN)
    bins = {"first": learning["bin"].min(), "last": learning["bin"].max()}
    accuracy = _means(learning[learning["context_display"] == "masked"], "bin", "is_correct")
    values = {f"learning_accuracy_masked_{name}_pct": 100.0 * _at(accuracy, b)
              for name, b in bins.items()}

    tests = _rt_seconds(prepare.rt_frame_experiment1_figures(kept[kept["phase"].isin(_TESTS)]))
    # A pair is keyed by its two ranks, the top-ranked item (rank 1) first: (1, 7) is the longest
    # pair.
    ranks = tests[["query_left_rank", "query_right_rank"]].astype(int)
    tests = tests.assign(pair=list(zip(ranks.min(axis=1), ranks.max(axis=1))))
    distance = tests.groupby("pair")["symbolic_distance"].first()
    by_pair = {test: _means(tests[tests["phase"] == test], "pair", "rt_s", "median")
               for test in _TESTS}
    icl = by_pair["icl_test"]
    values["icl_rt_adjacent_pairs_s"] = icl[distance[icl.index] == 1].mean()
    values["icl_rt_longest_pair_s"] = _at(icl, distance.idxmax() if len(distance) else None)
    values["iwl_rt_pair_range_s"] = (by_pair["iwl_test"].min(), by_pair["iwl_test"].max())

    slopes = participant_slopes_experiment1(kept).pivot(
        index="participant", columns="phase", values=["accuracy_slope", "rt_slope_pct"])
    accuracy, rt = _signs(slopes["accuracy_slope"]), _signs(slopes["rt_slope_pct"])
    values.update({
        "slope_participants": len(slopes),
        "accuracy_slope_iwl_positive_icl_negative": int(
            ((accuracy["iwl_test"] == 1) & (accuracy["icl_test"] == -1)).sum()),
        "rt_slope_icl_positive": int((rt["icl_test"] == 1).sum()),
    })

    arbitrage = kept[kept["phase"] == "arbitrage_test"]
    context = arbitrage["is_icl_consistent"].astype(bool).astype(float).groupby(
        arbitrage["participant"]).mean()
    values.update({
        "arbitrage_context_pct": 100.0 * context.mean(),
        "arbitrage_context_followers": int((context >= _CONTEXT_FOLLOWER_SHARE).sum()),
        "arbitrage_participants": len(context),
    })
    return values


def counts_experiment2(sessions: pd.DataFrame, trials: pd.DataFrame, *,
                       sets: dict[str, pd.DataFrame] | None = None) -> dict:
    """Experiment 2 participants, exclusions and question counts.

    ``people``; the people excluded under each reason of the retained set (``<reason>`` and
    ``<reason>_<condition>``) and of all finishers (``all_finishers_<reason>`` and
    ``all_finishers_<reason>_<condition>``); the participants kept in each set
    (``<set>_<condition>``); the number of retained participants (``retained``) and those of
    each wave (``wave<k>_<condition>``), of the second round of the second wave
    (``second_round_<condition>``) and with more than one session, as when a reloaded page
    started a new one (``reloaded_<condition>``); the retained participants' ``questions``,
    timeouts by condition, ``rt_questions`` (correct, answered), and the outliers the
    response-time models remove (z over those questions within each participant) with what they
    leave. ``sets`` is ``prepare.participant_sets_experiment2`` of the tables, computed when not
    given.
    """
    if sets is None:
        sets = prepare.participant_sets_experiment2(sessions, trials)
    people = _people(sets["retained"])
    values = {"people": len(people)}
    for reason in prepare.REASONS_EXPERIMENT2:
        excluded = people[people["reason"] == reason]
        values[reason] = len(excluded)
        for condition in _CONDITIONS:
            values[f"{reason}_{condition}"] = int((excluded["condition"] == condition).sum())
    finishers = _people(sets["all_finishers"])
    for reason in prepare.REASONS_EXPERIMENT2:
        excluded = finishers[finishers["reason"] == reason]
        values[f"all_finishers_{reason}"] = len(excluded)
        for condition in _CONDITIONS:
            values[f"all_finishers_{reason}_{condition}"] = int(
                (excluded["condition"] == condition).sum())
    for name, exclusions in sets.items():
        kept = exclusions[exclusions["reason"].isna()]
        for condition in _CONDITIONS:
            values[f"{name}_{condition}"] = int((kept["condition"] == condition).sum())
    retained = prepare.kept_rows(sessions, sets["retained"])
    values["retained"] = len(retained)
    reloaded = retained["participant"].map(sessions.groupby("participant").size()) > 1
    for condition in _CONDITIONS:
        in_condition = retained["condition"] == condition
        for wave in (1, 2):
            values[f"wave{wave}_{condition}"] = int(
                ((retained["wave"] == wave) & in_condition).sum())
        values[f"second_round_{condition}"] = int(
            ((retained["allocation_round"] == 2) & in_condition).sum())
        values[f"reloaded_{condition}"] = int((reloaded & in_condition).sum())

    questions = prepare.kept_rows(trials, sets["retained"])
    timed_out = questions["is_timed_out"].astype(bool)
    for condition in _CONDITIONS:
        values[f"timeouts_{condition}"] = int(
            (timed_out & (questions["condition"] == condition)).sum())
    correct = questions[~timed_out & questions["is_correct"].astype(bool)]
    outliers = prepare.rt_trimmed_experiment2(correct)["rt_trimmed"].astype(bool)
    values.update({
        "questions": len(questions),
        "rt_questions": len(correct),
        "rt_outliers": int(outliers.sum()),
        "rt_outlier_pct": 100.0 * outliers.sum() / len(correct),
        "rt_questions_kept": int((~outliers).sum()),
    })
    return values


def descriptives_experiment2(
    sessions: pd.DataFrame, trials: pd.DataFrame, questionnaire: pd.DataFrame, *,
    sets: dict[str, pd.DataFrame] | None = None,
) -> dict:
    """Experiment 2 accuracy by distance, questionnaire answers, strategies.

    Retained participants, shuffled condition, by question type (agree, conflict): accuracy at
    distance 1 and its range over distances 2-6. Questionnaire (retained, by condition): the
    participants answering how many statements were true and how often they answered from
    real-world knowledge. Strategies (retained, ``participant_rt_measures``, over correct,
    answered questions not flagged by ``prepare.rt_trimmed_experiment2``): by condition the
    median of the participants' median response times and of their slopes, and the Spearman
    correlation between the two; in the shuffled condition the median slope of the
    participants answering "Never" and "Rarely", and the range of the medians of the other
    answers. ``sets`` is as in ``counts_experiment2``.
    """
    if sets is None:
        sets = prepare.participant_sets_experiment2(sessions, trials)
    finishers = prepare.rt_trimmed_experiment2(prepare.kept_rows(trials, sets["all_finishers"]))
    retained = prepare.kept_rows(finishers, sets["retained"])
    answers = prepare.kept_rows(questionnaire, sets["retained"])

    values = {}
    shuffled = retained[retained["condition"] == "shuffled"]
    for question_type in ("agree", "conflict"):
        accuracy = _means(shuffled[shuffled["question_type"] == question_type],
                          "symbolic_distance", "is_correct")
        values.update({
            f"{question_type}_accuracy_d1": _at(accuracy, 1),
            f"{question_type}_accuracy_d2_d6": _span(accuracy, range(2, 7)),
        })

    measures = participant_rt_measures(retained)
    knowledge = answers.set_index("participant")[_KNOWLEDGE_ITEM]
    measures = measures.assign(knowledge=measures["participant"].map(knowledge))
    for condition in _CONDITIONS:
        given = answers[answers["condition"] == condition]
        m = measures[measures["condition"] == condition]
        values.update({
            f"statements_answered_{condition}": int(given[_STATEMENTS_ITEM].notna().sum()),
            f"knowledge_answered_{condition}": int(given[_KNOWLEDGE_ITEM].notna().sum()),
            f"median_rt_s_{condition}": m["median_rt_s"].median(),
            f"median_slope_pct_{condition}": m["rt_slope_pct"].median(),
            f"spearman_rho_{condition}": spearman_rho(m["median_rt_s"], m["rt_slope_pct"]),
        })
    m = measures[measures["condition"] == "shuffled"]
    slopes = m.groupby("knowledge")["rt_slope_pct"].median()
    values.update({
        "shuffled_slope_pct_never": _at(slopes, "Never"),
        "shuffled_slope_pct_rarely": _at(slopes, "Rarely"),
        "shuffled_slope_pct_other_answers": _span(slopes, _OTHER_KNOWLEDGE_ANSWERS),
    })
    return values


# Where the paper prints each number: its section, by the paper's headings.
_RESULTS_1 = "Results, Symbolic distance effects"
_RESULTS_2 = "Results, Content effects"
_METHODS_1_PARTICIPANTS = "Methods, Human experiments, Experiment 1, Participants"
_METHODS_1_ANALYSIS = "Methods, Human experiments, Experiment 1, Statistical analysis"
_METHODS_2_PARTICIPANTS = "Methods, Human experiments, Experiment 2, Participants"
_EXT_METHODS_1_PARTICIPANTS = "Extended methods, Human experiments, Experiment 1, Participants"
_EXT_METHODS_1_ANALYSIS = "Extended methods, Human experiments, Experiment 1, Statistical analysis"
_EXT_METHODS_2_PARTICIPANTS = "Extended methods, Human experiments, Experiment 2, Participants"
_EXT_METHODS_2_ANALYSIS = "Extended methods, Human experiments, Experiment 2, Statistical analysis"
_EXT_RESULTS_1_LEARNING = "Extended results, Human experiments, Experiment 1, Learning phase"
_EXT_RESULTS_1_DISTANCE = ("Extended results, Human experiments, Experiment 1, "
                           "Additional symbolic-distance results")
_EXT_RESULTS_1_ARBITRAGE = "Extended results, Human experiments, Experiment 1, Arbitrage test"
_EXT_RESULTS_2_ROBUSTNESS = "Extended results, Human experiments, Experiment 2, Robustness"
_EXT_RESULTS_2_ROBUSTNESS_FIGURE = ("Extended results, Human experiments, Experiment 2, "
                                    "Robustness, figure caption")
_EXT_RESULTS_2_AGREE_CONFLICT = ("Extended results, Human experiments, Experiment 2, "
                                 "Agree and conflict questions")
_EXT_RESULTS_2_STRATEGIES = ("Extended results, Human experiments, Experiment 2, "
                             "Strategies and self-reports")
_EXT_RESULTS_2_STRATEGIES_FIGURE = ("Extended results, Human experiments, Experiment 2, "
                                    "Strategies and self-reports, figure panels A and B")
# Where each value comes from.
_C1 = "summaries.counts_experiment1:"
_D1 = "summaries.descriptives_experiment1:"
_C2 = "summaries.counts_experiment2:"
_D2 = "summaries.descriptives_experiment2:"
# The Experiment 1 model terms the paper reports: the distance slope, and its difference
# between the IWL and ICL tests.
_SLOPE = "symbolic_distance"
_BY_TEST = "symbolic_distance:phase"


def _r(model: str, participant_set: str, term: str, column: str) -> str:
    """The source of a model result: a row of ``results/experiment<k>/models.csv``."""
    return f"R:{model}:{participant_set}:{term}:{column}"


# Every number the paper prints about the participants, exclusions, trials, descriptive
# statistics and models of the two experiments, in its text and on its figures, except the
# participants' demographics, which the data tables do not hold, and the tests of the Experiment 2
# effects within each wave, which ``results/experiment2/models.csv`` does not report; the
# paper's tables of the main models come from ``stats_tables``. A number the paper prints
# twice has a row for each place. Each has an ``id`` (``<experiment>-<n>``, numbered in the
# order the paper prints them), the ``experiment``, the ``site`` (the section or figure that
# prints it), the ``printed`` text, and the ``source`` of the value,
# ``summaries.<function>:<key>`` or
# ``R:<model>:<set>:<term>:<column>`` (a row of ``results/experiment<k>/models.csv``). A range
# is printed "low--high", "low to high" or "low and high".
# A source may also be a tuple ``(how, source, ...)``: the ``max``, ``min`` or ``range`` of
# them, or the value they all share (``same``).
PAPER_NUMBERS: tuple[tuple[str, int, str, str, str | tuple[str, ...]], ...] = (
    ("1-1", 1, _RESULTS_1, "40", f"{_C1}kept"),
    ("1-2", 1, _RESULTS_1, "< .001", _r("iwl_accuracy", "", _SLOPE, "p_value")),
    ("1-3", 1, _RESULTS_1, "< .001", _r("icl_accuracy", "", _SLOPE, "p_value")),
    ("1-4", 1, _RESULTS_1, "< .001", _r("accuracy_by_test", "", _BY_TEST, "p_value")),
    ("1-5", 1, _RESULTS_1, "< .001", _r("rt_by_test", "", _BY_TEST, "p_value")),
    ("1-6", 1, _RESULTS_1, "< .001", _r("icl_rt", "", _SLOPE, "p_value")),
    ("1-7", 1, _RESULTS_1, ".442", _r("iwl_rt", "", _SLOPE, "p_value")),
    ("1-8", 1, _METHODS_1_PARTICIPANTS, "65", f"{_C1}people"),
    ("1-9", 1, _METHODS_1_PARTICIPANTS, "65", f"{_C1}people"),
    ("1-10", 1, _METHODS_1_PARTICIPANTS, "13", f"{_C1}not_completed"),
    ("1-11", 1, _METHODS_1_PARTICIPANTS, "11", f"{_C1}failed_comprehension"),
    ("1-12", 1, _METHODS_1_PARTICIPANTS, "1", f"{_C1}low_learning_accuracy"),
    ("1-13", 1, _METHODS_1_PARTICIPANTS, "40", f"{_C1}kept"),
    ("1-14", 1, _METHODS_1_PARTICIPANTS, "40", f"{_C1}kept"),
    ("1-15", 1, _METHODS_1_ANALYSIS, "4", f"{_C1}rt_outliers"),
    ("1-16", 1, _METHODS_1_ANALYSIS, "2,478", f"{_C1}rt_trials"),
    ("1-17", 1, _METHODS_1_ANALYSIS, "0.16%", f"{_C1}rt_outlier_pct"),
    ("1-18", 1, _EXT_METHODS_1_PARTICIPANTS, "65", f"{_C1}people"),
    ("1-19", 1, _EXT_METHODS_1_PARTICIPANTS, "65", f"{_C1}people"),
    ("1-20", 1, _EXT_METHODS_1_PARTICIPANTS, "13", f"{_C1}not_completed"),
    ("1-21", 1, _EXT_METHODS_1_PARTICIPANTS, "11", f"{_C1}failed_comprehension"),
    ("1-22", 1, _EXT_METHODS_1_PARTICIPANTS, "1", f"{_C1}low_learning_accuracy"),
    ("1-23", 1, _EXT_METHODS_1_PARTICIPANTS, "40", f"{_C1}kept"),
    ("1-24", 1, _EXT_METHODS_1_ANALYSIS, "1,600", f"{_C1}icl_trials"),
    ("1-25", 1, _EXT_METHODS_1_ANALYSIS, "1,600", f"{_C1}iwl_trials"),
    ("1-26", 1, _EXT_METHODS_1_ANALYSIS, "1,252", f"{_C1}icl_rt_trials"),
    ("1-27", 1, _EXT_METHODS_1_ANALYSIS, "1,226", f"{_C1}iwl_rt_trials"),
    ("1-28", 1, _EXT_METHODS_1_ANALYSIS, "one", f"{_C1}icl_rt_outliers"),
    ("1-29", 1, _EXT_METHODS_1_ANALYSIS, "three", f"{_C1}iwl_rt_outliers"),
    ("1-30", 1, _EXT_METHODS_1_ANALYSIS, "1,251", f"{_C1}icl_rt_trials_kept"),
    ("1-31", 1, _EXT_METHODS_1_ANALYSIS, "1,223", f"{_C1}iwl_rt_trials_kept"),
    ("1-32", 1, _EXT_METHODS_1_ANALYSIS, "2,474", f"{_C1}rt_trials_kept"),
    ("1-33", 1, _EXT_RESULTS_1_LEARNING, "53%", f"{_D1}learning_accuracy_masked_first_pct"),
    ("1-34", 1, _EXT_RESULTS_1_LEARNING, "86%", f"{_D1}learning_accuracy_masked_last_pct"),
    ("1-35", 1, _EXT_RESULTS_1_DISTANCE, "5", f"{_D1}icl_rt_adjacent_pairs_s"),
    ("1-36", 1, _EXT_RESULTS_1_DISTANCE, "15", f"{_D1}icl_rt_longest_pair_s"),
    ("1-37", 1, _EXT_RESULTS_1_DISTANCE, "1.7 and 3.3", f"{_D1}iwl_rt_pair_range_s"),
    ("1-38", 1, _EXT_RESULTS_1_DISTANCE, "22",
     f"{_D1}accuracy_slope_iwl_positive_icl_negative"),
    ("1-39", 1, _EXT_RESULTS_1_DISTANCE, "40", f"{_D1}slope_participants"),
    ("1-40", 1, _EXT_RESULTS_1_DISTANCE, "39", f"{_D1}rt_slope_icl_positive"),
    ("1-41", 1, _EXT_RESULTS_1_DISTANCE, "40", f"{_D1}slope_participants"),
    ("1-42", 1, _EXT_RESULTS_1_ARBITRAGE, "72.5%", f"{_D1}arbitrage_context_pct"),
    ("1-43", 1, _EXT_RESULTS_1_ARBITRAGE, "40", f"{_D1}arbitrage_participants"),
    ("1-44", 1, _EXT_RESULTS_1_ARBITRAGE, "15", f"{_D1}arbitrage_context_followers"),
    ("2-1", 2, _RESULTS_2, "49", f"{_C2}retained_congruent"),
    ("2-2", 2, _RESULTS_2, "50", f"{_C2}retained_shuffled"),
    ("2-3", 2, _RESULTS_2, "< .001", _r("accuracy", "retained", "condition", "p_value")),
    ("2-4", 2, _RESULTS_2, "< .001",
     _r("accuracy", "retained", "condition:log_distance", "p_value")),
    ("2-5", 2, _RESULTS_2, "< .001", _r("accuracy", "retained", "slope_congruent", "p_value")),
    ("2-6", 2, _RESULTS_2, "< .001", _r("accuracy", "retained", "slope_shuffled", "p_value")),
    ("2-7", 2, _RESULTS_2, "< .001", _r("rt", "retained", "condition:log_distance", "p_value")),
    ("2-8", 2, _RESULTS_2, "< .001", _r("rt", "retained", "slope_shuffled", "p_value")),
    ("2-9", 2, _RESULTS_2, ".050", _r("rt", "retained", "slope_congruent", "p_value")),
    ("2-10", 2, _METHODS_2_PARTICIPANTS, "132", f"{_C2}people"),
    ("2-11", 2, _METHODS_2_PARTICIPANTS, "14", f"{_C2}not_completed"),
    ("2-12", 2, _METHODS_2_PARTICIPANTS, "18", f"{_C2}random_responder"),
    ("2-13", 2, _METHODS_2_PARTICIPANTS, "1", f"{_C2}fast_responses"),
    ("2-14", 2, _METHODS_2_PARTICIPANTS, "49", f"{_C2}retained_congruent"),
    ("2-15", 2, _METHODS_2_PARTICIPANTS, "50", f"{_C2}retained_shuffled"),
    ("2-16", 2, _METHODS_2_PARTICIPANTS, "99", f"{_C2}retained"),
    ("2-17", 2, _EXT_METHODS_2_PARTICIPANTS, "132", f"{_C2}people"),
    ("2-18", 2, _EXT_METHODS_2_PARTICIPANTS, "132", f"{_C2}people"),
    ("2-19", 2, _EXT_METHODS_2_PARTICIPANTS, "14", f"{_C2}not_completed"),
    ("2-20", 2, _EXT_METHODS_2_PARTICIPANTS, "2", f"{_C2}not_completed_congruent"),
    ("2-21", 2, _EXT_METHODS_2_PARTICIPANTS, "12", f"{_C2}not_completed_shuffled"),
    ("2-22", 2, _EXT_METHODS_2_PARTICIPANTS, "1", f"{_C2}random_responder_congruent"),
    ("2-23", 2, _EXT_METHODS_2_PARTICIPANTS, "17", f"{_C2}random_responder_shuffled"),
    ("2-24", 2, _EXT_METHODS_2_PARTICIPANTS, "2", f"{_C2}all_finishers_same_key"),
    ("2-25", 2, _EXT_METHODS_2_PARTICIPANTS, "1", f"{_C2}fast_responses_shuffled"),
    ("2-26", 2, _EXT_METHODS_2_PARTICIPANTS, "49", f"{_C2}retained_congruent"),
    ("2-27", 2, _EXT_METHODS_2_PARTICIPANTS, "50", f"{_C2}retained_shuffled"),
    ("2-28", 2, _EXT_METHODS_2_PARTICIPANTS, "One", f"{_C2}reloaded_shuffled"),
    ("2-29", 2, _EXT_METHODS_2_ANALYSIS, "4,752", f"{_C2}questions"),
    ("2-30", 2, _EXT_METHODS_2_ANALYSIS, "1", f"{_C2}timeouts_congruent"),
    ("2-31", 2, _EXT_METHODS_2_ANALYSIS, "19", f"{_C2}timeouts_shuffled"),
    ("2-32", 2, _EXT_METHODS_2_ANALYSIS, "4,010", f"{_C2}rt_questions"),
    ("2-33", 2, _EXT_METHODS_2_ANALYSIS, "22", f"{_C2}rt_outliers"),
    ("2-34", 2, _EXT_METHODS_2_ANALYSIS, "0.55%", f"{_C2}rt_outlier_pct"),
    ("2-35", 2, _EXT_METHODS_2_ANALYSIS, "3,988", f"{_C2}rt_questions_kept"),
    ("2-36", 2, _EXT_RESULTS_2_ROBUSTNESS, "two", f"{_C2}all_finishers_same_key"),
    ("2-37", 2, _EXT_RESULTS_2_ROBUSTNESS, "one", f"{_C2}all_finishers_fast_responses"),
    ("2-38", 2, _EXT_RESULTS_2_ROBUSTNESS, "49", f"{_C2}all_finishers_congruent"),
    ("2-39", 2, _EXT_RESULTS_2_ROBUSTNESS, "66", f"{_C2}all_finishers_shuffled"),
    ("2-40", 2, _EXT_RESULTS_2_ROBUSTNESS, "< .001", (
        "max",
        _r("accuracy", "all_finishers", "condition", "p_value"),
        _r("accuracy", "all_finishers", "condition:log_distance", "p_value"),
        _r("rt", "all_finishers", "condition", "p_value"),
        _r("rt", "all_finishers", "condition:log_distance", "p_value"),
    )),
    ("2-41", 2, _EXT_RESULTS_2_ROBUSTNESS, "30", f"{_C2}wave1_congruent"),
    ("2-42", 2, _EXT_RESULTS_2_ROBUSTNESS, "13", f"{_C2}wave1_shuffled"),
    ("2-43", 2, _EXT_RESULTS_2_ROBUSTNESS, "19", f"{_C2}wave2_congruent"),
    ("2-44", 2, _EXT_RESULTS_2_ROBUSTNESS, "37", f"{_C2}wave2_shuffled"),
    ("2-45", 2, _EXT_RESULTS_2_ROBUSTNESS, "< .001", (
        "max",
        _r("accuracy_waves", "retained", "condition", "p_value"),
        _r("accuracy_waves", "retained", "condition:log_distance", "p_value"),
        _r("rt_waves", "retained", "condition", "p_value"),
        _r("rt_waves", "retained", "condition:log_distance", "p_value"),
    )),
    ("2-46", 2, _EXT_RESULTS_2_ROBUSTNESS, ">= .327", (
        "min",
        _r("accuracy_waves", "retained", "condition:wave", "p_value"),
        _r("accuracy_waves", "retained", "condition:log_distance:wave", "p_value"),
        _r("rt_waves", "retained", "condition:wave", "p_value"),
        _r("rt_waves", "retained", "condition:log_distance:wave", "p_value"),
    )),
    ("2-47", 2, _EXT_RESULTS_2_ROBUSTNESS, "< .001", (
        "max",
        _r("accuracy_without_round_2", "retained", "condition", "p_value"),
        _r("accuracy_without_round_2", "retained", "condition:log_distance", "p_value"),
        _r("rt_without_round_2", "retained", "condition", "p_value"),
        _r("rt_without_round_2", "retained", "condition:log_distance", "p_value"),
    )),
    ("2-48", 2, _EXT_RESULTS_2_ROBUSTNESS, "seven", f"{_C2}second_round_congruent"),
    ("2-49", 2, _EXT_RESULTS_2_ROBUSTNESS, "99", (
        "same",
        _r("accuracy_leave_one_out", "retained", "refits", "estimate"),
        _r("rt_leave_one_out", "retained", "refits", "estimate"),
    )),
    ("2-50", 2, _EXT_RESULTS_2_ROBUSTNESS, "seven", f"{_C2}second_round_congruent"),
    ("2-51", 2, _EXT_RESULTS_2_ROBUSTNESS, ".050",
     _r("rt", "retained", "slope_congruent", "p_value")),
    ("2-52", 2, _EXT_RESULTS_2_ROBUSTNESS, ".047 to .069", (
        "range",
        _r("rt", "all_finishers", "slope_congruent", "p_value"),
        _r("rt_waves", "retained", "slope_congruent", "p_value"),
        _r("rt_without_round_2", "retained", "slope_congruent", "p_value"),
    )),
    ("2-53", 2, _EXT_RESULTS_2_ROBUSTNESS_FIGURE, "49", f"{_C2}all_finishers_congruent"),
    ("2-54", 2, _EXT_RESULTS_2_ROBUSTNESS_FIGURE, "66", f"{_C2}all_finishers_shuffled"),
    ("2-55", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".76", f"{_D2}conflict_accuracy_d1"),
    ("2-56", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".95", f"{_D2}agree_accuracy_d1"),
    ("2-57", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".56--.61", f"{_D2}conflict_accuracy_d2_d6"),
    ("2-58", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".83--.87", f"{_D2}agree_accuracy_d2_d6"),
    ("2-59", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "-1.749",
     _r("agree_conflict_accuracy", "retained", "type", "estimate")),
    ("2-60", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "0.117",
     _r("agree_conflict_accuracy", "retained", "type", "std_error")),
    ("2-61", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "-14.94",
     _r("agree_conflict_accuracy", "retained", "type", "statistic")),
    ("2-62", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "< .001",
     _r("agree_conflict_accuracy", "retained", "type", "p_value")),
    ("2-63", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".783",
     _r("agree_conflict_accuracy", "retained", "type:log_distance", "p_value")),
    ("2-64", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".018",
     _r("agree_conflict_accuracy_participant_level", "retained", "type:log_distance", "p_value")),
    ("2-65", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "0.084",
     _r("agree_conflict_rt", "retained", "type", "estimate")),
    ("2-66", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "0.029",
     _r("agree_conflict_rt", "retained", "type", "std_error")),
    ("2-67", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "1668.44",
     _r("agree_conflict_rt", "retained", "type", "df")),
    ("2-68", 2, _EXT_RESULTS_2_AGREE_CONFLICT, "2.93",
     _r("agree_conflict_rt", "retained", "type", "statistic")),
    ("2-69", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".003",
     _r("agree_conflict_rt", "retained", "type", "p_value")),
    ("2-70", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".535",
     _r("agree_conflict_rt_participant_level", "retained", "type", "p_value")),
    ("2-71", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".772",
     _r("agree_conflict_rt_all_answered", "retained", "type", "p_value")),
    ("2-72", 2, _EXT_RESULTS_2_AGREE_CONFLICT, ".002",
     _r("agree_conflict_rt_waves", "retained", "type:wave", "p_value")),
    ("2-73", 2, _EXT_RESULTS_2_STRATEGIES, "1.9", f"{_D2}median_rt_s_congruent"),
    ("2-74", 2, _EXT_RESULTS_2_STRATEGIES, "-3.3%", f"{_D2}median_slope_pct_congruent"),
    ("2-75", 2, _EXT_RESULTS_2_STRATEGIES, "10.3", f"{_D2}median_rt_s_shuffled"),
    ("2-76", 2, _EXT_RESULTS_2_STRATEGIES, "+9.6%", f"{_D2}median_slope_pct_shuffled"),
    ("2-77", 2, _EXT_RESULTS_2_STRATEGIES, ".48", f"{_D2}spearman_rho_congruent"),
    ("2-78", 2, _EXT_RESULTS_2_STRATEGIES, ".61", f"{_D2}spearman_rho_shuffled"),
    ("2-79", 2, _EXT_RESULTS_2_STRATEGIES, "14%", f"{_D2}shuffled_slope_pct_never"),
    ("2-80", 2, _EXT_RESULTS_2_STRATEGIES, "16%", f"{_D2}shuffled_slope_pct_rarely"),
    ("2-81", 2, _EXT_RESULTS_2_STRATEGIES, "0--5%", f"{_D2}shuffled_slope_pct_other_answers"),
    ("2-82", 2, _EXT_RESULTS_2_STRATEGIES_FIGURE, "49",
     f"{_D2}statements_answered_congruent"),
    ("2-83", 2, _EXT_RESULTS_2_STRATEGIES_FIGURE, "50", f"{_D2}statements_answered_shuffled"),
    ("2-84", 2, _EXT_RESULTS_2_STRATEGIES_FIGURE, "48", f"{_D2}knowledge_answered_congruent"),
    ("2-85", 2, _EXT_RESULTS_2_STRATEGIES_FIGURE, "50", f"{_D2}knowledge_answered_shuffled"),
)

_WORDS = ("none", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
_RANGE = re.compile(r"^(.+?)(--| and | to )(.+)$")
_NUMBER = re.compile(r"^([+-]?)(\d[\d,]*)?(?:\.(\d+))?(%?)$")
# Values are snapped to this many significant digits before rounding, so that a value stored in
# binary just below a tie (0.755 as 0.75499...) rounds as the tie it is.
_SIGNIFICANT_DIGITS = 12


def _round_half_up(value: float, decimals: int) -> Decimal:
    """``value`` rounded to ``decimals`` places, ties away from zero."""
    exact = Decimal(f"{float(value):.{_SIGNIFICANT_DIGITS}g}")
    return exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def _format_like(value, printed: str) -> str:
    """``value`` written as ``printed`` writes its number: the same decimals, rounded half away
    from zero; a thousands separator, a leading zero, a plus sign and a percent sign where
    ``printed`` has them; a number word ("none", "one", ...) for a printed word; "< x" or "> x"
    while the value is on that side of x, and ">= x" or "<= x" while the value, written as x
    is, is x or on that side of it (x a plain decimal). A range ("a--b", "a and b", "a to b")
    takes a pair.
    A value that could not be computed (NaN) is written "nan", which matches no printed value.
    """
    parts = _RANGE.match(printed)
    if parts:
        low, high = value
        return _format_like(low, parts[1]) + parts[2] + _format_like(high, parts[3])
    if printed[:3] in (">= ", "<= "):
        written = _format_like(value, printed[3:])
        if written == "nan":
            return written
        holds = (float(written) >= float(printed[3:]) if printed[0] == ">"
                 else float(written) <= float(printed[3:]))
        return printed if holds else written
    if printed[:2] in ("< ", "> "):
        bound = printed[2:]
        holds = value < float(bound) if printed[0] == "<" else value > float(bound)
        return printed if holds else _format_like(value, bound)
    if printed.lower() in _WORDS:
        whole = float(value).is_integer() and 0 <= value < len(_WORDS)
        word = _WORDS[int(value)] if whole else str(value)
        return word.capitalize() if printed[0].isupper() else word
    number = _NUMBER.match(printed)
    if number is None:
        raise ValueError(f"no number format in {printed!r}")
    sign, whole, fraction, percent = number.groups()
    if math.isnan(float(value)):
        return "nan"
    rounded = _round_half_up(value, len(fraction or ""))
    text = format(abs(rounded), ",f" if whole and "," in whole else "f")
    if whole is None and text.startswith("0."):
        text = text[1:]
    if rounded < 0:
        text = "-" + text
    elif sign == "+" and rounded > 0:
        text = "+" + text
    return text + percent


def _r_value(source: str, experiment: int, results_dir: Path, models: dict) -> float:
    """The value an ``R:<model>:<set>:<term>:<column>`` source names (a term may contain ':');
    NaN for an empty field, R's missing value."""
    _, model, participant_set, *term, column = source.split(":")
    path = results_dir / f"experiment{experiment}" / "models.csv"
    if path not in models:
        if not path.is_file():
            raise FileNotFoundError(f"{path} is missing: run the R models first")
        models[path] = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = models[path]
    rows = df[(df["model"] == model) & (df["set"] == participant_set)
              & (df["term"] == ":".join(term))]
    if len(rows) != 1:
        raise KeyError(f"{source}: {len(rows)} rows in {path}")
    field = rows[column].iloc[0]
    return float(field) if field else math.nan


_AGGREGATES = {
    "max": max,
    "min": min,
    "range": lambda values: (min(values), max(values)),
    "same": lambda values: values[0] if len(set(values)) == 1 else math.nan,
}


def _aggregate(how: str, values: list):
    """The ``max``, ``min`` or ``range`` of ``values``, or the value they all share (``same``;
    NaN when they differ): NaN (both ends of a range) when any of them is NaN, wherever it
    falls."""
    if any(math.isnan(value) for value in values):
        return (math.nan, math.nan) if how == "range" else math.nan
    return _AGGREGATES[how](values)


def _value(source, experiment: int, values: dict, results_dir: Path, models: dict):
    """The value a source names: a summary key, an R result, or an aggregate of sources."""
    if isinstance(source, tuple):
        how, *parts = source
        return _aggregate(how, [_value(part, experiment, values, results_dir, models)
                                for part in parts])
    if source.startswith("R:"):
        return _r_value(source, experiment, results_dir, models)
    return values[source]


def _source_text(source) -> str:
    """A source as written in ``results/numbers.csv``: an aggregate as ``how(source, ...)``."""
    if isinstance(source, tuple):
        how, *parts = source
        return f"{how}({', '.join(parts)})"
    return source


def summary_values(root: Path | None = None, *, experiment1: tuple | None = None,
                   experiment2: tuple | None = None) -> dict[str, dict]:
    """The values of the four summary functions on the data tables, by function name.

    ``root`` is the data directory (``tables.data_root()`` if None). ``experiment1`` and
    ``experiment2`` are what ``prepare.load_experiment1`` and ``prepare.load_experiment2``
    return; each is loaded from ``root`` when not given.
    """
    sessions, trials, exclusions = (
        experiment1 if experiment1 is not None else prepare.load_experiment1(root))
    values = {
        "counts_experiment1": counts_experiment1(sessions, trials, exclusions=exclusions),
        "descriptives_experiment1": descriptives_experiment1(sessions, trials,
                                                             exclusions=exclusions),
    }
    sessions, trials, questionnaire, sets = (
        experiment2 if experiment2 is not None else prepare.load_experiment2(root))
    values["counts_experiment2"] = counts_experiment2(sessions, trials, sets=sets)
    values["descriptives_experiment2"] = descriptives_experiment2(sessions, trials, questionnaire,
                                                                 sets=sets)
    return values


def numbers(root: Path | None = None, results_dir: Path | None = None) -> pd.DataFrame:
    """Every number of ``PAPER_NUMBERS``, recomputed from the tables and the R results.

    One row per number: ``id``, ``experiment``, ``site`` (where the paper prints it),
    ``printed``, ``computed``, ``source`` (the function, or the R models and terms, it comes
    from) and ``match`` (whether ``computed`` rounds to ``printed`` at the printed precision).
    ``root`` is the data directory (``tables.data_root()`` if None) and ``results_dir`` holds
    ``experiment<k>/models.csv`` (``results/`` in the repository if None).
    """
    results_dir = Path(results_dir) if results_dir is not None else REPO_ROOT / "results"
    values = {f"summaries.{name}:{key}": value
              for name, function_values in summary_values(root).items()
              for key, value in function_values.items()}
    models: dict = {}
    rows = []
    for id_, experiment, site, printed, source in PAPER_NUMBERS:
        computed = _format_like(_value(source, experiment, values, results_dir, models), printed)
        rows.append({"id": id_, "experiment": experiment, "site": site, "printed": printed,
                     "computed": computed, "source": _source_text(source),
                     "match": computed == printed})
    return pd.DataFrame(rows)
