"""Experiment 1 per-pair test results: accuracy and response time for each of the 21 item pairs
on the IWL and ICL tests. Tables: experiment1 sessions and trials.
"""

from __future__ import annotations

import argparse

import pandas as pd
from matplotlib.figure import Figure

from _shared import experiment1_trials, letter_panels, main, mosaic_figure
from geo_alg_ti_humans.plots import pairs, style

NAME = "pairs"
# Two full-width rows sharing one x layout: the 21 rotated pair labels need the full width.
MOSAIC = (("acc",), ("rt",))
LETTERS = {"acc": "A", "rt": "B"}
HEIGHT_IN = 4.0
RC = {"legend.handlelength": 1.5}

# The block labels ("Distance 1", ...) hang a fixed number of points under the rotated pair
# labels; xlabel_pad leaves room beneath them. x_margin pads the x range around the pairs.
PAIRS_SHARED = dict(
    point_dodge=0.25, xlabel_pad=16.0, block_label_offset_pt=19.0,
    xlim=None, x_margin=0.7, xticks=None,
)
# Every pair's mean accuracy is above chance, so a two-column legend fits under the chance line.
PAIRS_ACC = dict(ylim=(-0.02, 1.02), yticks=None, legend_ncol=2)
PAIRS_RT = dict(ylim=(0, 18), yticks=(0, 5, 10, 15))


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from the kept participants' test trials, and the statistics it drew."""
    with mosaic_figure(MOSAIC, width_in=style.DOUBLE_COL_W, height_in=HEIGHT_IN,
                       height_ratios=(1.0, 1.0), width_ratios=(1.0,), rc=RC) as (fig, axs):
        stats = {
            "acc": pairs.make_pair_accuracy(axs["acc"], trials, **PAIRS_SHARED, **PAIRS_ACC),
            "rt": pairs.make_pair_rt(axs["rt"], trials, **PAIRS_SHARED, **PAIRS_RT),
        }
        letter_panels(axs, LETTERS)
    return fig, stats


def build(args: argparse.Namespace) -> Figure:
    """Load the kept participants' trials from the tables and draw the figure."""
    fig, _ = draw(experiment1_trials(args.data))
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
