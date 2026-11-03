"""Accuracy and response time by symbolic distance, one line per series.

A series is the set of rows whose ``group_col`` equals one of ``phases``: by default the ICL and
IWL tests of Experiment 1 in the ``phase`` column; Experiment 2 passes ``group_col="condition"``
or a column that splits the shuffled condition into agree and conflict questions.
``participant_col`` names the participant key. ``colors``, ``labels``, ``markers`` and
``linestyles`` are dicts keyed by series.

Each participant is aggregated first (mean accuracy, or median response time, per participant
and distance), then the mean and standard error are taken across participants
(``summaries.participant_mean_sem``).
"""

from __future__ import annotations

import numpy as np

from geo_alg_ti_humans.plots import (
    _check_in_frame,
    _draw_series,
    _finish_axes,
    _legend,
    _rounded_sem,
    _rt_frame,
)
from geo_alg_ti_humans.plots.style import REFERENCE_LINE_COLOR, TEST_COLORS
from geo_alg_ti_humans.summaries import participant_mean_sem

_DEFAULT_PHASES = ("icl_test", "iwl_test")
_DEFAULT_LABELS = {"icl_test": "ICL test", "iwl_test": "IWL test"}
_DEFAULT_COLORS = {
    "icl_test": TEST_COLORS["icl"],
    "iwl_test": TEST_COLORS["iwl"],
}


def _draw_phase_series(ax, summary, wide, *, x_col, color, label, offset, rng,
                       show_band, band_alpha, show_points, point_size,
                       point_alpha, jitter_width, marker, marker_size,
                       line_width, ylim, fname, linestyle=None):
    x = summary[x_col].to_numpy(dtype=float) + offset
    _draw_series(ax, x, summary["value_mean"], summary["value_sem"], color=color, label=label,
                 show_band=show_band, band_alpha=band_alpha, marker=marker,
                 marker_size=marker_size, line_width=line_width, line_style=linestyle,
                 ylim=ylim, fname=fname)
    if show_points:
        _check_in_frame(wide.to_numpy(dtype=float), ylim, axis="y", fname=fname)
        for xv in wide.index:
            vals = wide.loc[xv].dropna().to_numpy()
            jit = rng.uniform(-jitter_width, jitter_width, size=len(vals))
            ax.scatter(np.full(len(vals), float(xv) + offset) + jit, vals,
                       s=point_size, color=color, alpha=point_alpha, lw=0,
                       zorder=2)


def _make_by_distance(ax, trials, *, fname, value_col, agg, phases, labels, colors,
                      distance_col, group_col, participant_col, markers,
                      linestyles, show_band, band_alpha, show_points,
                      point_size, point_alpha, point_dodge, jitter_width,
                      jitter_seed, marker, marker_size, line_width,
                      show_chance, chance, chance_ls, chance_lw, chance_color,
                      xlabel, ylabel, xlim, ylim, xticks, yticks,
                      show_legend, legend_loc, legend_ncol, legend_title,
                      legend_fontsize, legend_bbox):
    rng = np.random.default_rng(jitter_seed)
    colors = {**_DEFAULT_COLORS, **(colors or {})}
    labels = {**_DEFAULT_LABELS, **(labels or {})}
    stats = {"per_phase": {}, "n_trials_used": 0}
    all_x = set()
    markers = markers or {}
    linestyles = linestyles or {}
    for i, phase in enumerate(phases):
        sub = trials[trials[group_col] == phase]
        summary, wide = participant_mean_sem(
            sub, x_col=distance_col, value_col=value_col,
            participant_col=participant_col, agg=agg)
        offset = (i - (len(phases) - 1) / 2) * point_dodge
        _draw_phase_series(
            ax, summary, wide, x_col=distance_col, color=colors[phase],
            label=labels[phase], offset=offset, rng=rng, show_band=show_band,
            band_alpha=band_alpha, show_points=show_points,
            point_size=point_size, point_alpha=point_alpha,
            jitter_width=jitter_width, marker=markers.get(phase, marker),
            marker_size=marker_size, line_width=line_width, ylim=ylim, fname=fname,
            linestyle=linestyles.get(phase))
        all_x.update(summary[distance_col].tolist())
        stats["n_trials_used"] += int(len(sub))
        stats["per_phase"][phase] = {
            "mean_by_distance": {
                int(r[distance_col]): round(float(r["value_mean"]), 4)
                for _, r in summary.iterrows()},
            "sem_by_distance": {
                int(r[distance_col]): _rounded_sem(r["value_sem"]) for _, r in summary.iterrows()},
            "n_participants_by_distance": {
                int(r[distance_col]): int(r["n_participants"])
                for _, r in summary.iterrows()},
        }
    if show_chance:
        ax.axhline(chance, color=chance_color, ls=chance_ls, lw=chance_lw,
                   zorder=1)
    _finish_axes(ax, xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                 xticks=xticks, yticks=yticks, x_values=all_x)
    if show_legend:
        _legend(ax, legend_loc=legend_loc, legend_ncol=legend_ncol,
                legend_title=legend_title, legend_fontsize=legend_fontsize,
                legend_bbox=legend_bbox)
    return stats


def make_accuracy_by_distance(
    ax, trials, *,
    phases=_DEFAULT_PHASES,
    labels=None,
    colors=None,
    distance_col="symbolic_distance",
    group_col="phase", participant_col="participant",
    markers=None, linestyles=None,
    show_band=True, band_alpha=0.25,
    show_points=True, point_size=3.0, point_alpha=0.25,
    point_dodge=0.0, jitter_width=0.08, jitter_seed=0,
    marker="o", marker_size=3.5, line_width=None,
    show_chance=True, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel="Symbolic distance", ylabel="Accuracy",
    xlim=None, ylim=(-0.02, 1.02), xticks="auto", yticks=None,
    show_legend=True, legend_loc="lower left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
) -> dict:
    """Accuracy by symbolic distance, one line per series.

    The mean and standard error across participants of each participant's accuracy at each
    distance; a question that ran out of time counts as incorrect (``is_correct`` is false).
    Returns, per series, the means, standard errors and participant counts by distance.
    """
    return _make_by_distance(
        ax, trials, fname="make_accuracy_by_distance",
        value_col="is_correct", agg="mean", phases=phases,
        labels=labels, colors=colors, distance_col=distance_col,
        group_col=group_col, participant_col=participant_col,
        markers=markers, linestyles=linestyles,
        show_band=show_band, band_alpha=band_alpha, show_points=show_points,
        point_size=point_size, point_alpha=point_alpha,
        point_dodge=point_dodge, jitter_width=jitter_width,
        jitter_seed=jitter_seed, marker=marker, marker_size=marker_size,
        line_width=line_width, show_chance=show_chance, chance=chance,
        chance_ls=chance_ls, chance_lw=chance_lw, chance_color=chance_color,
        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim, xticks=xticks,
        yticks=yticks, show_legend=show_legend, legend_loc=legend_loc,
        legend_ncol=legend_ncol, legend_title=legend_title,
        legend_fontsize=legend_fontsize, legend_bbox=legend_bbox)


def make_rt_by_distance(
    ax, trials, *,
    phases=_DEFAULT_PHASES,
    labels=None,
    colors=None,
    distance_col="symbolic_distance",
    group_col="phase", participant_col="participant",
    markers=None, linestyles=None,
    rt_col="rt", rt_scale=1.0,
    correct_only=True, drop_timeouts=True, exclude_col=None,
    show_band=True, band_alpha=0.25,
    show_points=True, point_size=3.0, point_alpha=0.25,
    point_dodge=0.0, jitter_width=0.08, jitter_seed=0,
    marker="o", marker_size=3.5, line_width=None,
    show_chance=False, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel="Symbolic distance", ylabel="Response time (ms)",
    xlim=None, ylim=None, xticks="auto", yticks=None,
    show_legend=True, legend_loc="upper left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
) -> dict:
    """Response time by symbolic distance, one line per series.

    Each participant's median response time (over correct, answered trials by default), then the
    mean and standard error across participants. ``rt_scale`` rescales the values before
    aggregation (0.001 shows milliseconds as seconds). ``exclude_col`` names a boolean column
    without nulls whose true rows are dropped too, such as the response-time outlier flag
    ``rt_trimmed``; the returned statistics then count the rows it drops from those the other
    filters keep.
    """
    if exclude_col is not None and trials[exclude_col].isna().any():
        raise ValueError(f"make_rt_by_distance: {exclude_col} has nulls")
    sub = _rt_frame(trials, rt_col=rt_col, rt_scale=rt_scale, correct_only=correct_only,
                    drop_timeouts=drop_timeouts)
    n_flagged = None
    if exclude_col is not None:
        flag = sub[exclude_col].astype(bool)
        n_flagged = int(flag.sum())
        sub = sub[~flag]
    stats = _make_by_distance(
        ax, sub, fname="make_rt_by_distance",
        value_col=rt_col, agg="median", phases=phases,
        labels=labels, colors=colors, distance_col=distance_col,
        group_col=group_col, participant_col=participant_col,
        markers=markers, linestyles=linestyles,
        show_band=show_band, band_alpha=band_alpha, show_points=show_points,
        point_size=point_size, point_alpha=point_alpha,
        point_dodge=point_dodge, jitter_width=jitter_width,
        jitter_seed=jitter_seed, marker=marker, marker_size=marker_size,
        line_width=line_width, show_chance=show_chance, chance=chance,
        chance_ls=chance_ls, chance_lw=chance_lw, chance_color=chance_color,
        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim, xticks=xticks,
        yticks=yticks, show_legend=show_legend, legend_loc=legend_loc,
        legend_ncol=legend_ncol, legend_title=legend_title,
        legend_fontsize=legend_fontsize, legend_bbox=legend_bbox)
    if exclude_col is not None:
        stats[f"n_rows_dropped_by_{exclude_col}"] = n_flagged
    return stats
