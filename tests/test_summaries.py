"""Participant means, rank correlation, per-participant response-time measures, and the numbers."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from geo_alg_ti_humans import prepare, summaries


def _rt_rows() -> pd.DataFrame:
    """One participant whose log response time is exactly 7 + 0.1 * distance + 0.01 * question."""
    rows = []
    for d in range(1, 7):
        for q in (1, 25, 48):
            rt = math.exp(7.0 + 0.1 * d + 0.01 * q)
            rows.append({"participant": "P001", "condition": "shuffled", "symbolic_distance": d,
                         "question_number": q, "rt": rt, "log_rt": math.log(rt),
                         "is_timed_out": False, "is_correct": True, "rt_trimmed": False})
    return pd.DataFrame(rows)


def test_participant_mean_sem_aggregates_within_participant_first():
    """Each participant counts once per x value, whatever their number of trials."""
    df = pd.DataFrame({
        "participant": ["P001", "P001", "P001", "P002"],
        "symbolic_distance": [1, 1, 2, 1],
        "is_correct": [1, 0, 1, 1],
    })
    summary, wide = summaries.participant_mean_sem(
        df, x_col="symbolic_distance", value_col="is_correct")
    d1 = summary[summary["symbolic_distance"] == 1].iloc[0]
    assert d1["value_mean"] == pytest.approx(0.75)
    assert d1["value_sem"] == pytest.approx(0.25)
    assert d1["n_participants"] == 2
    d2 = summary[summary["symbolic_distance"] == 2].iloc[0]
    assert d2["value_mean"] == 1.0 and math.isnan(d2["value_sem"]) and d2["n_participants"] == 1
    assert list(wide.columns) == ["P001", "P002"]


def test_participant_mean_sem_takes_medians_for_response_times():
    """With ``agg="median"``, each participant contributes their median."""
    df = pd.DataFrame({
        "participant": ["P001", "P001", "P001", "P002"],
        "symbolic_distance": [1, 1, 1, 1],
        "rt": [100.0, 200.0, 900.0, 300.0],
    })
    summary, _ = summaries.participant_mean_sem(
        df, x_col="symbolic_distance", value_col="rt", agg="median")
    assert summary["value_mean"].iloc[0] == pytest.approx(250.0)


def test_participant_mean_sem_participant_column_is_a_keyword():
    """Any column can serve as the participant key."""
    df = pd.DataFrame({"assignment_id": [3, 3, 7], "x": [1, 1, 1], "v": [0.0, 1.0, 1.0]})
    summary, _ = summaries.participant_mean_sem(
        df, x_col="x", value_col="v", participant_col="assignment_id")
    assert summary["value_mean"].iloc[0] == pytest.approx(0.75)


def test_spearman_rho_of_monotone_relations():
    """A strictly increasing relation gives 1 and a decreasing one gives -1."""
    x = [1.0, 2.0, 3.0, 4.0]
    assert summaries.spearman_rho(x, [1.0, 4.0, 9.0, 16.0]) == pytest.approx(1.0)
    assert summaries.spearman_rho(x, [5.0, 3.0, 2.0, 0.0]) == pytest.approx(-1.0)


def test_spearman_rho_uses_average_ranks_for_ties():
    """Ties get the average of the ranks they span."""
    x, y = [1, 2, 2, 3], [1, 3, 2, 4]
    expected = np.corrcoef([1, 2.5, 2.5, 4], [1, 3, 2, 4])[0, 1]
    assert summaries.spearman_rho(x, y) == pytest.approx(expected)


def test_spearman_rho_drops_missing_pairs_and_is_nan_when_undefined():
    """Pairs with a missing value are dropped; no rank variance or fewer than two pairs is NaN."""
    assert summaries.spearman_rho([1, 2, np.nan, 4], [1, 2, 3, np.nan]) == pytest.approx(1.0)
    assert math.isnan(summaries.spearman_rho([1, 1, 1], [1, 2, 3]))
    assert math.isnan(summaries.spearman_rho([1], [2]))


def test_participant_rt_measures_slope_matches_a_hand_fit():
    """``distance_coef`` is the distance coefficient of ``log_rt ~ 1 + distance + question``."""
    rows = _rt_rows()
    out = summaries.participant_rt_measures(rows).iloc[0]
    assert out["n_questions"] == 18
    assert out["distance_coef"] == pytest.approx(0.1)
    assert out["rt_slope_pct"] == pytest.approx(100 * (math.exp(0.1) - 1))
    assert out["median_rt_s"] == pytest.approx(rows["rt"].median() * 0.001)


def test_participant_rt_measures_has_one_row_per_participant_in_key_order():
    """Rows follow the sorted participant keys, each with its own condition and questions."""
    second = _rt_rows()
    first = second.assign(participant="P001", condition="congruent").head(9)
    rows = pd.concat([second.assign(participant="P002"), first]).sample(frac=1.0, random_state=0)
    out = summaries.participant_rt_measures(rows)
    assert out["participant"].tolist() == ["P001", "P002"]
    assert out["condition"].tolist() == ["congruent", "shuffled"]
    assert out["n_questions"].tolist() == [9, 18]


def test_participant_rt_measures_refuses_too_few_questions():
    """A participant with fewer than ``min_questions`` kept questions raises."""
    with pytest.raises(ValueError):
        summaries.participant_rt_measures(_rt_rows().head(3))


# Each participant's own estimates

def test_wilson_interval_matches_a_hand_computation():
    """3 of 4 gives (0.5, 0.9) at z = 1; 0 of 1 gives (0, 0.5)."""
    low, high = summaries.wilson_interval([3, 0], [4, 1])
    assert low == pytest.approx([0.5, 0.0])
    assert high == pytest.approx([0.9, 0.5])


@pytest.mark.parametrize(("k", "n"), [(5, 4), (-1, 4), (0, 0)])
def test_wilson_interval_refuses_impossible_counts(k, n):
    with pytest.raises(ValueError):
        summaries.wilson_interval(k, n)


def test_bootstrap_sd_median_is_seeded_and_zero_for_one_value():
    """The same seed gives the same spread; one value has none and draws nothing."""
    values = [1.0, 2.0, 4.0, 8.0, 16.0]
    first = summaries.bootstrap_sd_median(values, n_boot=200, rng=np.random.default_rng(3))
    again = summaries.bootstrap_sd_median(values, n_boot=200, rng=np.random.default_rng(3))
    assert first == again > 0
    rng = np.random.default_rng(3)
    assert summaries.bootstrap_sd_median([2.5], n_boot=200, rng=rng) == 0.0
    assert rng.integers(0, 10) == np.random.default_rng(3).integers(0, 10)
    with pytest.raises(ValueError):
        summaries.bootstrap_sd_median([], n_boot=200, rng=rng)


def _test_rows() -> pd.DataFrame:
    """One participant on one test: distance 1 has a timeout, an error and two correct trials
    (one flagged); distance 2 has one correct trial; distance 3 only an error."""
    rows = [(1, False, True, 1000.0, False), (1, False, True, 3000.0, True),
            (1, False, True, 2000.0, False), (1, True, False, None, False),
            (1, False, False, 9000.0, False), (2, False, True, 4000.0, False),
            (3, False, False, 5000.0, False)]
    return pd.DataFrame([{"participant": "P001", "phase": "icl_test", "symbolic_distance": d,
                          "is_timed_out": t, "is_correct": c, "rt": rt, "rt_trimmed": flag}
                         for d, t, c, rt, flag in rows])


def test_participant_accuracy_by_distance_counts_a_timeout_as_incorrect():
    out = summaries.participant_accuracy_by_distance(_test_rows(), series_col="phase")
    d1 = out[out["symbolic_distance"] == 1].iloc[0]
    assert (d1["n_trials"], d1["n_correct"], d1["value"]) == (5, 3, 0.6)
    low, high = summaries.wilson_interval(3, 5)
    assert (d1["low"], d1["high"]) == (pytest.approx(low), pytest.approx(high))
    assert out["symbolic_distance"].tolist() == [1, 2, 3]


def test_participant_rt_by_distance_keeps_answered_correct_unflagged_trials():
    """Medians in seconds over answered, correct trials; ``exclude_col`` drops flagged ones; a
    single trial has no spread; a distance without such trials has no row."""
    rows = _test_rows()
    out = summaries.participant_rt_by_distance(rows, series_col="phase").set_index(
        "symbolic_distance")
    assert out.loc[1, "n_trials"] == 3 and out.loc[1, "value"] == pytest.approx(2.0)
    assert out.loc[2, "n_trials"] == 1 and out.loc[2, "sd"] == 0.0
    assert out.loc[2, "low"] == out.loc[2, "high"] == pytest.approx(4.0)
    assert 3 not in out.index
    trimmed = summaries.participant_rt_by_distance(rows, series_col="phase",
                                                   exclude_col="rt_trimmed")
    assert trimmed.loc[0, "n_trials"] == 2 and trimmed.loc[0, "value"] == pytest.approx(1.5)
    again = summaries.participant_rt_by_distance(rows, series_col="phase")
    pd.testing.assert_frame_equal(out.reset_index(), again[out.reset_index().columns])


def _slope_rows(*, rt_distances=range(1, 7)) -> pd.DataFrame:
    """One participant, two trials per distance on each test: correct at distances 1-3 only on
    the ICL test and at every distance on the IWL test; response times exactly
    ``exp(7 + 0.1 * distance)`` ms on the ICL test and ``exp(7 - 0.05 * distance)`` on the IWL
    test; only ``rt_distances`` keep a correct ICL test trial."""
    rows = []
    for test, step in (("icl_test", 0.1), ("iwl_test", -0.05)):
        for d in range(1, 7):
            for _ in range(2):
                correct = d <= 3 if test == "icl_test" else True
                if test == "icl_test" and d not in rt_distances:
                    correct = False
                rows.append({"participant": "P001", "phase": test, "symbolic_distance": d,
                             "is_timed_out": False, "is_correct": correct,
                             "rt": math.exp(7.0 + step * d)})
    return pd.DataFrame(rows)


def test_participant_slopes_experiment1_recovers_exact_slopes():
    """Noiseless slopes come back exactly, and their bootstrap spread is zero."""
    out = summaries.participant_slopes_experiment1(_slope_rows(), n_boot=50).set_index("phase")
    icl, iwl = out.loc["icl_test"], out.loc["iwl_test"]
    d = np.repeat(np.arange(1, 7), 2)
    expected = np.polyfit(d, (d <= 3).astype(float), 1)[0]
    assert icl["accuracy_slope"] == pytest.approx(expected)
    assert iwl["accuracy_slope"] == pytest.approx(0.0) and iwl["accuracy_slope_sd"] == 0.0
    assert iwl["rt_slope_pct"] == pytest.approx(100 * (math.exp(-0.05) - 1))
    assert iwl["rt_slope_pct_sd"] == pytest.approx(0.0, abs=1e-9)
    # The ICL response times come from the correct trials at distances 1-3 only.
    assert icl["n_rt_trials"] == 6
    assert icl["rt_slope_pct"] == pytest.approx(100 * (math.exp(0.1) - 1))
    # Trials agree within each distance, so resampling within distances leaves no spread.
    assert icl["accuracy_slope_sd"] == pytest.approx(0.0, abs=1e-12)


def test_participant_slopes_experiment1_spread_comes_from_trials_within_a_distance():
    """Mixed outcomes at one distance give the slope a spread; nowhere else does it vary."""
    rows = _slope_rows()
    mixed = rows.index[(rows["phase"] == "iwl_test") & (rows["symbolic_distance"] == 6)][0]
    rows.loc[mixed, "is_correct"] = False
    out = summaries.participant_slopes_experiment1(rows, n_boot=200).set_index("phase")
    assert out.loc["iwl_test", "accuracy_slope_sd"] > 0.01
    assert out.loc["icl_test", "accuracy_slope_sd"] == pytest.approx(0.0, abs=1e-12)


def test_participant_slopes_experiment1_refuses_a_single_distance():
    with pytest.raises(ValueError, match="fewer than two distances"):
        summaries.participant_slopes_experiment1(_slope_rows(rt_distances=(2,)), n_boot=10)


@pytest.mark.parametrize(("value", "printed", "expected"), [
    (1600, "1,600", "1,600"),
    (40, "40", "40"),
    (0.16142, "0.16%", "0.16%"),
    (72.5, "72.5%", "72.5%"),
    (0.755, ".76", ".76"),            # a tie, stored in binary just below .755
    (0.605, ".61", ".61"),
    (62.5, "63%", "63%"),             # ties round away from zero
    (-0.3874, "-0.387", "-0.387"),
    (-3.3242, "-3.3%", "-3.3%"),
    (9.6288, "+9.6%", "+9.6%"),
    (-0.0004, "0.000", "0.000"),
    (0.0503, ".050", ".050"),
    (0, "none", "none"),
    (1, "one", "one"),
    (3, "three", "three"),
    (2, "Two", "Two"),
    ((0.6269, 0.6496), ".63--.65", ".63--.65"),
    ((0.0779, 4.9777), "0--5%", "0--5%"),
    ((1.6944, 3.2988), "1.7 and 3.3", "1.7 and 3.3"),
    ((0.0471, 0.0694), ".047 to .069", ".047 to .069"),
    (3.6e-13, "< .001", "< .001"),
    (0.0035, "< .001", ".004"),
    (0.327, "> .32", "> .32"),
    (0.3, "> .32", ".30"),
    (0.32664, ">= .327", ">= .327"),  # .327 as printed
    (0.3264, ">= .327", ".326"),
    (0.0414, "<= .041", "<= .041"),
    (0.0416, "<= .041", ".042"),
    (14, "13", "14"),
])
def test_format_like_writes_a_value_as_the_paper_prints_it(value, printed, expected):
    """Decimals, separators, signs, percent, number words, ranges and bounds follow the print."""
    assert summaries._format_like(value, printed) == expected


def test_r_sources_name_one_row_of_models_csv(tmp_path):
    """``R:<model>:<set>:<term>:<column>`` reads one value; a term may contain ':'."""
    folder = tmp_path / "experiment1"
    folder.mkdir()
    pd.DataFrame({
        "experiment": [1, 1, 1], "model": ["accuracy_by_test"] * 3, "set": ["", "", ""],
        "term": ["(Intercept)", "symbolic_distance", "symbolic_distance:phase"],
        "estimate": [0.1, 0.2, 0.68512], "p_value": [0.5, 0.01, 1e-10],
    }).to_csv(folder / "models.csv", index=False)
    models: dict = {}
    source = "R:accuracy_by_test::symbolic_distance:phase:estimate"
    assert summaries._r_value(source, 1, tmp_path, models) == pytest.approx(0.68512)
    assert summaries._r_value("R:accuracy_by_test::(Intercept):p_value", 1, tmp_path,
                              models) == 0.5
    with pytest.raises(KeyError):
        summaries._r_value("R:accuracy_by_test:retained:(Intercept):estimate", 1, tmp_path,
                           models)
    with pytest.raises(FileNotFoundError):
        summaries._r_value("R:accuracy::(Intercept):estimate", 2, tmp_path, models)


def _slope_p_values(tmp_path, p_values) -> tuple[str, ...]:
    """Write three Experiment 2 p values to ``models.csv``, a missing one as an empty field as R
    writes it; return their sources."""
    folder = tmp_path / "experiment2"
    folder.mkdir()
    pd.DataFrame({
        "experiment": [2, 2, 2], "model": ["rt", "rt", "rt_waves"],
        "set": ["retained", "all_finishers", "retained"], "term": ["slope_congruent"] * 3,
        "p_value": p_values,
    }).to_csv(folder / "models.csv", index=False)
    return ("R:rt:retained:slope_congruent:p_value", "R:rt:all_finishers:slope_congruent:p_value",
            "R:rt_waves:retained:slope_congruent:p_value")


def test_aggregate_sources_take_the_max_min_or_range(tmp_path):
    """A tuple source names the largest, the smallest, or both, of several values."""
    parts = _slope_p_values(tmp_path, [0.050, 0.047, 0.069])
    models: dict = {}
    for how, expected in (("max", 0.069), ("min", 0.047), ("range", (0.047, 0.069))):
        value = summaries._value((how, *parts), 2, {}, tmp_path, models)
        assert value == pytest.approx(expected)
    assert summaries._source_text(("min", *parts[:2])) == f"min({parts[0]}, {parts[1]})"
    assert summaries._value("summaries.f:k", 2, {"summaries.f:k": 3}, tmp_path, models) == 3


def test_a_same_source_is_the_value_its_parts_share():
    """``same`` gives the one value of several sources, and NaN when they differ."""
    assert summaries._aggregate("same", [99.0, 99.0]) == 99.0
    assert math.isnan(summaries._aggregate("same", [99.0, 98.0]))
    assert math.isnan(summaries._aggregate("same", [99.0, float("nan"), 99.0]))


@pytest.mark.parametrize("position", [0, 1, 2])
def test_an_aggregate_of_a_missing_value_is_nan(tmp_path, position):
    """A value that could not be computed makes the max, min, same and range NaN, wherever it
    falls."""
    p_values = [0.050, 0.047, 0.069]
    p_values[position] = float("nan")
    parts = _slope_p_values(tmp_path, p_values)
    models: dict = {}
    for how in ("max", "min", "same"):
        value = summaries._value((how, *parts), 2, {}, tmp_path, models)
        assert math.isnan(value) and summaries._format_like(value, "< .001") == "nan"
    assert all(math.isnan(v) for v in summaries._value(("range", *parts), 2, {}, tmp_path, models))


def test_a_missing_value_is_nan_and_matches_no_printed_number():
    """A distance, bin, answer or pair the data lack gives NaN, written "nan"."""
    series = pd.Series([0.8, 0.6], index=[1, 2])
    assert summaries._at(series, 1) == 0.8 and math.isnan(summaries._at(series, 6))
    assert summaries._span(series, [1, 2]) == (0.6, 0.8)
    assert all(math.isnan(v) for v in summaries._span(series, [1, 2, 3]))
    assert summaries._format_like(float("nan"), ".83") == "nan"
    assert summaries._format_like((float("nan"), 0.65), ".63--.65") == "nan--.65"


def test_a_flat_slope_is_neither_positive_nor_negative():
    """A slope within ``_FLAT_SLOPE`` of zero, the remainder of a flat line's fit, counts as 0."""
    slopes = pd.Series([2.0e-18, -4.0e-18, 0.0, 0.01, -0.01])
    assert summaries._signs(slopes).tolist() == [0, 0, 0, 1, -1]


def test_people_are_counted_by_their_last_session():
    """A person with a kept session is kept; otherwise their last session's reason counts."""
    exclusions = pd.DataFrame({
        "participant": ["P001", "P001", "P002", "P002", "P003"],
        "session_index": [1, 2, 1, 2, 1],
        "reason": ["not_completed", None, "failed_comprehension", "not_completed", None],
    })
    people = summaries._people(exclusions)
    assert people["participant"].tolist() == ["P001", "P002", "P003"]
    assert [None if pd.isna(r) else r for r in people["reason"]] == [None, "not_completed", None]


def test_counts_experiment2_counts_the_retained_and_the_reloaded(synthetic_root):
    """The synthetic Experiment 2 keeps 11 participants, among them P012 (congruent), whose
    first session ended when the page was reloaded."""
    sessions, trials, _, sets = prepare.load_experiment2(synthetic_root)
    values = summaries.counts_experiment2(sessions, trials, sets=sets)
    assert values["retained"] == values["retained_congruent"] + values["retained_shuffled"] == 11
    assert (values["reloaded_congruent"], values["reloaded_shuffled"]) == (1, 0)


def test_paper_numbers_are_listed_once_with_known_sources():
    """Ids number each experiment's values in table order; every site names a section of the
    paper, and outside the main results its experiment; every source has a known form."""
    for experiment in (1, 2):
        ids = [row[0] for row in summaries.PAPER_NUMBERS if row[1] == experiment]
        assert ids == [f"{experiment}-{n}" for n in range(1, len(ids) + 1)]
    sections = ("Results, ", "Methods, ", "Extended methods, ", "Extended results, ")
    for id_, experiment, site, printed, source in summaries.PAPER_NUMBERS:
        assert site.startswith(sections), id_
        assert site.startswith("Results, ") or f"Experiment {experiment}" in site, id_
        assert printed, id_
        parts = source[1:] if isinstance(source, tuple) else (source,)
        if isinstance(source, tuple):
            assert source[0] in ("max", "min", "range", "same") and len(parts) > 1, id_
        assert all(p.startswith(("summaries.", "R:")) for p in parts), id_


def test_numbers_match_the_paper(data_root, repo_root):
    """Every number in ``results/numbers.csv`` is recomputed once and matches the printed value."""
    out = summaries.numbers(root=data_root, results_dir=repo_root / "results")
    committed = pd.read_csv(repo_root / "results" / "numbers.csv")
    assert len(out) > 0 and out["id"].is_unique
    assert set(out["id"]) == set(committed["id"]) and len(out) == len(committed)
    assert out["match"].all(), out.loc[~out["match"], ["id", "printed", "computed"]]
