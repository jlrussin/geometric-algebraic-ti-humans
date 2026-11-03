"""The participant box figures: one box per participant, holding that participant's accuracy
above their response time by symbolic distance.

Boxes run in rows from the slowest to the fastest participant. They are placed at fixed
positions in inches rather than by constrained layout, so every panel has the same size and only
the first column carries y tick labels; the page keeps its declared size. Experiment 1's figure
(``fig_participants.py``) and Experiment 2's two figures, one per condition
(``fig_participants_congruent.py``, ``fig_participants_shuffled.py``), share this layout; the
Experiment 2 settings live here, since the two condition pages share them, and so do the bootstrap
settings of every participant figure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.layout_engine import PlaceHolderLayoutEngine
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

from _shared import participants_by_condition, retained, styled_figure
from geo_alg_ti_humans import summaries
from geo_alg_ti_humans.plots import participants, style


@dataclass(frozen=True)
class BoxGrid:
    """A page of ``n_rows`` rows of ``n_columns`` participant boxes; lengths in inches."""

    n_columns: int
    n_rows: int
    width_in: float = style.DOUBLE_COL_W
    left_in: float = 0.40          # the first column's y tick labels and axis labels
    right_in: float = 0.03
    top_in: float = 0.24           # the legend
    bottom_in: float = 0.22        # the x-axis label
    gap_in: float = 0.075          # between neighboring boxes
    pad_in: float = 0.04           # between a box's edge and its panels
    key_in: float = 0.115          # the participant key, above the panels
    panel_h_in: float = 0.44
    inner_gap_in: float = 0.075    # between the accuracy and the response-time panel
    ticks_in: float = 0.115        # the x tick labels, below the lower panel

    @property
    def capacity(self) -> int:
        return self.n_columns * self.n_rows

    @property
    def box_w_in(self) -> float:
        inner = self.width_in - self.left_in - self.right_in
        return (inner - (self.n_columns - 1) * self.gap_in) / self.n_columns

    @property
    def box_h_in(self) -> float:
        return (self.pad_in + self.key_in + self.panel_h_in + self.inner_gap_in
                + self.panel_h_in + self.ticks_in)

    @property
    def panel_w_in(self) -> float:
        return self.box_w_in - 2 * self.pad_in

    @property
    def height_in(self) -> float:
        return (self.top_in + self.n_rows * self.box_h_in + (self.n_rows - 1) * self.gap_in
                + self.bottom_in)


# The look shared by every box: the gray box, the participant key, and both panels' settings
# (``participants.make_participant_by_distance`` keywords). Lines and markers are thinner than
# on the other figures, since each panel is about half an inch tall.
BOX_COLOR = "#f0f0f0"
BOX_RADIUS_IN = 0.04
KEY_SIZE = style.TICK_LABEL_SIZE
KEY_COLOR = "0.25"
LEGEND = dict(handlelength=1.6, columnspacing=1.6)
XLABEL = "Symbolic distance"
LINES = dict(line_width=0.9, marker_size=2.4, band_alpha=0.25)
ACCURACY = dict(ylim=(-0.02, 1.02), yticks=(0.0, 0.5, 1.0), ytick_format="{:.1f}",
                show_chance=True, ylabel="Accuracy")
RT = dict(ytick_format="{:.0f}", ylabel=style.RESPONSE_TIME_SHORT_LABEL)
# Resamples and seed of every bootstrap in the participant figures.
N_BOOT = 1000
SEED = 0


def _add_axes(fig: Figure, x_in: float, top_in: float, w_in: float, h_in: float):
    """Axes at ``x_in`` from the left edge and ``top_in`` below the top edge."""
    w, h = fig.get_size_inches()
    return fig.add_axes((x_in / w, 1.0 - (top_in + h_in) / h, w_in / w, h_in / h))


def draw_boxes(
    grid: BoxGrid,
    order: Sequence[str],
    accuracy: pd.DataFrame,
    rt: pd.DataFrame,
    *,
    series: Sequence[str],
    series_col: str,
    colors: Mapping[str, str],
    labels: Mapping[str, str],
    rt_ylim: tuple[float, float],
    rt_yticks: Sequence[float],
    offsets: Mapping[str, float] | None = None,
) -> tuple[Figure, dict]:
    """The page of boxes for the participants in ``order``, row by row, and its statistics.

    ``accuracy`` and ``rt`` are the long frames of ``summaries.participant_accuracy_by_distance``
    and ``participant_rt_by_distance``; every response-time panel shares ``rt_ylim`` and
    ``rt_yticks``. Raises if ``order`` repeats a participant, holds more participants than the
    grid, or names one without rows. Returns the figure and, per participant, the box position
    and the statistics of both panels, with totals and the grid's sizes.
    """
    fname = "draw_boxes"
    order = list(order)
    if len(set(order)) != len(order):
        raise ValueError(f"{fname}: a participant appears twice in the order")
    if len(order) > grid.capacity:
        raise ValueError(f"{fname}: {len(order)} participants for {grid.capacity} boxes")
    by_participant = {name: dict(tuple(df.groupby("participant", sort=False, observed=True)))
                      for name, df in (("accuracy", accuracy), ("rt", rt))}
    for name, groups in by_participant.items():
        missing = [p for p in order if p not in groups]
        if missing:
            raise ValueError(f"{fname}: no {name} rows for {missing}")
    # A layout engine that does nothing: the axes keep their positions, and saving does not
    # switch on the style's constrained layout. The figure is closed if a panel raises.
    with styled_figure(figsize=(grid.width_in, grid.height_in),
                       layout=PlaceHolderLayoutEngine(adjust_compatible=True,
                                                      colorbar_gridspec=True)) as fig:
        lines = {**LINES, "series": series, "series_col": series_col, "colors": colors,
                 "offsets": offsets}
        stats = {"order": order, "per_participant": {}}
        for i, participant in enumerate(order):
            row, col = divmod(i, grid.n_columns)
            x0 = grid.left_in + col * (grid.box_w_in + grid.gap_in)
            y0 = grid.top_in + row * (grid.box_h_in + grid.gap_in)
            fig.add_artist(FancyBboxPatch(
                (x0, grid.height_in - y0 - grid.box_h_in), grid.box_w_in, grid.box_h_in,
                boxstyle=f"round,pad=0,rounding_size={BOX_RADIUS_IN}",
                transform=fig.dpi_scale_trans, facecolor=BOX_COLOR, edgecolor="none", zorder=0))
            fig.text((x0 + grid.pad_in) / grid.width_in,
                     1.0 - (y0 + 0.6 * grid.pad_in) / grid.height_in, participant,
                     fontsize=KEY_SIZE, color=KEY_COLOR, ha="left", va="top")
            top = y0 + grid.pad_in + grid.key_in
            ax_acc = _add_axes(fig, x0 + grid.pad_in, top, grid.panel_w_in, grid.panel_h_in)
            ax_rt = _add_axes(fig, x0 + grid.pad_in, top + grid.panel_h_in + grid.inner_gap_in,
                              grid.panel_w_in, grid.panel_h_in)
            first = col == 0
            acc_settings = {**ACCURACY, "ylabel": ACCURACY["ylabel"] if first else None}
            rt_panel = {**RT, "ylim": rt_ylim, "yticks": rt_yticks,
                        "ylabel": RT["ylabel"] if first else None}
            for ax in (ax_acc, ax_rt):
                ax.set_facecolor("none")
            stats["per_participant"][participant] = {
                "row": row + 1, "column": col + 1,
                "accuracy": participants.make_participant_by_distance(
                    ax_acc, by_participant["accuracy"][participant], **lines, **acc_settings,
                    show_xticklabels=False, show_yticklabels=first),
                "rt": participants.make_participant_by_distance(
                    ax_rt, by_participant["rt"][participant], **lines, **rt_panel,
                    show_xticklabels=True, show_yticklabels=first),
            }
        handles = [Line2D([], [], color=colors[s], label=labels[s], lw=LINES["line_width"],
                          marker="o", markersize=LINES["marker_size"], markeredgewidth=0)
                   for s in series]
        fig.legend(handles=handles, loc="center", ncol=len(handles), frameon=False,
                   bbox_to_anchor=(0.5, 1.0 - 0.5 * grid.top_in / grid.height_in), **LEGEND)
        inner_mid = grid.left_in + (grid.width_in - grid.left_in - grid.right_in) / 2
        fig.text(inner_mid / grid.width_in, 0.5 * grid.bottom_in / grid.height_in, XLABEL,
                 fontsize=style.AXES_LABEL_SIZE, ha="center", va="center")
    stats["totals"] = _totals(stats["per_participant"])
    stats["grid"] = {"n_columns": grid.n_columns, "n_rows": grid.n_rows,
                     "box_in": [round(grid.box_w_in, 4), round(grid.box_h_in, 4)],
                     "panel_in": [round(grid.panel_w_in, 4), round(grid.panel_h_in, 4)],
                     "figure_in": [grid.width_in, round(grid.height_in, 4)]}
    return fig, stats


def _totals(per_participant: dict) -> dict:
    """Single-trial points, distances without a value and bands cut at the frame, per panel."""
    totals = {}
    for panel in ("accuracy", "rt"):
        series = [s for p in per_participant.values() for s in p[panel]["per_series"].values()]
        totals[panel] = {
            "n_single_trial_points": sum(s["n_single_trial_points"] for s in series),
            "n_missing_points": sum(len(s["missing_distances"]) for s in series),
            "n_bands_cut_at_frame": sum(s["n_bands_cut_at_frame"] for s in series),
        }
    return totals


# Experiment 2: ten boxes across. Both condition pages share the response-time range, as the
# two conditions share one axis in the main text's response-time panel.
EXPERIMENT2_GRID = BoxGrid(n_columns=10, n_rows=5)
EXPERIMENT2_RT = dict(rt_ylim=(0, 34), rt_yticks=(0, 10, 20, 30))
EXPERIMENT2_CONDITIONS = ("congruent", "shuffled")


def draw_condition(trials: pd.DataFrame, condition: str) -> tuple[Figure, dict]:
    """One Experiment 2 condition's page of boxes, from all finishers' main questions.

    ``trials`` carry the boolean ``retained``, ``log_rt`` and ``rt_trimmed``
    (``experiment2_frames``); the retained participants of ``condition`` are drawn. Accuracy
    uses every question; response time the answered, correct questions not flagged
    ``rt_trimmed``. Participants run from the slowest to the fastest median response time over
    those questions (``summaries.participant_rt_measures``).
    """
    if condition not in EXPERIMENT2_CONDITIONS:
        raise ValueError(f"draw_condition: unknown condition {condition!r}")
    kept = retained(trials)
    rows = kept[kept["condition"] == condition]
    if rows.empty:
        raise ValueError(f"draw_condition: no retained participants in {condition!r}")
    accuracy = summaries.participant_accuracy_by_distance(rows, series_col="condition")
    rt = summaries.participant_rt_by_distance(rows, series_col="condition",
                                              exclude_col="rt_trimmed", n_boot=N_BOOT, seed=SEED)
    measures = summaries.participant_rt_measures(rows).set_index("participant")
    order = participants.slowest_first(measures["median_rt_s"])
    fig, stats = draw_boxes(
        EXPERIMENT2_GRID, order, accuracy, rt, series=(condition,), series_col="condition",
        colors={condition: style.CONTEXT_COLORS[condition]},
        labels={condition: style.CONTEXT_LABELS[condition]}, **EXPERIMENT2_RT)
    stats["participant_set"] = {
        "name": "retained", "condition": condition,
        "n_participants": participants_by_condition(rows, (condition,))[condition],
        "all_finishers": participants_by_condition(trials, (condition,))[condition]}
    stats["order_median_rt_s"] = {p: round(float(measures.loc[p, "median_rt_s"]), 4)
                                  for p in order}
    return fig, stats
