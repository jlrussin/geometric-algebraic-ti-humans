"""Experiment 2 strategies: how many statements participants judged true of the real world, how
often they said they answered from real-world knowledge, and how each participant's response-time
slope over symbolic distance relates to their speed and to their knowledge answer. Retained
participants. Tables: experiment2 sessions, trials and questionnaire.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence

import pandas as pd
from matplotlib.figure import Figure

from _shared import (
    experiment2_frames,
    letter_panels,
    main,
    mosaic_figure,
    participants_by_condition,
    questions_per_session,
    retained,
)
from geo_alg_ti_humans import prepare, summaries
from geo_alg_ti_humans.plots import strategies, style

NAME = "strategies"
# Top row: the two questionnaire items as stacked bars; bottom row: the per-participant
# measures. The top row holds two bars and a legend, so it is shorter.
MOSAIC = (("statements", "knowledge"), ("speed", "rating"))
LETTERS = {"statements": "A", "knowledge": "B", "speed": "C", "rating": "D"}
HEIGHT_IN = 4.3
RC = {"legend.handlelength": 1.5}

CONDITIONS = ("congruent", "shuffled")
STATEMENTS_ITEM = "statements_true"
KNOWLEDGE_ITEM = "knowledge_use"
# Each item's answer options as participants saw them, in order.
OPTIONS: dict[str, tuple[str, ...]] = {
    STATEMENTS_ITEM: ("All of them", "Most of them", "About half of them", "Few of them",
                      "None of them", "I don't know"),
    KNOWLEDGE_ITEM: ("Never", "Rarely", "Sometimes", "Often", "Always"),
}
KNOWLEDGE_OFF_SCALE = ()
# The speed and slope panels share the slope range; the speed axis is logarithmic.
SLOPE_YLIM = (-20, 40)
SLOPE_YTICKS = (-20, -10, 0, 10, 20, 30, 40)
BARS_SHARED = dict(
    off_hatch="//////", hatch_lw=0.4, bar_height=0.62,
    # Two lines, so the bar labels are no wider than the bottom row's y-axis decorations.
    tick_label="{name}\n(n = {n})",
    xlim=(0, 100), xticks=(0, 25, 50, 75, 100),
    # Bars at y = 0 and 1 with the axis inverted; the space above holds the legend.
    ylim=(1.45, -1.95),
    legend_bbox=(0.0, 1.0), legend_ncol=3, legend_title_fontsize=style.LEGEND_SIZE,
    legend_borderaxespad=0.0,
)
STATEMENTS_BARS = dict(item=STATEMENTS_ITEM, legend_title="Statements true of the real world")
KNOWLEDGE_BARS = dict(item=KNOWLEDGE_ITEM, off_scale=KNOWLEDGE_OFF_SCALE,
                      legend_title="Answered from real-world knowledge")
POINTS_SHARED = dict(ylim=SLOPE_YLIM, yticks=SLOPE_YTICKS)
SPEED = dict(
    point_alpha=0.7, legend_handletextpad=0.2,
    xlim=(0.6, 32), xticks=(1, 2, 5, 10, 20),
)
# Violins of the slope by the knowledge answer, every participant drawn on top.
RATING = dict(
    cat_col=KNOWLEDGE_ITEM, xlim=(-0.5, 4.5),
    xlabel="Self-rated use of real-world knowledge",
    legend_handlelength=1.0, legend_handleheight=1.0, legend_handletextpad=0.5,
)


def draw(
    trials: pd.DataFrame,
    questionnaire: pd.DataFrame,
    *,
    options: Mapping[str, Sequence[str]] = OPTIONS,
) -> tuple[Figure, dict]:
    """The figure from the retained participants' questions and answers, and its statistics.

    ``trials`` and ``questionnaire`` hold all finishers with the boolean ``retained``; the
    questions also carry ``log_rt``, ``rt_trimmed`` and the session's saved
    ``n_main_questions`` (``experiment2_frames``).
    """
    kept_trials = retained(trials)
    answers = retained(questionnaire)
    questions = questions_per_session(kept_trials)
    if (kept_trials.groupby("participant").size() != questions).any():
        raise ValueError(f"expected {questions} main questions per participant")
    measures = summaries.participant_rt_measures(kept_trials)
    rated = strategies.attach_answers(measures, answers, item=KNOWLEDGE_ITEM)
    stats = {"participant_set": {
        "name": "retained",
        "trials": participants_by_condition(kept_trials, CONDITIONS),
        "questionnaire": participants_by_condition(answers, CONDITIONS),
        "all_finishers": {"trials": participants_by_condition(trials, CONDITIONS),
                          "questionnaire": participants_by_condition(questionnaire, CONDITIONS)},
    }}
    with mosaic_figure(MOSAIC, width_in=style.DOUBLE_COL_W, height_in=HEIGHT_IN,
                       height_ratios=(0.5, 1.0), width_ratios=(1.0, 1.0), rc=RC) as (fig, axs):
        stats["statements"] = strategies.make_answer_bars(
            axs["statements"], answers, options=options[STATEMENTS_ITEM], **BARS_SHARED,
            **STATEMENTS_BARS)
        stats["knowledge"] = strategies.make_answer_bars(
            axs["knowledge"], answers, options=options[KNOWLEDGE_ITEM], **BARS_SHARED,
            **KNOWLEDGE_BARS)
        stats["speed"] = strategies.make_participant_scatter(
            axs["speed"], measures, **POINTS_SHARED, **SPEED)
        stats["rating"] = strategies.make_category_violins(
            axs["rating"], rated, categories=options[KNOWLEDGE_ITEM], **POINTS_SHARED, **RATING)
        stats["measures"] = _measure_stats(kept_trials, measures)
        letter_panels(axs, LETTERS)
    return fig, stats


def _measure_stats(trials: pd.DataFrame, measures: pd.DataFrame) -> dict:
    """Question counts behind the measures (``kept``: answered, correct, not an outlier, as
    ``prepare.rt_kept_experiment2`` keeps them), and each participant's measures."""
    by_condition = {}
    for c in CONDITIONS:
        t = trials[trials["condition"] == c]
        answered = ~prepare.as_bool(t["is_timed_out"], "_measure_stats")
        correct = answered & prepare.as_bool(t["is_correct"], "_measure_stats")
        trimmed = correct & ~prepare.rt_kept_experiment2(t)
        by_condition[c] = {
            "questions": int(len(t)), "answered": int(answered.sum()),
            "answered_correct": int(correct.sum()),
            "answered_correct_trimmed": int(trimmed.sum()),
            "kept": int(measures.loc[measures["condition"] == c, "n_questions"].sum()),
        }
    return {
        "questions": by_condition,
        "n_questions": {
            c: {"min": int(m["n_questions"].min()),
                "median": float(m["n_questions"].median()),
                "max": int(m["n_questions"].max())}
            for c, m in measures.groupby("condition")},
        "per_participant": {
            r["participant"]: {
                "condition": r["condition"],
                "n_questions": int(r["n_questions"]),
                "median_rt_s": round(float(r["median_rt_s"]), 4),
                "rt_slope_pct": round(float(r["rt_slope_pct"]), 4)}
            for _, r in measures.iterrows()},
    }


def build(args: argparse.Namespace) -> Figure:
    """Load the main questions and the questionnaire from the tables and draw the figure."""
    trials, questionnaire = experiment2_frames(args.data)
    fig, _ = draw(trials, questionnaire)
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
