"""Experiment 2, Shuffled condition, one participant at a time: each retained participant's
accuracy and response time by symbolic distance, from the slowest to the fastest median response
time. Tables: experiment2 sessions, trials and questionnaire.
"""

from __future__ import annotations

import argparse

import pandas as pd
from matplotlib.figure import Figure

from _participants import EXPERIMENT2_GRID, draw_condition
from _shared import experiment2_frames, main

NAME = "participants_shuffled"
CONDITION = "shuffled"
HEIGHT_IN = EXPERIMENT2_GRID.height_in


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from all finishers' main questions (with ``retained``), and its statistics."""
    return draw_condition(trials, CONDITION)


def build(args: argparse.Namespace) -> Figure:
    """Load the main questions from the tables and draw the figure."""
    trials, _ = experiment2_frames(args.data)
    fig, _ = draw(trials)
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
