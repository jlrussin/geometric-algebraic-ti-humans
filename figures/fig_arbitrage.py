"""The Experiment 1 arbitrage test: which ordering responses followed by symbolic distance, how
long those responses took, and the distribution of each participant's own proportion. Tables:
experiment1 sessions and trials.
"""

from __future__ import annotations

import argparse

import pandas as pd
from matplotlib.figure import Figure

from _shared import experiment1_trials, letter_panels, main, mosaic_figure
from geo_alg_ti_humans.plots import arbitrage, style

NAME = "arbitrage"
MOSAIC = (("outcomes", "rt", "hist"),)
LETTERS = {"outcomes": "A", "rt": "B", "hist": "C"}
HEIGHT_IN = 2.4
RC = {"legend.handlelength": 1.5}

SHARED = dict(xlim=None, xticks="auto")
OUTCOMES_BY_D = dict(ylim=(-0.02, 1.02), yticks=None)
RT_BY_D = dict(ylim=(0, 15), yticks=(0, 5, 10, 15))
PARTICIPANT_HIST = dict(
    xlim=(-0.02, 1.02), ylim=(0, 15), xticks=(0, 0.2, 0.4, 0.6, 0.8, 1.0), yticks=(0, 5, 10, 15),
)


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from the kept participants' arbitrage trials, and the statistics it drew."""
    with mosaic_figure(MOSAIC, width_in=style.DOUBLE_COL_W, height_in=HEIGHT_IN,
                       height_ratios=(1.0,), width_ratios=(1.0, 1.0, 1.0), rc=RC) as (fig, axs):
        stats = {
            "outcomes": arbitrage.make_outcomes_by_distance(
                axs["outcomes"], trials, **SHARED, **OUTCOMES_BY_D),
            "rt": arbitrage.make_rt_by_distance_split(axs["rt"], trials, **SHARED, **RT_BY_D),
            "hist": arbitrage.make_participant_histogram(axs["hist"], trials, **PARTICIPANT_HIST),
        }
        letter_panels(axs, LETTERS)
    return fig, stats


def build(args: argparse.Namespace) -> Figure:
    """Load the kept participants' trials from the tables and draw the figure."""
    fig, _ = draw(experiment1_trials(args.data))
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
