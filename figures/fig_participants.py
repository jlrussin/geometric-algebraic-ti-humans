"""Experiment 1, one participant at a time: each kept participant's accuracy and response time by
symbolic distance on the ICL and IWL tests, from the slowest to the fastest median ICL test
response time. Tables: experiment1 sessions and trials.
"""

from __future__ import annotations

import argparse

import pandas as pd
from matplotlib.figure import Figure

from _participants import N_BOOT, SEED, BoxGrid, draw_boxes
from _shared import experiment1_trials, main
from geo_alg_ti_humans import prepare, summaries
from geo_alg_ti_humans.plots import participants, style

NAME = "participants"
GRID = BoxGrid(n_columns=8, n_rows=5)
HEIGHT_IN = GRID.height_in

TESTS = ("icl_test", "iwl_test")
COLORS = {"icl_test": style.TEST_COLORS["icl"], "iwl_test": style.TEST_COLORS["iwl"]}
LABELS = {"icl_test": "ICL test", "iwl_test": "IWL test"}
# The two tests sit a little to either side of each distance, so equal values stay visible.
OFFSETS = {"icl_test": -0.09, "iwl_test": 0.09}
# The test whose median response time orders the participants.
ORDER_TEST = "icl_test"
RT = dict(rt_ylim=(0, 43), rt_yticks=(0, 20, 40))


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from the kept participants' trials, and the statistics it drew."""
    tests = trials[trials["phase"].isin(TESTS)]
    # The response-time rows of the Experiment 1 figures: answered, correct, no outlier removal.
    answered = prepare.rt_frame_experiment1_figures(tests)
    accuracy = summaries.participant_accuracy_by_distance(tests, series_col="phase")
    rt = summaries.participant_rt_by_distance(answered, series_col="phase", n_boot=N_BOOT,
                                              seed=SEED)
    ordering = answered[answered["phase"] == ORDER_TEST]
    median_s = ordering.groupby("participant", observed=True)["rt"].median() * 0.001
    people = sorted(tests["participant"].unique())
    if sorted(median_s.index) != people:
        raise ValueError("draw: every participant needs an answered, correct trial on the "
                         f"{ORDER_TEST}")
    order = participants.slowest_first(median_s)
    fig, stats = draw_boxes(GRID, order, accuracy, rt, series=TESTS, series_col="phase",
                            colors=COLORS, labels=LABELS, offsets=OFFSETS, **RT)
    stats["n_participants"] = len(people)
    stats["order_median_rt_s"] = {p: round(float(median_s[p]), 4) for p in order}
    return fig, stats


def build(args: argparse.Namespace) -> Figure:
    """Load the kept participants' trials from the tables and draw the figure."""
    fig, _ = draw(experiment1_trials(args.data))
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
