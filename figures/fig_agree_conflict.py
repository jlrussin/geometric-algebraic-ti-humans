"""Experiment 2's shuffled condition split into agree and conflict questions, with the congruent
condition for comparison: accuracy and response time by symbolic distance for the retained
participants. Tables: experiment2 sessions and trials.
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
    questions_per_session,
    retained,
)
from geo_alg_ti_humans.plots import distance, style

NAME = "agree_conflict"
MOSAIC = (("acc", "rt"),)
LETTERS = {"acc": "A", "rt": "B"}
HEIGHT_IN = 2.6
RC = {"legend.handlelength": 1.5}

CONDITIONS = ("congruent", "shuffled")
SPLIT_CONDITION = "shuffled"
# The column added to the questions: the condition, with each shuffled question's type appended.
SERIES_COL = "series"
SERIES = ("congruent", "shuffled_agree", "shuffled_conflict")
SERIES_COLORS = {key: style.CONTEXT_COLORS[key] for key in SERIES}
SERIES_LABELS = {key: style.CONTEXT_LABELS[key] for key in SERIES}
# The symbolic distances every session asks about (``symbolic_distance`` in the trials codebook).
DISTANCES = (1, 2, 3, 4, 5, 6)
# A participant's questions (``questions_per_session``) spread evenly over the distances; a
# shuffled participant's questions at a distance split evenly into agree and conflict questions.
# A shuffled participant answers only a few questions of each type at a distance, so
# per-participant points would fall on a few values; they are not drawn.
COMMON = dict(
    phases=SERIES, labels=SERIES_LABELS, colors=SERIES_COLORS, group_col=SERIES_COL,
    show_points=False, xlim=None, xticks="auto",
)
ACC = dict(ylim=(-0.02, 1.02), yticks=None)
# Correct, answered questions without the response-time outliers (``rt_trimmed``).
RT = dict(
    rt_scale=0.001, exclude_col="rt_trimmed", ylabel=style.RESPONSE_TIME_LABEL, ylim=(0, 20),
    yticks=(0, 5, 10, 15, 20),
)


def series_of(trials: pd.DataFrame) -> pd.Series:
    """Each question's series: its condition, with the question type appended when shuffled."""
    condition = trials["condition"].astype(str)
    question_type = trials["question_type"].astype(str)
    return condition.where(condition != SPLIT_CONDITION, condition + "_" + question_type)


def _check(drawn: pd.DataFrame) -> None:
    """Raise unless the questions split as the design laid them out."""
    if set(drawn["condition"].unique()) != set(CONDITIONS):
        raise ValueError(f"the retained participants' conditions are not {CONDITIONS}")
    if not (drawn.loc[drawn["condition"] != SPLIT_CONDITION, "question_type"] == "agree").all():
        raise ValueError(f"a question outside the {SPLIT_CONDITION} condition is not 'agree'")
    distances = sorted(int(d) for d in drawn["symbolic_distance"].unique())
    if distances != list(DISTANCES):
        raise ValueError(f"the questions' symbolic distances are {distances}, not {DISTANCES}")
    questions = questions_per_session(drawn)
    per_distance, remainder = divmod(questions, len(DISTANCES))
    if remainder:
        raise ValueError(f"{questions} questions do not spread evenly over {len(DISTANCES)} "
                         "distances")
    if per_distance % 2:
        raise ValueError(f"{per_distance} questions at each distance, an odd count, cannot split "
                         "into agree and conflict halves")
    per = drawn.groupby(["participant", "symbolic_distance"]).size()
    if (len(per) != drawn["participant"].nunique() * len(DISTANCES)
            or not (per == per_distance).all()):
        raise ValueError(f"not every participant has {per_distance} questions at each distance")
    split = drawn[drawn["condition"] == SPLIT_CONDITION]
    halves = split.groupby(["participant", "symbolic_distance", SERIES_COL]).size()
    if not (halves == per_distance // 2).all():
        raise ValueError(f"a {SPLIT_CONDITION} participant's distance is not split evenly into "
                         "agree and conflict questions")


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from the retained participants' main questions, and the statistics it drew.

    ``trials`` holds all finishers' questions with the response-time outlier flag
    ``rt_trimmed``, the boolean ``retained`` and the session's saved ``n_main_questions``
    (``experiment2_frames``).
    """
    drawn = retained(trials)
    drawn = drawn.assign(**{SERIES_COL: series_of(drawn)})
    _check(drawn)
    stats = {
        "participant_set": "retained",
        "n_participants_by_condition_all_finishers": participants_by_condition(trials, CONDITIONS),
        "n_participants_by_condition": participants_by_condition(drawn, CONDITIONS),
        "n_questions": int(len(drawn)),
        "n_timeouts_by_series": {
            key: int(drawn.loc[drawn[SERIES_COL] == key, "is_timed_out"].astype(bool).sum())
            for key in SERIES},
    }
    with mosaic_figure(MOSAIC, width_in=style.DOUBLE_COL_W, height_in=HEIGHT_IN,
                       height_ratios=(1.0,), width_ratios=(1.0, 1.0), rc=RC) as (fig, axs):
        stats["acc"] = distance.make_accuracy_by_distance(axs["acc"], drawn, **COMMON, **ACC)
        stats["rt"] = distance.make_rt_by_distance(axs["rt"], drawn, **COMMON, **RT)
        letter_panels(axs, LETTERS)
    return fig, stats


def build(args: argparse.Namespace) -> Figure:
    """Load the main questions from the tables and draw the figure."""
    trials, _ = experiment2_frames(args.data)
    fig, _ = draw(trials)
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
