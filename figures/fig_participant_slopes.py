"""Experiment 1, one point per participant: each kept participant's symbolic distance slope on
the ICL test against their slope on the IWL test, for accuracy and for response time. Tables:
experiment1 sessions and trials.
"""

from __future__ import annotations

import argparse

import pandas as pd
from matplotlib.figure import Figure

from _participants import N_BOOT, SEED
from _shared import experiment1_trials, letter_panels, main, mosaic_figure
from geo_alg_ti_humans import summaries
from geo_alg_ti_humans.plots import participants, style

NAME = "participant_slopes"
MOSAIC = (("accuracy", "rt"),)
LETTERS = {"accuracy": "A", "rt": "B"}
HEIGHT_IN = 3.25

# Each panel's slope columns in ``summaries.participant_slopes_experiment1``.
MEASURES = {"accuracy": "accuracy_slope", "rt": "rt_slope_pct"}
# The IWL test on x and the ICL test on y; whiskers are one bootstrap standard deviation.
SHARED = dict(x_col="iwl_test", y_col="icl_test", x_err_col="iwl_test_sd",
              y_err_col="icl_test_sd")
# The tinted regions: accuracy falling with distance on the ICL test and rising on the IWL
# test; response time rising with distance on the ICL test, whatever it does on the IWL test.
ACCURACY = dict(
    shade="lower_right", title="Accuracy",
    xlim=(-0.24, 0.24), ylim=(-0.24, 0.24),
    xticks=(-0.2, -0.1, 0.0, 0.1, 0.2), yticks=(-0.2, -0.1, 0.0, 0.1, 0.2),
    xlabel="IWL test slope", ylabel="ICL test slope",
)
RT = dict(
    shade="upper_half", title="Response time",
    xlim=(-30, 30), ylim=(-100, 100),
    xticks=(-30, -20, -10, 0, 10, 20, 30), yticks=(-100, -50, 0, 50, 100),
    xlabel="IWL test slope (% per unit of symbolic distance)",
    ylabel="ICL test slope (% per unit of symbolic distance)",
)


def wide_slopes(slopes: pd.DataFrame, measure: str) -> pd.DataFrame:
    """One row per participant: the measure's slope and its standard deviation on each test."""
    wide = slopes.pivot(index="participant", columns="phase",
                        values=[measure, f"{measure}_sd"])
    out = pd.DataFrame({"participant": wide.index})
    for test in ("iwl_test", "icl_test"):
        out[test] = wide[(measure, test)].to_numpy()
        out[f"{test}_sd"] = wide[(f"{measure}_sd", test)].to_numpy()
    return out


def draw(trials: pd.DataFrame) -> tuple[Figure, dict]:
    """The figure from the kept participants' trials, and the statistics it drew."""
    slopes = summaries.participant_slopes_experiment1(trials, n_boot=N_BOOT, seed=SEED)
    with mosaic_figure(MOSAIC, width_in=style.DOUBLE_COL_W, height_in=HEIGHT_IN,
                       height_ratios=(1.0,), width_ratios=(1.0, 1.0)) as (fig, axs):
        stats = {
            "accuracy": participants.make_slope_scatter(
                axs["accuracy"], wide_slopes(slopes, MEASURES["accuracy"]), **SHARED, **ACCURACY),
            "rt": participants.make_slope_scatter(
                axs["rt"], wide_slopes(slopes, MEASURES["rt"]), **SHARED, **RT),
        }
        letter_panels(axs, LETTERS)
    return fig, stats


def build(args: argparse.Namespace) -> Figure:
    """Load the kept participants' trials from the tables and draw the figure."""
    fig, _ = draw(experiment1_trials(args.data))
    return fig


if __name__ == "__main__":
    main(build, name=NAME)
