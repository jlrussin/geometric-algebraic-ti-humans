"""How participants learned the ordering in Experiment 1: accuracy and response time over the
learning phase with the context shown or masked, and both against the number of intervening
distractors in the first and second half of the learning phase. Tables: experiment1 sessions
and trials.
"""

from __future__ import annotations

import argparse

import pandas as pd
from matplotlib.figure import Figure

from _shared import experiment1_trials, letter_panels, main, mosaic_figure
from geo_alg_ti_humans.plots import learning, style

NAME = "learning"
# Top row: the learning curves; bottom row: the same two measures against intervening
# distractors. Columns share a measure, rows share an x-axis.
MOSAIC = (("acc_bin", "rt_bin"), ("acc_distractors", "rt_distractors"))
LETTERS = {"acc_bin": "A", "rt_bin": "B", "acc_distractors": "C", "rt_distractors": "D"}
HEIGHT_IN = 4.6

N_TRIALS = 100                # learning trials per participant
BIN_WIDTH = 20                # top row: five bins of 20 trials
# The two accuracy panels share a range that gives most of the height to 0.5-1.0, with the
# chance line in view; the two response-time panels share 0-7 s.
ACC_YLIM = (0.4, 1.02)
ACC_YTICKS = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
# The accuracy legends sit just above the chance line, in axes fractions.
ACC_LEGEND_ANCHOR_Y = 0.22
RT_YLIM = (0, 7)
BIN_EDGES = tuple(range(0, N_TRIALS + 1, BIN_WIDTH))
XLIM_DISTRACTORS = (-0.2, 2.2)
# The ticks mark the bin edges, so the bin width is passed with them.
BINS = dict(bin_width=BIN_WIDTH, xlim=(0, N_TRIALS), xticks=BIN_EDGES)
DISTRACTORS = dict(xlim=XLIM_DISTRACTORS, xticks=(0, 1, 2))
RT = dict(ylim=RT_YLIM, yticks=None)
ACC = dict(ylim=ACC_YLIM, yticks=ACC_YTICKS)
ACC_BIN = dict(legend_bbox=(1.0, ACC_LEGEND_ANCHOR_Y))
ACC_DISTRACTORS = dict(legend_bbox=(0.0, ACC_LEGEND_ANCHOR_Y))


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from the kept participants' learning trials, and the statistics it drew."""
    with mosaic_figure(MOSAIC, width_in=style.DOUBLE_COL_W, height_in=HEIGHT_IN,
                       height_ratios=(1.0, 1.0), width_ratios=(1.0, 1.0)) as (fig, axs):
        stats = {
            "acc_bin": learning.make_accuracy_by_bin(
                axs["acc_bin"], trials, **BINS, **ACC, **ACC_BIN),
            "rt_bin": learning.make_rt_by_bin(axs["rt_bin"], trials, **BINS, **RT),
            "acc_distractors": learning.make_accuracy_by_distractors(
                axs["acc_distractors"], trials, **DISTRACTORS, **ACC, **ACC_DISTRACTORS),
            "rt_distractors": learning.make_rt_by_distractors(
                axs["rt_distractors"], trials, **DISTRACTORS, **RT),
        }
        letter_panels(axs, LETTERS)
    return fig, stats


def build(args: argparse.Namespace) -> Figure:
    """Load the kept participants' trials from the tables and draw the figure."""
    fig, _ = draw(experiment1_trials(args.data))
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
