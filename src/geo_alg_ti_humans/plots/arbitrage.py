"""Experiment 1 arbitrage-test panels: which ordering a response followed.

On the arbitrage test participants are queried on the trained items while the context shows
the trained ordering reversed, so memory and context imply opposite answers. Every response
follows either the trained ordering or the ordering shown in context, and the two proportions
are exact complements at every distance.

- ``make_outcomes_by_distance``: the two complementary proportions by symbolic distance.
- ``make_rt_by_distance_split``: response time by symbolic distance, split by the ordering the
  response followed.
- ``make_participant_histogram``: a histogram of each participant's own proportion of responses
  that followed the context ordering.

Participants are the only averaged axis: each participant is aggregated first (mean proportion,
or median response time), then the mean and one standard error are taken across participants.
The two by-distance panels draw no per-participant points: the two response classes are exact
complements, so their points would mirror each other, and a participant has few trials at each
distance, so the points would fall on a few values. The histogram shows every participant.

The two columns that record which ordering a response followed are null outside the arbitrage
test, so a bare cast to bool would read every null as false. ``_arbitrage_frame`` drops
timed-out trials, checks the two columns before casting, and checks that exactly one is true per
row and that the trained-ordering response is the one scored as correct.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator

from geo_alg_ti_humans.plots import (
    _check_in_frame,
    _draw_series,
    _finish_axes,
    _legend,
    _rounded_sem,
    _rt_frame,
)
from geo_alg_ti_humans.plots.style import (
    ARBITRAGE_OUTCOME_COLORS,
    ARBITRAGE_OUTCOME_DISPLAY,
    REFERENCE_LINE_COLOR,
    RESPONSE_TIME_LABEL,
    TEST_COLORS,
)
from geo_alg_ti_humans.summaries import participant_mean_sem

_ARBITRAGE_PHASE = "arbitrage_test"
_TRAINED_COL = "is_iwl_consistent"   # the response followed the trained ordering
_CONTEXT_COL = "is_icl_consistent"   # the response followed the ordering shown in context
_DEFAULT_OUTCOMES = (_TRAINED_COL, _CONTEXT_COL)


def _arbitrage_frame(trials, *, phase, fname):
    """The answered arbitrage rows with both response-class columns as float flags.

    A timed-out trial follows neither ordering (both flags are saved false), so it is dropped.
    Raises unless both columns are non-null on every answered arbitrage row (they are null
    elsewhere, so casting without checking would read null as false), exactly one of them is
    true per row, and the trained-ordering flag equals the correctness column.
    """
    sub = trials[trials["phase"] == phase]
    if sub.empty:
        raise ValueError(f"{fname}: no rows for phase {phase!r}")
    for col in (_TRAINED_COL, _CONTEXT_COL, "is_correct", "is_timed_out"):
        if col not in sub.columns:
            raise KeyError(f"{fname}: no column {col!r}")
    sub = sub[~sub["is_timed_out"].fillna(False).astype(bool)]
    if sub.empty:
        raise ValueError(f"{fname}: every {phase!r} trial timed out")
    for col in (_TRAINED_COL, _CONTEXT_COL):
        if sub[col].isna().any():
            raise ValueError(
                f"{fname}: {col!r} is null on {int(sub[col].isna().sum())} of "
                f"{len(sub)} {phase!r} rows; it is null outside the "
                "arbitrage test and a bare cast would read null as false")
    trained = sub[_TRAINED_COL].astype(bool)
    context = sub[_CONTEXT_COL].astype(bool)
    if not (trained ^ context).all():
        raise ValueError(f"{fname}: a {phase!r} response follows both orderings "
                         "or neither")
    if not (trained == sub["is_correct"].astype(bool)).all():
        raise ValueError(f"{fname}: {_TRAINED_COL!r} != 'is_correct' on some "
                         f"{phase!r} rows")
    return sub.assign(**{_TRAINED_COL: trained.astype(float),
                         _CONTEXT_COL: context.astype(float)})


def _series_stats(summary, wide, counts, *, x_col):
    """The drawn points: means, standard errors and counts by x."""
    return {
        "mean_by_x": {int(r[x_col]): round(float(r["value_mean"]), 4)
                      for _, r in summary.iterrows()},
        "sem_by_x": {int(r[x_col]): _rounded_sem(r["value_sem"]) for _, r in summary.iterrows()},
        "n_participants_by_x": {int(r[x_col]): int(r["n_participants"])
                                for _, r in summary.iterrows()},
        "n_trials_by_x": {int(k): int(v) for k, v in counts.items()},
        "n_rows_used": int(sum(int(v) for v in counts.values())),
        "x_values": [int(v) for v in wide.index],
    }


def make_outcomes_by_distance(
    ax, trials, *,
    phase=_ARBITRAGE_PHASE,
    outcomes=_DEFAULT_OUTCOMES,
    colors=None,                # {flag column: color}; None: style.ARBITRAGE_OUTCOME_COLORS
    labels=None,                # {flag column: label}; None: style.ARBITRAGE_OUTCOME_DISPLAY
    distance_col="symbolic_distance", participant_col="participant",
    show_band=True, band_alpha=0.25, point_dodge=0.0,
    marker="o", marker_size=3.5, line_width=None, line_styles=None,
    show_chance=True, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel="Symbolic distance", ylabel="Proportion of responses",
    xlim=None, ylim=(-0.02, 1.02), xticks="auto", yticks=None,
    show_legend=True, legend_loc="upper right", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
) -> dict:
    """Proportion of arbitrage responses that followed each ordering, by symbolic distance.

    One line per entry of ``outcomes``: each participant's mean of that response class's flag
    at each distance, then the mean and one standard error across participants. The two classes
    are exact complements, so their means sum to one at every distance; the returned
    ``max_abs_dev_from_sum_one`` is the check. ``point_dodge`` offsets each series along x; it
    is 0 by default because complementary series are symmetric about chance.
    """
    fname = "make_outcomes_by_distance"
    sub = _arbitrage_frame(trials, phase=phase, fname=fname)
    missing = [c for c in outcomes if c not in sub.columns]
    if missing:
        raise KeyError(f"{fname}: outcome columns {missing} not in frame")
    colors = dict(ARBITRAGE_OUTCOME_COLORS) if colors is None else colors
    labels = dict(ARBITRAGE_OUTCOME_DISPLAY) if labels is None else labels
    line_styles = {} if line_styles is None else line_styles
    counts = sub.groupby(distance_col).size().to_dict()

    per_outcome, all_x = {}, set()
    for i, key in enumerate(outcomes):
        summary, wide = participant_mean_sem(
            sub, x_col=distance_col, value_col=key,
            participant_col=participant_col, agg="mean")
        offset = (i - (len(outcomes) - 1) / 2) * point_dodge
        _draw_series(ax, summary[distance_col].to_numpy(dtype=float) + offset,
                     summary["value_mean"], summary["value_sem"], color=colors[key],
                     label=labels[key], show_band=show_band, band_alpha=band_alpha,
                     band_zorder=2, marker=marker, marker_size=marker_size,
                     line_width=line_width, line_style=line_styles.get(key),
                     ylim=ylim, fname=fname)
        all_x.update(int(v) for v in summary[distance_col])
        per_outcome[key] = _series_stats(summary, wide, counts,
                                         x_col=distance_col)

    if show_chance:
        ax.axhline(chance, color=chance_color, ls=chance_ls, lw=chance_lw,
                   zorder=1)
    _finish_axes(ax, xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                 xticks=xticks, yticks=yticks, x_values=all_x)
    if show_legend:
        _legend(ax, legend_loc=legend_loc, legend_ncol=legend_ncol,
                legend_title=legend_title, legend_fontsize=legend_fontsize,
                legend_bbox=legend_bbox, legend_frameon=legend_frameon,
                legend_framealpha=legend_framealpha)

    xs = sorted(all_x)
    sum_dev = max(abs(sum(per_outcome[k]["mean_by_x"][x] for k in outcomes) - 1.0)
                  for x in xs) if xs else None
    return {
        "phase": phase,
        "outcomes": list(outcomes),
        "per_outcome": per_outcome,
        "max_abs_dev_from_sum_one": (None if sum_dev is None
                                     else round(float(sum_dev), 6)),
        "n_participants": int(sub[participant_col].nunique()),
        "n_trials_by_x": {int(k): int(v) for k, v in counts.items()},
        "n_rows_used": int(len(sub)),
    }


def make_rt_by_distance_split(
    ax, trials, *,
    phase=_ARBITRAGE_PHASE,
    outcome_col=_CONTEXT_COL,
    outcome_values=(False, True),   # draw order: trained ordering, then context ordering
    colors=None,                # {True/False: color}; None: the two outcome colors
    labels=None,                # {True/False: legend label}; None: the two outcome labels
    distance_col="symbolic_distance", participant_col="participant",
    rt_col="rt", rt_scale=0.001,
    show_band=True, band_alpha=0.25, point_dodge=0.0,
    marker="o", marker_size=3.5, line_width=None, line_styles=None,
    show_chance=False, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel="Symbolic distance", ylabel=RESPONSE_TIME_LABEL,
    xlim=None, ylim=(0, 15), xticks="auto", yticks=(0, 5, 10, 15),
    show_legend=True, legend_loc="upper left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
) -> dict:
    """Response time by symbolic distance, split by which ordering the response followed.

    No correctness filter is applied: which ordering the response followed is the split, so
    filtering by correctness would delete one of the two series. Timed-out trials follow
    neither ordering and are dropped, as in every arbitrage panel. Each participant's median
    response time per ordering followed and distance, then the mean and one standard error
    across participants. ``rt_scale`` rescales the values before aggregation (0.001 shows
    milliseconds as seconds). Far fewer participants contribute to the trained-ordering
    series; the returned statistics count them.
    """
    fname = "make_rt_by_distance_split"
    sub = _arbitrage_frame(trials, phase=phase, fname=fname)
    if outcome_col not in sub.columns:
        raise KeyError(f"{fname}: no column {outcome_col!r}")
    # The arbitrage frame holds no timed-out trials.
    sub = _rt_frame(sub, rt_col=rt_col, rt_scale=rt_scale, correct_only=False,
                    drop_timeouts=False)
    if sub.empty:
        raise ValueError(f"{fname}: no response times left after filtering")
    followed_context = sub[outcome_col].astype(bool)
    if colors is None:
        colors = {True: ARBITRAGE_OUTCOME_COLORS[_CONTEXT_COL],
                  False: ARBITRAGE_OUTCOME_COLORS[_TRAINED_COL]}
    if labels is None:
        labels = {True: ARBITRAGE_OUTCOME_DISPLAY[_CONTEXT_COL],
                  False: ARBITRAGE_OUTCOME_DISPLAY[_TRAINED_COL]}
    line_styles = {} if line_styles is None else line_styles

    per_outcome, all_x = {}, set()
    for i, val in enumerate(outcome_values):
        part = sub[followed_context == bool(val)]
        if part.empty:
            raise ValueError(f"{fname}: no rows with {outcome_col}={val}")
        summary, wide = participant_mean_sem(
            part, x_col=distance_col, value_col=rt_col,
            participant_col=participant_col, agg="median")
        offset = (i - (len(outcome_values) - 1) / 2) * point_dodge
        _draw_series(ax, summary[distance_col].to_numpy(dtype=float) + offset,
                     summary["value_mean"], summary["value_sem"], color=colors[val],
                     label=labels[val], show_band=show_band, band_alpha=band_alpha,
                     band_zorder=2, marker=marker, marker_size=marker_size,
                     line_width=line_width, line_style=line_styles.get(val),
                     ylim=ylim, fname=fname)
        all_x.update(int(v) for v in summary[distance_col])
        counts = part.groupby(distance_col).size().to_dict()
        per_outcome[str(bool(val))] = {
            "label": labels[val],
            **_series_stats(summary, wide, counts, x_col=distance_col),
        }

    if show_chance:
        ax.axhline(chance, color=chance_color, ls=chance_ls, lw=chance_lw,
                   zorder=1)
    _finish_axes(ax, xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                 xticks=xticks, yticks=yticks, x_values=all_x)
    if show_legend:
        _legend(ax, legend_loc=legend_loc, legend_ncol=legend_ncol,
                legend_title=legend_title, legend_fontsize=legend_fontsize,
                legend_bbox=legend_bbox, legend_frameon=legend_frameon,
                legend_framealpha=legend_framealpha)

    return {
        "phase": phase,
        "outcome_col": outcome_col,
        "correctness_filter": False,
        "drop_timeouts": True,
        "rt_scale": float(rt_scale),
        "per_outcome": per_outcome,
        "n_participants": int(sub[participant_col].nunique()),
        "n_rows_used": int(len(sub)),
    }


def make_participant_histogram(
    ax, trials, *,
    phase=_ARBITRAGE_PHASE,
    outcome=_CONTEXT_COL,
    participant_col="participant",
    color=None,                 # None: style.TEST_COLORS["icl"]
    bin_width=0.1, bin_lo=0.0, bin_hi=1.0,
    bar_alpha=1.0, bar_edge_color="#ffffff", bar_edge_width=0.6,
    show_chance=True, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    high_threshold=0.9, low_threshold=0.5,
    xlabel="Proportion following context ordering", ylabel="Participants",
    xlim=(-0.02, 1.02), ylim=None, xticks=(0, 0.2, 0.4, 0.6, 0.8, 1.0),
    yticks=None, integer_yticks=True,
) -> dict:
    """Histogram of each participant's proportion of arbitrage responses following ``outcome``.

    One bar per bin of width ``bin_width`` over [``bin_lo``, ``bin_hi``]; a bar's height is the
    number of participants whose own proportion over their answered arbitrage trials falls in
    the bin.
    Bins are right-closed, (a, b] with the lowest bin also closed on the left, because the
    proportions are multiples of 1/40 and several participants sit exactly on a bin edge (0.5,
    0.9, 1.0): a participant at 1.0 counts in the top bin and one at 0.5 in the bin ending at
    chance. The dashed chance line is vertical (the proportion is on the x-axis).
    Nothing drawn is averaged across participants; the returned ``group_mean`` is the mean of
    the participants' proportions.
    """
    fname = "make_participant_histogram"
    sub = _arbitrage_frame(trials, phase=phase, fname=fname)
    if outcome not in sub.columns:
        raise KeyError(f"{fname}: no column {outcome!r}")
    if bin_width <= 0 or bin_hi <= bin_lo:
        raise ValueError(f"{fname}: bad bins (lo {bin_lo}, hi {bin_hi}, "
                         f"width {bin_width})")
    n_bins = int(round((bin_hi - bin_lo) / bin_width))
    if abs(n_bins * bin_width - (bin_hi - bin_lo)) > 1e-9:
        raise ValueError(f"{fname}: bin_width {bin_width} does not tile "
                         f"[{bin_lo}, {bin_hi}]")
    edges = np.linspace(bin_lo, bin_hi, n_bins + 1)

    by_participant = sub.groupby(participant_col)[outcome].mean()
    trials_each = sub.groupby(participant_col).size()
    values = by_participant.to_numpy(dtype=float)
    if ((values < bin_lo) | (values > bin_hi)).any():
        raise ValueError(f"{fname}: a proportion lies outside [{bin_lo}, {bin_hi}]")
    cats = pd.cut(values, bins=edges, right=True, include_lowest=True)
    counts = pd.Series(cats).value_counts(sort=False).to_numpy(dtype=int)
    if int(counts.sum()) != len(values):
        raise ValueError(f"{fname}: binning lost participants "
                         f"({counts.sum()} of {len(values)})")
    _check_in_frame(counts, ylim, axis="y", fname=fname)
    centers = (edges[:-1] + edges[1:]) / 2
    color = TEST_COLORS["icl"] if color is None else color
    group_mean = float(values.mean())

    if show_chance:
        ax.axvline(chance, color=chance_color, ls=chance_ls, lw=chance_lw,
                   zorder=1)
    ax.bar(centers, counts, width=bin_width, align="center", color=color,
           alpha=bar_alpha, edgecolor=bar_edge_color,
           linewidth=bar_edge_width, zorder=2)
    _finish_axes(ax, xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
                 xticks=xticks, yticks=yticks, x_values=set(edges.tolist()))
    if yticks is None and integer_yticks:
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    bin_labels = [f"{lo:g}-{hi:g}" for lo, hi in zip(edges[:-1], edges[1:])]
    order = by_participant.sort_values()
    return {
        "phase": phase,
        "outcome": outcome,
        "bin_edges": [round(float(e), 4) for e in edges],
        "count_by_bin": {lab: int(c) for lab, c in zip(bin_labels, counts)},
        "proportions_sorted": [round(float(v), 4) for v in order.to_numpy()],
        "participants_sorted": [str(p) for p in order.index],
        "n_trials_by_participant": {str(p): int(trials_each[p])
                                    for p in order.index},
        "group_mean": round(group_mean, 4),
        "high_threshold": float(high_threshold),
        "n_at_or_above_high": int((values >= high_threshold).sum()),
        "low_threshold": float(low_threshold),
        "n_at_or_below_low": int((values <= low_threshold).sum()),
        "max_count": int(counts.max()),
        "n_participants": int(len(values)),
        "n_rows_used": int(len(sub)),
    }
