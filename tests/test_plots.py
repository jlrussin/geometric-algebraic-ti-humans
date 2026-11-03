"""The panel functions, the figure style, and the figure scripts, on small synthetic frames."""

from __future__ import annotations

import argparse
import importlib
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from geo_alg_ti_humans import cli, tables  # noqa: E402
from geo_alg_ti_humans.plots import (  # noqa: E402
    arbitrage,
    distance,
    learning,
    pairs,
    participants,
    strategies,
    style,
)

PANELS = {
    "distance": ("make_accuracy_by_distance", "make_rt_by_distance"),
    "learning": ("make_accuracy_by_bin", "make_rt_by_bin", "make_accuracy_by_distractors",
                 "make_rt_by_distractors"),
    "pairs": ("make_pair_accuracy", "make_pair_rt"),
    "arbitrage": ("make_outcomes_by_distance", "make_rt_by_distance_split",
                  "make_participant_histogram"),
    "strategies": ("make_answer_bars", "make_participant_scatter", "make_category_violins"),
    "participants": ("make_participant_by_distance", "make_slope_scatter"),
}
ALL = [(module, name) for module, names in PANELS.items() for name in names]
PAIRS = [(a, b) for a in range(1, 8) for b in range(a + 1, 8)]
# The answer options of the two questionnaire items, as the strategies figure lists them.
OPTIONS = cli._figure_module("fig_strategies").OPTIONS
STATEMENTS = OPTIONS["statements_true"]
KNOWLEDGE = OPTIONS["knowledge_use"]


def _typed(df: pd.DataFrame, experiment: str, table: str) -> pd.DataFrame:
    """``df`` with the table's dtypes on the columns it shares with the table."""
    schema = tables.SCHEMAS[(experiment, table)]
    return df.astype({c: t for c, t in schema.items() if c in df.columns})


def _experiment1(n_participants: int = 3, seed: int = 0) -> pd.DataFrame:
    """Learning and test trials of ``n_participants`` people, in the trials table's columns.

    Learning: 100 trials each, adjacent pairs, every tenth trial (positions 3, 13, ...) with the
    context masked, the first masked trial of each 20-trial bin answered correctly, and the
    shown trials cycling through 0, 1 and 2 intervening distractors. Tests: the 21 pairs of
    seven items once each, answered incorrectly when the pair's rank sum plus the person's
    number is a multiple of five (so every pair has correct answers); on the arbitrage test a
    response follows the trained ordering when that sum is a multiple of three.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_participants):
        base = {"participant": f"P{p + 1:03d}", "session_index": 1, "assignment_id": 10 * p}
        index = 0
        for pos in range(100):
            masked = pos % 10 == 3
            a = int(rng.integers(1, 7))
            left, right = (a, a + 1) if rng.random() < 0.5 else (a + 1, a)
            timed_out = p == 0 and pos == 50
            correct = (pos % 20 == 3 or bool(rng.random() < 0.8)) and not timed_out
            rows.append({**base, "phase": "learning", "trial_index": index,
                         "symbolic_distance": 1, "query_left_rank": left,
                         "query_right_rank": right,
                         "context_display": "masked" if masked else "shown",
                         "intervening_distractors": None if masked else pos % 3,
                         "is_correct": correct, "is_timed_out": timed_out,
                         "rt": None if timed_out else float(rng.uniform(500, 5000)),
                         "is_icl_consistent": None, "is_iwl_consistent": None})
            index += 1
        for phase in ("icl_test", "iwl_test", "arbitrage_test"):
            for a, b in PAIRS:
                left, right = (a, b) if rng.random() < 0.5 else (b, a)
                trained = (a + b + p) % 3 == 0
                arb = phase == "arbitrage_test"
                rows.append({**base, "phase": phase, "trial_index": index,
                             "symbolic_distance": b - a, "query_left_rank": left,
                             "query_right_rank": right,
                             "context_display": "masked" if phase == "iwl_test" else "shown",
                             "intervening_distractors": None,
                             "is_correct": trained if arb else (a + b + p) % 5 != 0,
                             "is_timed_out": False, "rt": float(rng.uniform(800, 9000)),
                             "is_icl_consistent": (not trained) if arb else None,
                             "is_iwl_consistent": trained if arb else None})
                index += 1
    return _typed(pd.DataFrame(rows), "experiment1", "trials")


def _experiment2(seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Main questions and questionnaire answers of five people, the last not retained.

    48 questions each, 8 at each distance (shuffled: 4 agree and 4 conflict), each carrying its
    session's ``n_main_questions``; response time ``exp(7.5 + 0.05 * distance + noise)`` ms; one
    timed-out question and one flagged outlier.
    """
    rng = np.random.default_rng(seed)
    people = [("P001", "congruent", True), ("P002", "shuffled", True),
              ("P003", "congruent", True), ("P004", "shuffled", True),
              ("P005", "shuffled", False)]
    rows, answers = [], []
    for i, (participant, condition, kept) in enumerate(people):
        types = ["agree"] * 8 if condition == "congruent" else ["agree", "conflict"] * 4
        order = [(d, t) for d in range(1, 7) for t in types]
        rng.shuffle(order)
        for q, (d, question_type) in enumerate(order, start=1):
            timed_out = participant == "P002" and q == 5
            rt = None if timed_out else float(np.exp(7.5 + 0.05 * d + rng.normal(0.0, 0.2)))
            rows.append({"participant": participant, "session_index": 1, "assignment_id": i,
                         "condition": condition, "question_number": q, "block": (q - 1) // 12 + 1,
                         "symbolic_distance": d, "question_type": question_type,
                         "is_timed_out": timed_out,
                         "is_correct": (not timed_out) and bool(rng.random() < 0.85),
                         "rt": rt, "retained": kept})
        answers.append({"participant": participant, "session_index": 1, "condition": condition,
                        "statements_true": STATEMENTS[i % len(STATEMENTS)],
                        "knowledge_use": KNOWLEDGE[i % len(KNOWLEDGE)], "retained": kept})
    trials = _typed(pd.DataFrame(rows), "experiment2", "trials")
    trials["log_rt"] = np.log(trials["rt"].astype(float))
    trials["n_main_questions"] = trials.groupby("participant")["participant"].transform("size")
    trials["rt_trimmed"] = (trials["participant"] == "P001") & (trials["question_number"] == 7)
    return trials, _typed(pd.DataFrame(answers), "experiment2", "questionnaire")


@pytest.fixture
def ax():
    fig, axes = plt.subplots()
    yield axes
    plt.close(fig)


@pytest.fixture(scope="module")
def trials1() -> pd.DataFrame:
    return _experiment1()


@pytest.fixture(scope="module")
def frames2() -> tuple[pd.DataFrame, pd.DataFrame]:
    return _experiment2()


@pytest.mark.parametrize(("module", "name"), ALL)
def test_every_panel_function_exists(module, name):
    """Each panel module offers its ``make_<name>`` functions."""
    assert callable(getattr(importlib.import_module(f"geo_alg_ti_humans.plots.{module}"), name))


# Style

def test_apply_style_sets_the_figure_fonts():
    """``apply_style`` sets the font family, sizes and TrueType embedding of every figure."""
    plt.rcParams["legend.handlelength"] = 9.0
    style.apply_style()
    rc = matplotlib.rcParams
    assert rc["pdf.fonttype"] == 42 and rc["ps.fonttype"] == 42
    assert rc["font.sans-serif"][:3] == ["Helvetica", "Arial", "DejaVu Sans"]
    assert rc["font.size"] == 7.0 and rc["xtick.labelsize"] == 6.0
    assert rc["legend.fontsize"] == 6.0 and rc["legend.handlelength"] == 2.0
    assert rc["savefig.bbox"] in ("standard", None)  # matplotlib stores "standard" as None
    assert rc["figure.constrained_layout.use"]
    assert rc["savefig.dpi"] == style.PREVIEW_DPI == 200


def test_add_panel_label_draws_a_bold_letter(ax):
    """The letter sits at the axes' top-left corner, offset in points, bold at 9 pt."""
    style.add_panel_label(ax, "B")
    (letter,) = ax.texts
    assert letter.get_text() == "B" and letter.get_fontweight() == "bold"
    assert letter.get_fontsize() == style.PANEL_LABEL_SIZE == 9.0
    assert letter.xy == (0.0, 1.0)


def test_context_colors_and_labels_cover_the_experiment2_series():
    """Each Experiment 2 series has a color and a label; the two tests keep red and blue."""
    assert set(style.CONTEXT_COLORS) == set(style.CONTEXT_LABELS) == {
        "congruent", "shuffled", "shuffled_agree", "shuffled_conflict"}
    assert style.TEST_COLORS == {"iwl": "#d62728", "icl": "#1f77b4"}
    assert style.LEARNING_DISPLAY_ORDER == ("shown", "masked")


# Accuracy and response time by distance

def test_accuracy_by_distance_averages_within_participant_first(ax):
    """Each participant counts once per distance, and timeouts count as incorrect."""
    df = pd.DataFrame({
        "participant": ["P001", "P001", "P002", "P001", "P002"],
        "phase": ["icl_test"] * 5,
        "symbolic_distance": [1, 1, 1, 2, 2],
        "is_correct": [True, False, True, True, False],
        "is_timed_out": [False, False, False, False, True],
    })
    stats = distance.make_accuracy_by_distance(ax, df, phases=("icl_test",))
    series = stats["per_phase"]["icl_test"]
    assert series["mean_by_distance"] == {1: 0.75, 2: 0.5}
    assert series["sem_by_distance"][1] == 0.25
    assert series["n_participants_by_distance"] == {1: 2, 2: 2}
    assert stats["n_trials_used"] == 5


def test_rt_by_distance_takes_medians_of_correct_answered_trials(ax):
    """Incorrect, timed-out and flagged rows are dropped before each participant's median; the
    count of flagged rows dropped leaves out the incorrect one, which is dropped anyway."""
    df = pd.DataFrame({
        "participant": ["P001"] * 4 + ["P002"] * 2,
        "condition": ["shuffled"] * 6,
        "symbolic_distance": [1] * 6,
        "is_correct": [True, True, True, False, True, False],
        "is_timed_out": [False, False, False, False, False, True],
        "rt": [1000.0, 3000.0, 9000.0, 500.0, 2000.0, None],
        "rt_trimmed": [False, False, True, True, False, False],
    })
    stats = distance.make_rt_by_distance(
        ax, df, phases=("shuffled",), group_col="condition", rt_scale=0.001,
        exclude_col="rt_trimmed", colors=style.CONTEXT_COLORS, labels=style.CONTEXT_LABELS)
    assert stats["per_phase"]["shuffled"]["mean_by_distance"] == {1: 2.0}
    assert stats["n_rows_dropped_by_rt_trimmed"] == 1


def test_a_single_participant_has_no_standard_error(ax, trials1):
    """With one participant, the statistics write each standard error as None, not NaN."""
    one = trials1[trials1["participant"] == "P001"]
    acc = distance.make_accuracy_by_distance(ax, one)
    assert set(acc["per_phase"]["icl_test"]["sem_by_distance"].values()) == {None}
    pair = pairs.make_pair_accuracy(ax, one)
    assert set(pair["per_phase"]["icl_test"]["sem_by_pair"].values()) == {None}
    arb = arbitrage.make_outcomes_by_distance(ax, one)
    assert set(arb["per_outcome"]["is_icl_consistent"]["sem_by_x"].values()) == {None}


def test_points_are_jittered_by_series_then_distance_then_participant(ax):
    """One generator per call, drawn in series order, then sorted x, then sorted participants."""
    df = pd.DataFrame({
        "participant": ["P002", "P001", "P002", "P001", "P003", "P001"],
        "phase": ["iwl_test", "iwl_test", "iwl_test", "iwl_test", "icl_test", "icl_test"],
        "symbolic_distance": [2, 2, 1, 1, 1, 1],
        "is_correct": [True, False, True, True, False, True],
    })
    width = 0.08
    distance.make_accuracy_by_distance(ax, df, show_band=False, jitter_width=width,
                                       jitter_seed=3)
    rng = np.random.default_rng(3)
    expected = []
    for points_by_x in ([(1, [1.0, 0.0])], [(1, [1.0, 1.0]), (2, [0.0, 1.0])]):
        for x, values in points_by_x:
            jitter = rng.uniform(-width, width, size=len(values))
            expected.append(np.column_stack([x + jitter, values]))
    drawn = [c.get_offsets() for c in ax.collections]
    assert len(drawn) == len(expected)
    for got, want in zip(drawn, expected, strict=True):
        np.testing.assert_array_equal(np.asarray(got), want)


# Learning phase

def test_learning_bins_keep_masked_trials_at_their_positions(ax, trials1):
    """Bins count all 100 learning trials; each display covers all five bins."""
    stats = learning.make_accuracy_by_bin(ax, trials1)
    assert stats["bin_centers"] == [10, 30, 50, 70, 90]
    assert stats["n_rows_used"] == 300
    masked = stats["per_mode"]["masked"]
    assert masked["n_trials_by_x"] == {10: 6, 30: 6, 50: 6, 70: 6, 90: 6}
    assert masked["label"] == "Context masked"
    assert set(stats["per_mode"]) == {"shown", "masked"}


def test_learning_bins_of_an_odd_width_keep_their_centers(ax, trials1):
    """With 25-trial bins the statistics are keyed by the centers 12.5, 37.5, ..., not 12, 37."""
    stats = learning.make_accuracy_by_bin(ax, trials1, bin_width=25)
    assert stats["bin_centers"] == [12.5, 37.5, 62.5, 87.5]
    assert stats["per_mode"]["masked"]["n_trials_by_x"] == {12.5: 9, 37.5: 6, 62.5: 9, 87.5: 6}


def test_learning_rt_by_bin_uses_correct_answered_trials(ax, trials1):
    """Response times are in seconds and drop incorrect and timed-out trials."""
    stats = learning.make_rt_by_bin(ax, trials1)
    learn = trials1[trials1["phase"] == "learning"]
    usable = learn[learn["is_correct"].astype(bool) & ~learn["is_timed_out"].astype(bool)]
    assert stats["n_rows_used"] == len(usable)
    assert all(0.5 <= v <= 5.0 for v in stats["per_mode"]["shown"]["mean_by_x"].values())


def test_learning_by_distractors_reads_context_shown_trials(ax, trials1):
    """Masked trials are left out; the halves split at trial 50."""
    stats = learning.make_accuracy_by_distractors(ax, trials1)
    assert stats["n_masked_rows_excluded"] == 30
    assert set(stats["per_half"]) == {"first", "second"}
    assert set(stats["per_half"]["first"]["mean_by_x"]) == {0, 1, 2}
    rt = learning.make_rt_by_distractors(ax, trials1)
    assert rt["per_half"]["second"]["label"] == "Trials 51–100"


def test_learning_halves_are_named_by_their_trials(ax, trials1):
    """The legend names each half by the trials ``split_at`` and ``n_trials`` give it."""
    stats = learning.make_accuracy_by_distractors(ax, trials1, split_at=40)
    labels = [stats["per_half"][half]["label"] for half in ("first", "second")]
    assert labels == ["Trials 1–40", "Trials 41–100"]
    assert [t.get_text() for t in ax.get_legend().get_texts()] == labels


def test_learning_halves_may_take_other_names(ax, trials1):
    """Custom ``split_values`` take the style's labels, line styles and markers in order."""
    stats = learning.make_rt_by_distractors(ax, trials1, split_values=("early", "late"))
    assert [stats["per_half"][h]["label"] for h in ("early", "late")] == [
        "Trials 1–50", "Trials 51–100"]
    assert [line.get_linestyle() for line in ax.lines] == ["-", "--"]
    assert [line.get_marker() for line in ax.lines] == ["o", "s"]


def test_learning_refuses_a_non_adjacent_query(ax, trials1):
    """A learning query between non-adjacent items raises."""
    bad = trials1.copy()
    bad.loc[0, "symbolic_distance"] = 2
    with pytest.raises(ValueError, match="adjacent"):
        learning.make_accuracy_by_bin(ax, bad)


def test_learning_refuses_a_repeated_trial_index(ax, trials1):
    """Two learning rows of one participant with the same ``trial_index`` raise."""
    bad = trials1.copy()
    bad.loc[1, "trial_index"] = bad.loc[0, "trial_index"]
    with pytest.raises(ValueError, match="strictly increasing"):
        learning.make_accuracy_by_bin(ax, bad)


def test_learning_refuses_out_of_range_distractors(ax, trials1):
    """Intervening distractors outside 0-2 on a context-shown trial raise."""
    bad = trials1.copy()
    shown = bad.index[(bad["phase"] == "learning") & (bad["context_display"] == "shown")][0]
    bad.loc[shown, "intervening_distractors"] = 3
    with pytest.raises(ValueError, match="outside"):
        learning.make_accuracy_by_distractors(ax, bad)


# Item pairs

def test_pair_panels_lay_out_the_21_pairs_by_distance(ax, trials1):
    """Pairs are lettered from the observed ranks and blocked by distance, AB first."""
    stats = pairs.make_pair_accuracy(ax, trials1)
    assert stats["n_pairs"] == 21 and stats["d_values"] == [1, 2, 3, 4, 5, 6]
    assert stats["pairs_in_x_order"][:7] == ["AB", "BC", "CD", "DE", "EF", "FG", "AC"]
    assert stats["rank_letters_by_phase"]["icl_test"][1] == "A"
    rt = pairs.make_pair_rt(ax, trials1)
    assert rt["rt_scale"] == 0.001 and set(rt["per_phase"]) == {"iwl_test", "icl_test"}


def test_pair_panels_refuse_tests_with_different_pairs(ax, trials1):
    """The tests must query the same pairs."""
    bad = trials1[~((trials1["phase"] == "iwl_test") & (trials1["symbolic_distance"] == 6))]
    with pytest.raises(ValueError):
        pairs.make_pair_accuracy(ax, bad)


def test_pair_rt_keeps_the_layout_when_a_pair_has_no_correct_answer(ax, trials1):
    """A pair without a correct answered trial on one test leaves a gap; the layout stays."""
    trials = trials1.copy()
    ab = (trials["phase"] == "icl_test") & (
        trials[["query_left_rank", "query_right_rank"]].max(axis=1) == 2)
    trials.loc[ab, "is_correct"] = False
    stats = pairs.make_pair_rt(ax, trials)
    assert stats["n_pairs"] == 21 and stats["pairs_in_x_order"][0] == "AB"
    assert "AB" not in stats["per_phase"]["icl_test"]["mean_by_pair"]
    assert "AB" in stats["per_phase"]["iwl_test"]["mean_by_pair"]
    icl_lines = [line for line in ax.lines if line.get_color() == style.TEST_COLORS["icl"]]
    assert np.isnan(icl_lines[0].get_ydata()[0])


# Arbitrage test

def test_arbitrage_outcomes_are_complements(ax, trials1):
    """The two response classes sum to one at every distance."""
    stats = arbitrage.make_outcomes_by_distance(ax, trials1)
    assert stats["max_abs_dev_from_sum_one"] == 0.0
    assert stats["n_participants"] == 3 and stats["n_rows_used"] == 63


def test_arbitrage_rt_split_and_histogram(ax, trials1):
    """Response times split by the ordering followed; the histogram counts every participant."""
    rt = arbitrage.make_rt_by_distance_split(ax, trials1, ylim=None, yticks=None)
    assert set(rt["per_outcome"]) == {"False", "True"} and rt["n_participants"] == 3
    hist = arbitrage.make_participant_histogram(ax, trials1)
    assert sum(hist["count_by_bin"].values()) == hist["n_participants"] == 3
    assert set(hist["participants_sorted"]) == {"P001", "P002", "P003"}
    assert set(hist["n_trials_by_participant"].values()) == {21}


def test_arbitrage_refuses_a_missing_response_class(ax, trials1):
    """A null response-class flag on an arbitrage row raises instead of reading as false."""
    bad = trials1.copy()
    row = bad.index[bad["phase"] == "arbitrage_test"][0]
    bad.loc[row, "is_icl_consistent"] = pd.NA
    with pytest.raises(ValueError, match="null"):
        arbitrage.make_outcomes_by_distance(ax, bad)


def test_arbitrage_drops_timed_out_trials(ax, trials1):
    """A timeout, saved with both response-class flags false, follows neither ordering."""
    trials = trials1.copy()
    rows = trials.index[trials["phase"] == "arbitrage_test"]
    timeout = {"is_timed_out": True, "is_correct": False, "rt": np.nan,
               "is_icl_consistent": False, "is_iwl_consistent": False}
    for column, value in timeout.items():
        trials.loc[rows[0], column] = value
    stats = arbitrage.make_outcomes_by_distance(ax, trials)
    assert stats["n_rows_used"] == 62 and stats["max_abs_dev_from_sum_one"] == 0.0
    hist = arbitrage.make_participant_histogram(ax, trials)
    assert hist["n_trials_by_participant"]["P001"] == 20
    rt = arbitrage.make_rt_by_distance_split(ax, trials, ylim=None, yticks=None)
    assert rt["n_rows_used"] == 62 and rt["drop_timeouts"]
    trials.loc[rows[1], ["is_icl_consistent", "is_iwl_consistent", "is_correct"]] = False
    with pytest.raises(ValueError, match="neither"):
        arbitrage.make_outcomes_by_distance(ax, trials)


# Strategies

def test_answer_helpers():
    """Counts per condition, the median answer, the gray ramp and the checked join."""
    responses = pd.DataFrame({"participant": ["P001", "P002", "P003"],
                              "condition": ["congruent", "congruent", "shuffled"],
                              "knowledge_use": ["Never", "Often", None]})
    counts = strategies.answer_counts(responses, item="knowledge_use", options=KNOWLEDGE)
    assert counts["congruent"]["counts"]["Often"] == 1 and counts["shuffled"]["n_skipped"] == 1
    assert strategies.median_answer(counts["congruent"]["counts"], KNOWLEDGE) == "Never to Often"
    assert strategies.gray_ramp(3, light=1.0, dark=0.0) == ["#ffffff", "#808080", "#000000"]
    measures = pd.DataFrame({"participant": ["P003", "P001", "P002"],
                             "condition": ["shuffled", "congruent", "congruent"]})
    joined = strategies.attach_answers(measures, responses, item="knowledge_use")
    assert joined["knowledge_use"].tolist()[1:] == ["Never", "Often"]
    with pytest.raises(ValueError):
        strategies.attach_answers(measures.head(2), responses, item="knowledge_use")


def test_answer_bars_and_participant_panels(frames2):
    """Bar shares sum to 100; scatter and violins draw one point per participant."""
    from geo_alg_ti_humans import summaries

    trials, answers = frames2
    fig, (bars_ax, scatter_ax, violins_ax) = plt.subplots(1, 3)
    try:
        bars = strategies.make_answer_bars(bars_ax, answers, item="statements_true",
                                           options=STATEMENTS, off_scale=("I don't know",))
        for condition in ("congruent", "shuffled"):
            shares = bars["by_condition"][condition]["percent"].values()
            assert math.isclose(sum(shares), 100.0, abs_tol=0.05)  # shares rounded to 0.01
        measures = summaries.participant_rt_measures(trials)
        scatter = strategies.make_participant_scatter(scatter_ax, measures)
        assert scatter["by_group"]["shuffled"]["n"] == 3
        rated = strategies.attach_answers(measures, answers, item="knowledge_use")
        violins = strategies.make_category_violins(violins_ax, rated, cat_col="knowledge_use",
                                                   categories=KNOWLEDGE)
        assert violins["by_group"]["congruent"]["n"] == 2
    finally:
        plt.close(fig)


@pytest.mark.parametrize(("module", "name"), ALL)
def test_every_panel_draws_on_the_synthetic_tables(ax, module, name, trials1, frames2):
    """Each panel draws on the synthetic frames and returns the statistics it drew."""
    from geo_alg_ti_humans import summaries

    trials2, answers = frames2
    fn = getattr(importlib.import_module(f"geo_alg_ti_humans.plots.{module}"), name)
    if module == "strategies":
        measures = summaries.participant_rt_measures(trials2)
        frame, kwargs = {
            "make_answer_bars": (answers, {"item": "knowledge_use", "options": KNOWLEDGE,
                                           "off_scale": ()}),
            "make_participant_scatter": (measures, {}),
            "make_category_violins": (
                strategies.attach_answers(measures, answers, item="knowledge_use"),
                {"cat_col": "knowledge_use", "categories": KNOWLEDGE}),
        }[name]
    elif module == "distance":
        frame, kwargs = trials1, {}
    elif module == "participants":
        tests = trials1[trials1["phase"].isin(["icl_test", "iwl_test"])]
        if name == "make_participant_by_distance":
            rows = summaries.participant_accuracy_by_distance(tests, series_col="phase")
            frame = rows[rows["participant"] == "P001"]
            kwargs = {"series": ("icl_test", "iwl_test"), "series_col": "phase",
                      "colors": {"icl_test": "C0", "iwl_test": "C1"}}
        else:
            frame = pd.DataFrame({"participant": ["P001", "P002"], "x": [0.1, -0.2],
                                  "y": [-0.1, 0.3]})
            kwargs = {"x_col": "x", "y_col": "y", "xlim": (-1, 1), "ylim": (-1, 1)}
    else:
        frame, kwargs = trials1, ({"ylim": None, "yticks": None}
                                  if name == "make_rt_by_distance_split" else {})
    stats = fn(ax, frame, **kwargs)
    assert isinstance(stats, dict) and stats


@pytest.mark.parametrize(("module", "name", "ylim"), [
    ("learning", "make_accuracy_by_bin", (0.99, 1.0)),
    ("learning", "make_rt_by_distractors", (0.0, 0.1)),
    ("distance", "make_accuracy_by_distance", (0.99, 1.0)),
    ("pairs", "make_pair_rt", (0.0, 0.1)),
    ("arbitrage", "make_outcomes_by_distance", (0.99, 1.0)),
    ("arbitrage", "make_participant_histogram", (0.0, 0.5)),
])
def test_fixed_y_limits_refuse_a_value_outside_the_frame(ax, trials1, module, name, ylim):
    """A mean or bar drawn outside a fixed y range raises, naming the panel function, instead
    of being cut at the frame."""
    fn = getattr(importlib.import_module(f"geo_alg_ti_humans.plots.{module}"), name)
    with pytest.raises(ValueError, match=f"^{name}: .* outside the drawn y range"):
        fn(ax, trials1, ylim=ylim)


# Figure scripts

@pytest.mark.parametrize("topic", ["learning", "pairs", "arbitrage"])
def test_experiment1_figures_draw(topic, trials1):
    """Each Experiment 1 figure draws every panel and letters them."""
    module = cli._figure_module(f"fig_{topic}")
    fig, stats = module.draw(trials1)
    try:
        texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        letters = sorted(t for t in texts if len(t) == 1)
        assert letters == sorted(module.LETTERS.values())
        assert set(stats) == set(module.LETTERS)
        assert tuple(fig.get_size_inches()) == (style.DOUBLE_COL_W, module.HEIGHT_IN)
    finally:
        plt.close(fig)


def test_robustness_figure_counts_both_sets(frames2):
    """All finishers are drawn; the retained participants are counted beside them."""
    trials, _ = frames2
    fig, stats = cli._figure_module("fig_robustness").draw(trials)
    plt.close(fig)
    assert stats["participants_by_condition"] == {"congruent": 2, "shuffled": 3}
    assert stats["participants_by_condition_retained"] == {"congruent": 2, "shuffled": 2}
    assert stats["n_trials_in_set"] == 5 * 48


def test_agree_conflict_figure_splits_the_shuffled_questions(frames2):
    """The retained shuffled questions split into agree and conflict series."""
    trials, _ = frames2
    fig, stats = cli._figure_module("fig_agree_conflict").draw(trials)
    plt.close(fig)
    assert stats["n_questions"] == 4 * 48
    assert set(stats["acc"]["per_phase"]) == {"congruent", "shuffled_agree", "shuffled_conflict"}
    assert stats["n_timeouts_by_series"]["shuffled_agree"] + \
        stats["n_timeouts_by_series"]["shuffled_conflict"] == 1


def test_strategies_figure_draws_the_retained_participants(frames2):
    """Bars, scatter and violins from the retained participants' questions and answers."""
    trials, answers = frames2
    fig, stats = cli._figure_module("fig_strategies").draw(trials, answers)
    plt.close(fig)
    assert stats["participant_set"]["trials"] == {"congruent": 2, "shuffled": 2}
    assert stats["participant_set"]["all_finishers"]["trials"] == {"congruent": 2, "shuffled": 3}
    assert len(stats["measures"]["per_participant"]) == 4


def test_experiment2_figures_check_the_saved_question_count(frames2):
    """The questions per session come from the sessions table's saved count: every drawn
    session must agree on it, and the questions must fill it."""
    shared = cli._figure_module("_shared")
    trials, answers = frames2
    assert shared.questions_per_session(trials) == int((trials["participant"] == "P001").sum())
    one_short = trials.assign(n_main_questions=trials["n_main_questions"].mask(
        trials["participant"] == "P002", 47))
    for draw in (lambda t: cli._figure_module("fig_agree_conflict").draw(t),
                 lambda t: cli._figure_module("fig_strategies").draw(t, answers)):
        with pytest.raises(ValueError, match=r"different numbers of main questions: \[47, 48\]"):
            draw(one_short)
    other = trials.assign(n_main_questions=36)
    with pytest.raises(ValueError, match="6 questions at each distance"):
        cli._figure_module("fig_agree_conflict").draw(other)
    with pytest.raises(ValueError, match="expected 36 main questions"):
        cli._figure_module("fig_strategies").draw(other, answers)
    with pytest.raises(KeyError, match="no n_main_questions column"):
        shared.questions_per_session(trials.drop(columns="n_main_questions"))
    with pytest.raises(ValueError, match="no questions"):
        shared.questions_per_session(trials.iloc[:0])
    unmatched = trials.assign(n_main_questions=trials["n_main_questions"].mask(
        trials["participant"] == "P003"))
    with pytest.raises(ValueError, match="no n_main_questions for 1 of the questions' sessions"):
        shared.questions_per_session(unmatched)


def test_agree_conflict_figure_refuses_an_odd_count_per_distance(frames2):
    """Seven questions per distance (42 per session) cannot split into agree and conflict
    halves."""
    trials, _ = frames2
    with pytest.raises(ValueError, match="7 questions at each distance, an odd count"):
        cli._figure_module("fig_agree_conflict").draw(trials.assign(n_main_questions=42))


def test_agree_conflict_figure_refuses_a_missing_distance(frames2):
    """Questions that skip a symbolic distance fail the design check, even when the remaining
    distances split evenly."""
    trials, _ = frames2
    six = trials["symbolic_distance"] == 6
    shifted = trials.assign(symbolic_distance=trials["symbolic_distance"].mask(six, 5))
    with pytest.raises(ValueError, match=r"distances are \[1, 2, 3, 4, 5\]"):
        cli._figure_module("fig_agree_conflict").draw(shifted)


def test_figure_command_saves_a_pdf_and_a_preview(monkeypatch, tmp_path, trials1):
    """``figure --name`` builds the script's figure and writes it to the output directory."""
    script = cli._figure_module("fig_arbitrage")
    monkeypatch.setattr(script, "experiment1_trials", lambda data_root=None: trials1)
    monkeypatch.setattr(cli._figure_module("_shared"), "OUT_DIR", tmp_path)
    assert cli.main(["figure", "--name", "arbitrage"]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["arbitrage.pdf", "arbitrage.png"]


def test_mosaic_figure_applies_its_rc_inside_the_with_statement_only():
    """A figure's ``rc`` reaches the legends drawn in the ``with`` body and no later figure."""
    shared = cli._figure_module("_shared")
    with shared.mosaic_figure((("a",),), width_in=3.0, height_in=2.0,
                              rc={"legend.handlelength": 3.0}) as (fig, axes):
        axes["a"].plot([0, 1], [0, 1], label="line")
        legend = axes["a"].legend()
    plt.close(fig)
    assert legend.handlelength == 3.0
    assert plt.rcParams["legend.handlelength"] == 2.0  # the style's


def test_save_writes_the_figure_under_its_rc(tmp_path):
    """A parameter read when the file is written, such as the saved background, takes the rc
    the figure was drawn with, which the figure keeps after the ``with`` statement."""
    shared = cli._figure_module("_shared")
    pixels = []
    for name, rc in (("plain", None), ("red", {"savefig.facecolor": "#ff0000"})):
        with shared.mosaic_figure((("a",),), width_in=1.0, height_in=1.0, rc=rc) as (fig, _):
            pass
        assert shared.figure_rc(fig) == (rc or {})
        paths = shared.save(fig, name, out_dir=tmp_path, formats=("pdf",))
        pixels.append(tuple(plt.imread(paths[1])[0, 0, :3]))
    assert pixels == [(1.0, 1.0, 1.0), (1.0, 0.0, 0.0)]
    assert plt.rcParams["savefig.facecolor"] == "auto"


def test_mosaic_figure_closes_the_figure_when_its_body_raises():
    """A panel that raises inside the ``with`` statement leaves no figure open."""
    shared = cli._figure_module("_shared")
    open_before = plt.get_fignums()
    with pytest.raises(ValueError, match="panel"):
        with shared.mosaic_figure((("a",),), width_in=3.0, height_in=2.0):
            raise ValueError("panel")
    assert plt.get_fignums() == open_before


def test_shared_save_keeps_the_declared_size(tmp_path):
    """Saved figures keep their physical size and write TrueType text."""
    shared = cli._figure_module("_shared")
    with shared.mosaic_figure((("a", "b"),), width_in=7.0, height_in=2.0) as (fig, axes):
        shared.letter_panels(axes, {"a": "A", "b": "B"})
    paths = shared.save(fig, "check", out_dir=tmp_path, formats=("pdf",))
    assert [p.suffix for p in paths] == [".pdf", ".png"]
    png = plt.imread(paths[1])
    assert png.shape[:2] == (2 * style.PREVIEW_DPI, 7 * style.PREVIEW_DPI)


def _exclusions(keys, reasons):
    return pd.DataFrame({"participant": [p for p, _ in keys], "session_index": [s for _, s in keys],
                         "reason": reasons})


def test_experiment1_trials_keeps_the_kept_sessions(monkeypatch, trials1):
    """Only kept sessions' learning and test rows, in trial order within each participant."""
    shared = cli._figure_module("_shared")
    repeat = trials1[trials1["participant"] == "P001"].assign(session_index=2)
    practice = trials1.head(3).assign(phase="practice_query_only")
    table = pd.concat([repeat, trials1, practice]).sample(frac=1.0, random_state=0)
    exclusions = _exclusions([("P001", 1), ("P001", 2), ("P002", 1), ("P003", 1)],
                             [None, "repeat", None, None])
    monkeypatch.setattr(shared.tables, "load", lambda table_name, experiment, root=None: table)
    monkeypatch.setattr(shared.prepare, "exclusions_experiment1", lambda s, t: exclusions)
    rows = shared.experiment1_trials()
    pd.testing.assert_frame_equal(rows, trials1.reset_index(drop=True))


def test_experiment2_frames_flag_the_retained_participants(monkeypatch, frames2):
    """All finishers' questions and answers, with ``retained`` from the retained set."""
    shared = cli._figure_module("_shared")
    trials, answers = frames2
    unfinished = trials[trials["participant"] == "P005"].assign(participant="P006")
    table = pd.concat([trials, unfinished]).drop(
        columns=["log_rt", "rt_trimmed", "retained", "n_main_questions"])
    sessions = pd.DataFrame({"participant": [f"P00{i}" for i in range(1, 7)],
                             "session_index": 1, "n_main_questions": [48] * 5 + [20]})
    tables_by_name = {"sessions": sessions, "trials": table.iloc[::-1],
                      "questionnaire": answers.drop(columns="retained")}
    keys = [(f"P00{i}", 1) for i in range(1, 7)]
    sets = {"retained": _exclusions(keys, [None] * 4 + ["random_responder", "not_completed"]),
            "all_finishers": _exclusions(keys, [None] * 5 + ["not_completed"])}

    def flag(df):
        return df.assign(log_rt=np.log(df["rt"].astype(float)), rt_trimmed=False)

    monkeypatch.setattr(shared.tables, "load",
                        lambda table_name, experiment, root=None: tables_by_name[table_name])
    monkeypatch.setattr(shared.prepare, "participant_sets_experiment2", lambda s, t: sets)
    monkeypatch.setattr(shared.prepare, "rt_trimmed_experiment2", flag)
    rows, kept_answers = shared.experiment2_frames()
    assert sorted(rows["participant"].unique()) == ["P001", "P002", "P003", "P004", "P005"]
    assert rows.groupby("participant")["question_number"].apply(
        lambda q: q.is_monotonic_increasing).all()
    assert rows.groupby("participant")["retained"].first().tolist() == [True] * 4 + [False]
    assert (rows["n_main_questions"] == 48).all()
    assert kept_answers["retained"].tolist() == [True] * 4 + [False]
    tables_by_name["sessions"] = sessions[sessions["participant"] != "P002"]
    with pytest.raises(ValueError, match="no n_main_questions for 1 of the questions' sessions"):
        shared.experiment2_frames()


def test_figure_build_reads_the_tables(monkeypatch, trials1):
    """``build`` loads the frames through the shared loaders and returns the figure."""
    module = cli._figure_module("fig_learning")
    assert module.experiment1_trials is cli._figure_module("_shared").experiment1_trials
    monkeypatch.setattr(module, "experiment1_trials", lambda data_root=None: trials1)
    fig = module.build(argparse.Namespace(data=None, out=None))
    try:
        assert len(fig.axes) == 4
    finally:
        plt.close(fig)


# Participant figures

def _participant_rows():
    """One participant's long frame on two series: a value at every distance on one, a gap at
    distance 3 and a single-trial point at distance 6 on the other."""
    rows = []
    for d in range(1, 7):
        rows.append({"phase": "a", "symbolic_distance": d, "value": 0.5, "low": 0.4,
                     "high": 0.6, "n_trials": 4})
        if d != 3:
            rows.append({"phase": "b", "symbolic_distance": d, "value": 0.9,
                         "low": 0.8 if d < 6 else 0.9, "high": 1.1 if d == 1 else 0.95,
                         "n_trials": 1 if d == 6 else 4})
    return pd.DataFrame(rows)


def test_participant_by_distance_counts_gaps_single_trials_and_cut_bands(ax):
    stats = participants.make_participant_by_distance(
        ax, _participant_rows(), series=("a", "b"), series_col="phase",
        colors={"a": "C0", "b": "C1"}, offsets={"b": 0.1}, ylim=(0, 1), yticks=(0, 1))
    a, b = stats["per_series"]["a"], stats["per_series"]["b"]
    assert a["missing_distances"] == [] and b["missing_distances"] == [3]
    assert b["n_single_trial_points"] == 1 and b["n_bands_cut_at_frame"] == 1
    assert sorted(b["value_by_distance"]) == [1, 2, 4, 5, 6]
    xs = ax.lines[1].get_xdata()
    assert xs[0] == pytest.approx(1.1)


def test_participant_by_distance_refuses_a_value_outside_the_range(ax):
    with pytest.raises(ValueError, match="outside the drawn y range"):
        participants.make_participant_by_distance(
            ax, _participant_rows(), series=("b",), series_col="phase", colors={"b": "C1"},
            ylim=(0, 0.8))


def test_participant_by_distance_refuses_a_distance_it_does_not_draw(ax):
    with pytest.raises(ValueError, match=r"distances \[6\] outside"):
        participants.make_participant_by_distance(
            ax, _participant_rows(), series=("a",), series_col="phase", colors={"a": "C0"},
            distances=(1, 2, 3, 4, 5))


def test_slope_scatter_counts_the_tinted_region_and_refuses_outside_points(ax):
    slopes = pd.DataFrame({"participant": ["P001", "P002", "P003"], "x": [0.1, -0.1, 0.2],
                           "y": [-0.1, -0.2, 0.3], "x_sd": [0.05, 0.05, 0.9],
                           "y_sd": [0.0, 0.0, 0.0]})
    stats = participants.make_slope_scatter(
        ax, slopes, x_col="x", y_col="y", x_err_col="x_sd", y_err_col="y_sd",
        shade="lower_right", xlim=(-1, 1), ylim=(-1, 1))
    assert stats["n"] == 3 and stats["n_in_shaded_region"] == 1
    assert stats["n_on_shaded_region_edge"] == 0
    assert stats["n_whiskers_cut_at_frame"] == 1
    upper = participants.make_slope_scatter(ax, slopes, x_col="x", y_col="y",
                                            shade="upper_half", xlim=(-1, 1), ylim=(-1, 1))
    assert upper["n_in_shaded_region"] == 1
    with pytest.raises(ValueError, match="outside the drawn x range"):
        participants.make_slope_scatter(ax, slopes, x_col="x", y_col="y", xlim=(-0.15, 0.15),
                                        ylim=(-1, 1))


def test_slope_scatter_counts_a_zero_slope_on_the_edge_not_inside(ax):
    """A slope that is zero but for rounding, or a corner, sits on the region's edge; a point on
    a zero line beyond the region is neither inside nor on its edge."""
    slopes = pd.DataFrame({"participant": ["P001", "P002", "P003", "P004", "P005"],
                           "x": [2e-18, 0.1, -1e-17, 0.0, 0.0],
                           "y": [-0.1, -0.1, -0.1, 0.0, 0.5]})
    for tol in (1e-9, 0.0):
        stats = participants.make_slope_scatter(ax, slopes, x_col="x", y_col="y",
                                                shade="lower_right", xlim=(-1, 1), ylim=(-1, 1),
                                                edge_tol=tol)
        inside, edge = stats["n_in_shaded_region"], stats["n_on_shaded_region_edge"]
        assert (inside, edge) == ((1, 3) if tol else (2, 1))
    with pytest.raises(ValueError, match="edge_tol"):
        participants.make_slope_scatter(ax, slopes, x_col="x", y_col="y", xlim=(-1, 1),
                                        ylim=(-1, 1), edge_tol=-1e-9)


def test_slowest_first_orders_by_median_then_key():
    medians = pd.Series({"P003": 2.0, "P001": 5.0, "P002": 2.0, "P004": 9.0})
    assert participants.slowest_first(medians) == ["P004", "P001", "P002", "P003"]


def _panel_sizes_in(fig):
    w, h = fig.get_size_inches()
    return {(round(ax.get_position().width * w, 6), round(ax.get_position().height * h, 6))
            for ax in fig.axes}


def test_participants_figure_runs_slowest_first_with_equal_panels(trials1):
    """One box per participant, ordered by the median ICL test response time, slowest first;
    every panel the same size; y tick labels in the first column only."""
    from geo_alg_ti_humans import prepare

    module = cli._figure_module("fig_participants")
    fig, stats = module.draw(trials1)
    try:
        assert tuple(fig.get_size_inches()) == (style.DOUBLE_COL_W, module.HEIGHT_IN)
        assert module.HEIGHT_IN <= 7.5
        rt = prepare.rt_frame_experiment1_figures(trials1)
        medians = rt[rt["phase"] == "icl_test"].groupby("participant")["rt"].median()
        assert stats["order"] == medians.sort_values(ascending=False).index.tolist()
        assert len(fig.axes) == 2 * 3 and len(_panel_sizes_in(fig)) == 1
        fig.canvas.draw()
        labeled = [any(t.get_text() for t in ax.get_yticklabels()) for ax in fig.axes]
        assert labeled == [True, True, False, False, False, False]
    finally:
        plt.close(fig)


def test_participant_boxes_refuse_more_participants_than_boxes(trials1):
    from geo_alg_ti_humans import summaries

    boxes = cli._figure_module("_participants")
    tests = trials1[trials1["phase"].isin(["icl_test", "iwl_test"])]
    accuracy = summaries.participant_accuracy_by_distance(tests, series_col="phase")
    rt = summaries.participant_rt_by_distance(tests, series_col="phase", n_boot=10)
    with pytest.raises(ValueError, match="for 2 boxes"):
        boxes.draw_boxes(boxes.BoxGrid(n_columns=2, n_rows=1), ["P001", "P002", "P003"],
                         accuracy, rt, series=("icl_test",), series_col="phase",
                         colors={"icl_test": "C0"}, labels={"icl_test": "ICL test"},
                         rt_ylim=(0, 10), rt_yticks=(0, 10))


def test_participant_boxes_close_the_figure_when_a_panel_raises(trials1):
    """A box whose value falls outside the shared range raises and leaves no figure open."""
    from geo_alg_ti_humans import summaries

    boxes = cli._figure_module("_participants")
    tests = trials1[trials1["phase"].isin(["icl_test", "iwl_test"])]
    accuracy = summaries.participant_accuracy_by_distance(tests, series_col="phase")
    rt = summaries.participant_rt_by_distance(tests, series_col="phase", n_boot=10)
    open_before = plt.get_fignums()
    with pytest.raises(ValueError, match="outside the drawn y range"):
        boxes.draw_boxes(boxes.BoxGrid(n_columns=2, n_rows=1), ["P001"], accuracy, rt,
                         series=("icl_test",), series_col="phase", colors={"icl_test": "C0"},
                         labels={"icl_test": "ICL test"}, rt_ylim=(0, 1), rt_yticks=(0, 1))
    assert plt.get_fignums() == open_before


def test_participant_slopes_figure_letters_both_panels(trials1):
    from geo_alg_ti_humans import summaries

    module = cli._figure_module("fig_participant_slopes")
    fig, stats = module.draw(trials1)
    try:
        texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert sorted(t for t in texts if len(t) == 1) == ["A", "B"]
        assert tuple(fig.get_size_inches()) == (style.DOUBLE_COL_W, module.HEIGHT_IN)
        slopes = summaries.participant_slopes_experiment1(trials1, n_boot=module.N_BOOT,
                                                          seed=module.SEED)
        wide = slopes.pivot(index="participant", columns="phase", values="rt_slope_pct")
        assert stats["rt"]["n_in_shaded_region"] == int((wide["icl_test"] > 1e-9).sum())
        assert stats["accuracy"]["n"] == stats["rt"]["n"] == 3
    finally:
        plt.close(fig)


@pytest.mark.parametrize("condition", ["congruent", "shuffled"])
def test_experiment2_participant_pages_draw_one_condition(frames2, condition):
    """Each page draws the retained participants of its condition, slowest first."""
    from geo_alg_ti_humans import summaries

    trials, _ = frames2
    module = cli._figure_module(f"fig_participants_{condition}")
    fig, stats = module.draw(trials)
    try:
        assert tuple(fig.get_size_inches()) == (style.DOUBLE_COL_W, module.HEIGHT_IN)
        kept = trials[trials["retained"] & (trials["condition"] == condition)]
        measures = summaries.participant_rt_measures(kept).set_index("participant")
        assert stats["order"] == measures["median_rt_s"].sort_values(
            ascending=False).index.tolist()
        assert stats["participant_set"]["n_participants"] == 2
        assert stats["participant_set"]["all_finishers"] == (2 if condition == "congruent"
                                                             else 3)
        assert len(_panel_sizes_in(fig)) == 1
    finally:
        plt.close(fig)
