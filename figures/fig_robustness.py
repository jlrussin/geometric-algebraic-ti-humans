"""Experiment 2 on all finishers: accuracy and response time by symbolic distance, as in the
main text, for every participant who passed the response-pattern rules, including those who
answered at chance. Tables: experiment2 sessions and trials.
"""

from __future__ import annotations

import argparse

import pandas as pd
from matplotlib.figure import Figure

from _shared import (
    experiment2_frames,
    letter_panels,
    main,
    mosaic_figure,
    participants_by_condition,
    retained,
)
from geo_alg_ti_humans.plots import distance, style

NAME = "robustness"
MOSAIC = (("acc", "rt"),)
LETTERS = {"acc": "A", "rt": "B"}
HEIGHT_IN = 2.6
RC = {"legend.handlelength": 1.5}

CONDITIONS = ("congruent", "shuffled")
COLORS = {c: style.CONTEXT_COLORS[c] for c in CONDITIONS}
LABELS = {c: style.CONTEXT_LABELS[c] for c in CONDITIONS}
# One series per condition, as in the main text, with every participant drawn as a point.
COMMON = dict(
    group_col="condition", phases=CONDITIONS, colors=COLORS, labels=LABELS,
    point_dodge=0.16, jitter_width=0.05,
    xlim=None, xticks="auto", yticks=None,
)
ACC = dict(ylim=(-0.02, 1.02))
# Correct, answered questions without the response-time outliers (``rt_trimmed``); the range
# follows the data.
RT = dict(rt_scale=0.001, exclude_col="rt_trimmed", ylabel=style.RESPONSE_TIME_LABEL, ylim=None)


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from all finishers' main questions, and the statistics it drew.

    ``trials`` carries the response-time outlier flag ``rt_trimmed`` and the boolean
    ``retained`` (``experiment2_frames``); the retained participants are counted, not selected.
    """
    per_participant = trials.groupby("participant")["condition"].nunique()
    if (per_participant != 1).any():
        raise ValueError("a participant has two conditions")
    drawn = participants_by_condition(trials, CONDITIONS)
    kept = participants_by_condition(retained(trials), CONDITIONS)
    stats = {
        "participant_set": "all_finishers",
        "participants_by_condition": drawn,
        "participants_by_condition_retained": kept,
        "participants_drawn_minus_retained": {c: drawn[c] - kept[c] for c in CONDITIONS},
        "n_trials_in_set": int(len(trials)),
    }
    with mosaic_figure(MOSAIC, width_in=style.DOUBLE_COL_W, height_in=HEIGHT_IN,
                       height_ratios=(1.0,), width_ratios=(1.0, 1.0), rc=RC) as (fig, axs):
        stats["acc"] = distance.make_accuracy_by_distance(axs["acc"], trials, **COMMON, **ACC)
        stats["rt"] = distance.make_rt_by_distance(axs["rt"], trials, **COMMON, **RT)
        letter_panels(axs, LETTERS)
    return fig, stats


def build(args: argparse.Namespace) -> Figure:
    """Load all finishers' main questions from the tables and draw the figure."""
    trials, _ = experiment2_frames(args.data)
    fig, _ = draw(trials)
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
