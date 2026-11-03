"""Experiment 1 learning-phase panels: accuracy and response time over learning trials.

Two panels per x-axis:

- ``make_accuracy_by_bin`` / ``make_rt_by_bin``: the measure in fixed-width bins of learning
  trials, one series per context display (shown or masked). On masked trials the answer can
  come only from memory, so the two series show whether the context or memory carries the
  answer at each point in learning.
- ``make_accuracy_by_distractors`` / ``make_rt_by_distractors``: the measure against the number
  of intervening distractors (0, 1 or 2 items placed between the two queried items in the
  displayed context), one series per half of the learning phase. The number is undefined when
  the context was masked, so these panels read context-shown trials only.

Each participant is aggregated first (mean accuracy, or the median response time of their
correct, answered trials), then the mean and one standard error are taken across participants.
A masked bin holds one to six trials per participant, so per-participant points would fall on a
few values; the panels do not draw them.

A trial's position in the learning phase is counted within each participant over all learning
trials, before any split by context display, so the masked trials keep their true positions.
"""

from __future__ import annotations

import numpy as np

from geo_alg_ti_humans.plots import (
    _draw_series,
    _finish_axes,
    _legend,
    _rounded_sem,
    _rt_frame,
)
from geo_alg_ti_humans.plots.style import (
    INTERVENING_DISTRACTORS_LABEL,
    LEARNING_DISPLAY_COLORS,
    LEARNING_DISPLAY_LABELS,
    LEARNING_DISPLAY_ORDER,
    LEARNING_HALF_LABEL,
    LEARNING_HALF_LS,
    LEARNING_HALF_MARKER,
    LEARNING_HALF_ORDER,
    REFERENCE_LINE_COLOR,
    RESPONSE_TIME_LABEL,
    TRIAL_AXIS_LABEL,
)
from geo_alg_ti_humans.summaries import participant_mean_sem

# Columns and values the learning phase is read from; facts of the data, not drawing choices.
_PHASE_COL = "phase"
_LEARNING_PHASE = "learning"
_TRIAL_INDEX_COL = "trial_index"
_DISTANCE_COL = "symbolic_distance"
_ADJACENT_DISTANCE = 1        # every learning query compares adjacent items
_CORRECT_COL = "is_correct"   # false on timeouts, so accuracy counts them as incorrect
_POSITION_COL = "_position"   # 0..n-1 within participant, added by _learning_position
_SHOWN_MODE = LEARNING_DISPLAY_ORDER[0]   # "shown": the context was displayed
_EXPECTED_DISTRACTORS = (0, 1, 2)


# Data preparation

def _learning_position(trials, *, participant_col):
    """The learning-phase rows with each trial's position within its participant.

    Checks that every learning query compares adjacent items and that ``trial_index``
    strictly increases within every participant, then adds ``_POSITION_COL`` as a cumulative
    count within participant over all learning rows, before any split by context display.
    """
    for col in (_PHASE_COL, _TRIAL_INDEX_COL, _DISTANCE_COL, participant_col):
        if col not in trials.columns:
            raise KeyError(f"_learning_position: no column {col!r} "
                           f"(have {list(trials.columns)})")
    learn = trials[trials[_PHASE_COL] == _LEARNING_PHASE]
    if learn.empty:
        raise ValueError(f"_learning_position: no rows with "
                         f"{_PHASE_COL} == {_LEARNING_PHASE!r}")
    if not (learn[_DISTANCE_COL] == _ADJACENT_DISTANCE).all():
        raise ValueError("_learning_position: a learning query does not compare "
                         f"adjacent items ({_DISTANCE_COL} != {_ADJACENT_DISTANCE})")
    if not learn.groupby(participant_col)[_TRIAL_INDEX_COL].apply(
            lambda s: s.is_monotonic_increasing and s.is_unique).all():
        raise ValueError(f"_learning_position: {_TRIAL_INDEX_COL} is not "
                         "strictly increasing within every participant, so the "
                         "cumulative position would be meaningless")
    learn = learn.copy()
    learn[_POSITION_COL] = learn.groupby(participant_col).cumcount()
    return learn


def _assert_full_phase(learn, *, participant_col, n_trials):
    counts = sorted(learn.groupby(participant_col).size().unique().tolist())
    if counts != [n_trials]:
        raise ValueError(f"learning: learning trials per participant "
                         f"{counts} != [{n_trials}]")


# Drawing

def _finish(ax, *, show_chance, chance, chance_ls, chance_lw, chance_color, show_legend,
            legend_loc, legend_ncol, legend_title, legend_fontsize, legend_bbox,
            legend_frameon, legend_framealpha, **axes):
    """The chance line, the axes (``plots._finish_axes``) and the legend."""
    if show_chance:
        ax.axhline(chance, color=chance_color, ls=chance_ls, lw=chance_lw, zorder=1)
    _finish_axes(ax, **axes)
    if show_legend:
        _legend(ax, legend_loc=legend_loc, legend_ncol=legend_ncol, legend_title=legend_title,
                legend_fontsize=legend_fontsize, legend_bbox=legend_bbox,
                legend_frameon=legend_frameon, legend_framealpha=legend_framealpha)


def _x_key(x):
    """The statistics key of a drawn x value: an int when it is whole (the bin center 10, or 0
    distractors), else the float (the center 12.5 of a 25-trial bin)."""
    x = float(x)
    return int(x) if x.is_integer() else x


def _series_stats(summary, x_col, x_of, counts, min_participants, what):
    mean_by_x, sem_by_x, n_p_by_x = {}, {}, {}
    for _, row in summary.iterrows():
        key = _x_key(x_of(row[x_col]))
        mean_by_x[key] = round(float(row["value_mean"]), 4)
        sem_by_x[key] = _rounded_sem(row["value_sem"])
        n_p = int(row["n_participants"])
        if n_p < min_participants:
            raise ValueError(f"learning: {what} at x={key} has {n_p} "
                             f"participants (< min_participants="
                             f"{min_participants})")
        n_p_by_x[key] = n_p
    return {
        "mean_by_x": mean_by_x,
        "sem_by_x": sem_by_x,
        "n_participants_by_x": n_p_by_x,
        "n_trials_by_x": {_x_key(x_of(k)): int(v) for k, v in counts.items()},
    }


# Binned learning curves, one series per context display

def _make_by_bin(ax, trials, *, fname, value_col, agg, modes, labels, colors,
                 mode_col, bin_width, n_trials, min_participants,
                 participant_col, prepare, show_band, band_alpha, point_dodge,
                 marker, marker_size, line_style, line_width,
                 show_chance, chance, chance_ls, chance_lw, chance_color,
                 xlabel, ylabel, xlim, ylim, xticks, yticks, show_legend,
                 legend_loc, legend_ncol, legend_title, legend_fontsize,
                 legend_bbox, legend_frameon, legend_framealpha):
    if n_trials % bin_width:
        raise ValueError(f"learning: bin_width={bin_width} does not "
                         f"divide n_trials={n_trials}")
    n_bins = n_trials // bin_width
    expected_bins = set(range(n_bins))
    colors = {**LEARNING_DISPLAY_COLORS, **(colors or {})}
    labels = {**LEARNING_DISPLAY_LABELS, **(labels or {})}

    learn = _learning_position(trials, participant_col=participant_col)
    _assert_full_phase(learn, participant_col=participant_col,
                       n_trials=n_trials)
    if mode_col not in learn.columns:
        raise KeyError(f"learning: no context-display column {mode_col!r}")
    learn = learn.assign(_bin=learn[_POSITION_COL] // bin_width)
    prepared = prepare(learn)

    # A bin is drawn at its center, so a point sits over the trials it summarizes and the ticks
    # can mark the bin edges.
    def x_of(b):
        return int(b) * bin_width + bin_width / 2.0

    stats = {"bin_width": int(bin_width), "n_bins": int(n_bins),
             "n_trials": int(n_trials),
             "bin_edges": [int(i * bin_width) for i in range(n_bins + 1)],
             "bin_centers": [_x_key(x_of(b)) for b in range(n_bins)],
             "n_rows_used": 0, "per_mode": {}}
    for i, mode in enumerate(modes):
        sub = prepared[prepared[mode_col] == mode]
        if sub.empty:
            raise ValueError(f"learning: no rows for {mode_col}="
                             f"{mode!r} (have "
                             f"{sorted(prepared[mode_col].unique())})")
        got = set(int(b) for b in sub["_bin"].unique())
        if got != expected_bins:
            raise ValueError(f"learning: {mode!r} covers bins "
                             f"{sorted(got)} != {sorted(expected_bins)}")
        summary, _ = participant_mean_sem(
            sub, x_col="_bin", value_col=value_col, agg=agg,
            participant_col=participant_col)
        offset = (i - (len(modes) - 1) / 2.0) * point_dodge
        x = np.array([x_of(b) for b in summary["_bin"]], dtype=float) + offset
        _draw_series(ax, x, summary["value_mean"], summary["value_sem"],
                     color=colors[mode], label=labels[mode], show_band=show_band,
                     band_alpha=band_alpha, marker=marker, marker_size=marker_size,
                     line_width=line_width, line_style=line_style, ylim=ylim,
                     fname=fname, line_zorder=3 + i, band_zorder=2 + i)
        stats["n_rows_used"] += int(len(sub))
        stats["per_mode"][mode] = {
            "label": labels[mode],
            "n_rows_used": int(len(sub)),
            **_series_stats(summary, "_bin", x_of,
                            sub.groupby("_bin").size().to_dict(),
                            min_participants, f"{mode!r}"),
        }
    _finish(ax, xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
            xticks=xticks, yticks=yticks, x_values=[x_of(b) for b in range(n_bins)],
            show_chance=show_chance, chance=chance, chance_ls=chance_ls,
            chance_lw=chance_lw, chance_color=chance_color, show_legend=show_legend,
            legend_loc=legend_loc, legend_ncol=legend_ncol,
            legend_title=legend_title, legend_fontsize=legend_fontsize,
            legend_bbox=legend_bbox, legend_frameon=legend_frameon,
            legend_framealpha=legend_framealpha)
    return stats


def make_accuracy_by_bin(
    ax, trials, *,
    modes=LEARNING_DISPLAY_ORDER,
    labels=None,                  # None: style.LEARNING_DISPLAY_LABELS
    colors=None,                  # None: style.LEARNING_DISPLAY_COLORS
    mode_col="context_display",
    bin_width=20, n_trials=100, min_participants=2,
    show_band=True, band_alpha=0.25, point_dodge=0.0,
    marker="o", marker_size=3.5, line_style="-", line_width=None,
    show_chance=True, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel=TRIAL_AXIS_LABEL, ylabel="Accuracy",
    xlim=None, ylim=(-0.02, 1.02), xticks=None, yticks=None,
    show_legend=True, legend_loc="lower right", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
    participant_col="participant",
) -> dict:
    """Accuracy in ``bin_width``-trial bins of the learning phase, one line per context display.

    Positions are counted over all ``n_trials`` learning trials before the split by display, so
    masked trials keep their true positions; each series must cover every bin, and no point may
    rest on fewer than ``min_participants`` participants. Points are drawn at bin centers (10,
    30, ... for 20-trial bins); pass ``xticks`` at the bin edges. Timeouts count as incorrect.
    """
    return _make_by_bin(
        ax, trials, fname="make_accuracy_by_bin",
        value_col=_CORRECT_COL, agg="mean", modes=modes,
        labels=labels, colors=colors, mode_col=mode_col, bin_width=bin_width,
        n_trials=n_trials, min_participants=min_participants,
        participant_col=participant_col, prepare=lambda df: df,
        show_band=show_band, band_alpha=band_alpha, point_dodge=point_dodge,
        marker=marker, marker_size=marker_size,
        line_style=line_style, line_width=line_width,
        show_chance=show_chance, chance=chance,
        chance_ls=chance_ls, chance_lw=chance_lw, chance_color=chance_color,
        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim, xticks=xticks,
        yticks=yticks, show_legend=show_legend, legend_loc=legend_loc,
        legend_ncol=legend_ncol, legend_title=legend_title,
        legend_fontsize=legend_fontsize, legend_bbox=legend_bbox,
        legend_frameon=legend_frameon, legend_framealpha=legend_framealpha)


def make_rt_by_bin(
    ax, trials, *,
    modes=LEARNING_DISPLAY_ORDER,
    labels=None,
    colors=None,
    mode_col="context_display",
    bin_width=20, n_trials=100, min_participants=2,
    rt_col="rt", rt_scale=0.001, correct_only=True, drop_timeouts=True,
    show_band=True, band_alpha=0.25, point_dodge=0.0,
    marker="o", marker_size=3.5, line_style="-", line_width=None,
    show_chance=False, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel=TRIAL_AXIS_LABEL, ylabel=RESPONSE_TIME_LABEL,
    xlim=None, ylim=None, xticks=None, yticks=None,
    show_legend=True, legend_loc="upper right", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
    participant_col="participant",
) -> dict:
    """Response time in ``bin_width``-trial bins of the learning phase, one line per display.

    Each participant's median over their correct, answered trials in the bin, then the mean
    and one standard error across participants. ``rt_scale`` rescales the values before
    aggregation (0.001 shows milliseconds as seconds). Bins are assigned before the
    response-time filters, so dropping a trial never shifts another trial's position.
    """
    return _make_by_bin(
        ax, trials, fname="make_rt_by_bin",
        value_col=rt_col, agg="median", modes=modes,
        labels=labels, colors=colors, mode_col=mode_col, bin_width=bin_width,
        n_trials=n_trials, min_participants=min_participants,
        participant_col=participant_col,
        prepare=lambda df: _rt_frame(
            df, rt_col=rt_col, rt_scale=rt_scale, correct_only=correct_only,
            drop_timeouts=drop_timeouts),
        show_band=show_band, band_alpha=band_alpha, point_dodge=point_dodge,
        marker=marker, marker_size=marker_size,
        line_style=line_style, line_width=line_width,
        show_chance=show_chance, chance=chance,
        chance_ls=chance_ls, chance_lw=chance_lw, chance_color=chance_color,
        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim, xticks=xticks,
        yticks=yticks, show_legend=show_legend, legend_loc=legend_loc,
        legend_ncol=legend_ncol, legend_title=legend_title,
        legend_fontsize=legend_fontsize, legend_bbox=legend_bbox,
        legend_frameon=legend_frameon, legend_framealpha=legend_framealpha)


# By intervening distractors, one series per half of the learning phase

def _make_by_distractors(ax, trials, *, fname, value_col, agg, split_at,
                         split_values, labels, color, line_styles, markers,
                         distractors_col, mode_col, shown_mode,
                         min_participants, participant_col, prepare, n_trials,
                         show_band, band_alpha, point_dodge, marker_size,
                         line_width, show_chance, chance, chance_ls, chance_lw,
                         chance_color, xlabel, ylabel,
                         xlim, ylim, xticks, yticks, show_legend, legend_loc,
                         legend_ncol, legend_title, legend_fontsize,
                         legend_bbox, legend_frameon, legend_framealpha):
    if len(split_values) != 2:
        raise ValueError(f"learning: split_values={split_values!r} "
                         "must name exactly two halves")
    color = LEARNING_DISPLAY_COLORS[shown_mode] if color is None else color
    first, second = split_values
    labels = {first: LEARNING_HALF_LABEL.format(first=1, last=split_at),
              second: LEARNING_HALF_LABEL.format(first=split_at + 1, last=n_trials),
              **(labels or {})}
    # The style's line styles and markers go to the two halves in order, whatever their names.
    defaults = dict(zip(split_values, LEARNING_HALF_ORDER))
    line_styles = {**{h: LEARNING_HALF_LS[d] for h, d in defaults.items()}, **(line_styles or {})}
    markers = {**{h: LEARNING_HALF_MARKER[d] for h, d in defaults.items()}, **(markers or {})}

    learn = _learning_position(trials, participant_col=participant_col)
    _assert_full_phase(learn, participant_col=participant_col,
                       n_trials=n_trials)
    for col in (distractors_col, mode_col):
        if col not in learn.columns:
            raise KeyError(f"learning: no column {col!r}")
    shown = learn[learn[mode_col] == shown_mode]
    n_excluded = int(len(learn) - len(shown))
    if shown.empty:
        raise ValueError(f"learning: no rows with {mode_col}="
                         f"{shown_mode!r}")
    # Undefined when the context was masked; on context-shown trials it must be 0, 1 or 2.
    if shown[distractors_col].isna().any():
        raise ValueError(f"learning: {distractors_col} is null on a "
                         "context-shown learning trial")
    got = set(int(v) for v in shown[distractors_col].unique())
    if not got <= set(_EXPECTED_DISTRACTORS):
        raise ValueError(f"learning: {distractors_col} values {sorted(got)} "
                         f"outside {list(_EXPECTED_DISTRACTORS)}")
    shown = shown.assign(
        _distractors=shown[distractors_col].astype(int),
        _half=np.where(shown[_POSITION_COL] < split_at, split_values[0],
                       split_values[1]))
    prepared = prepare(shown)

    stats = {"split_at": int(split_at), "n_trials": int(n_trials),
             "n_masked_rows_excluded": n_excluded,
             "n_rows_used": 0, "per_half": {}}
    for i, half in enumerate(split_values):
        sub = prepared[prepared["_half"] == half]
        if sub.empty:
            raise ValueError(f"learning: no rows in half {half!r}")
        summary, _ = participant_mean_sem(
            sub, x_col="_distractors", value_col=value_col, agg=agg,
            participant_col=participant_col)
        offset = (i - (len(split_values) - 1) / 2.0) * point_dodge
        x = summary["_distractors"].to_numpy(dtype=float) + offset
        _draw_series(ax, x, summary["value_mean"], summary["value_sem"],
                     color=color, label=labels[half], show_band=show_band,
                     band_alpha=band_alpha, marker=markers[half], marker_size=marker_size,
                     line_width=line_width, line_style=line_styles[half], ylim=ylim,
                     fname=fname, line_zorder=3 + i, band_zorder=2 + i)
        stats["n_rows_used"] += int(len(sub))
        stats["per_half"][half] = {
            "label": labels[half],
            "n_rows_used": int(len(sub)),
            **_series_stats(summary, "_distractors", float,
                            sub.groupby("_distractors").size().to_dict(),
                            min_participants, f"half {half!r}"),
        }
    _finish(ax, xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim,
            xticks=xticks, yticks=yticks, x_values=sorted(got),
            show_chance=show_chance, chance=chance, chance_ls=chance_ls,
            chance_lw=chance_lw, chance_color=chance_color, show_legend=show_legend,
            legend_loc=legend_loc, legend_ncol=legend_ncol,
            legend_title=legend_title, legend_fontsize=legend_fontsize,
            legend_bbox=legend_bbox, legend_frameon=legend_frameon,
            legend_framealpha=legend_framealpha)
    return stats


def make_accuracy_by_distractors(
    ax, trials, *,
    split_at=50, split_values=LEARNING_HALF_ORDER,
    labels=None,                  # None: each half's trials, "Trials 1–50" and "Trials 51–100"
    color=None,                   # None: style.LEARNING_DISPLAY_COLORS["shown"]
    line_styles=None,             # None: style.LEARNING_HALF_LS, in the order of split_values
    markers=None,                 # None: style.LEARNING_HALF_MARKER, in the same order
    distractors_col="intervening_distractors",
    mode_col="context_display", shown_mode=_SHOWN_MODE,
    n_trials=100, min_participants=2,
    show_band=True, band_alpha=0.25, point_dodge=0.0,
    marker_size=3.5, line_width=None,
    show_chance=True, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel=INTERVENING_DISTRACTORS_LABEL, ylabel="Accuracy",
    xlim=None, ylim=(-0.02, 1.02), xticks=(0, 1, 2), yticks=None,
    show_legend=True, legend_loc="lower left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
    participant_col="participant",
) -> dict:
    """Accuracy against the number of intervening distractors, one line per learning half.

    Context-shown trials only; the halves split at trial position ``split_at``. Both halves
    share one color and are told apart by line style and marker. Timeouts count as incorrect.
    """
    return _make_by_distractors(
        ax, trials, fname="make_accuracy_by_distractors",
        value_col=_CORRECT_COL, agg="mean", split_at=split_at,
        split_values=split_values, labels=labels, color=color,
        line_styles=line_styles, markers=markers,
        distractors_col=distractors_col, mode_col=mode_col,
        shown_mode=shown_mode, min_participants=min_participants,
        participant_col=participant_col, prepare=lambda df: df,
        n_trials=n_trials, show_band=show_band,
        band_alpha=band_alpha, point_dodge=point_dodge, marker_size=marker_size,
        line_width=line_width, show_chance=show_chance, chance=chance,
        chance_ls=chance_ls, chance_lw=chance_lw, chance_color=chance_color,
        xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim, xticks=xticks,
        yticks=yticks, show_legend=show_legend, legend_loc=legend_loc,
        legend_ncol=legend_ncol, legend_title=legend_title,
        legend_fontsize=legend_fontsize, legend_bbox=legend_bbox,
        legend_frameon=legend_frameon, legend_framealpha=legend_framealpha)


def make_rt_by_distractors(
    ax, trials, *,
    split_at=50, split_values=LEARNING_HALF_ORDER,
    labels=None,
    color=None,
    line_styles=None,
    markers=None,
    distractors_col="intervening_distractors",
    mode_col="context_display", shown_mode=_SHOWN_MODE,
    n_trials=100, min_participants=2,
    rt_col="rt", rt_scale=0.001, correct_only=True, drop_timeouts=True,
    show_band=True, band_alpha=0.25, point_dodge=0.0,
    marker_size=3.5, line_width=None,
    show_chance=False, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel=INTERVENING_DISTRACTORS_LABEL, ylabel=RESPONSE_TIME_LABEL,
    xlim=None, ylim=None, xticks=(0, 1, 2), yticks=None,
    show_legend=True, legend_loc="upper left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
    participant_col="participant",
) -> dict:
    """Response time against the number of intervening distractors, one line per learning half.

    Context-shown trials only; each participant's median over their correct, answered trials,
    then the mean and one standard error across participants. ``rt_scale`` rescales the values
    before aggregation. The half is assigned from the trial's position before the response-time
    filters.
    """
    return _make_by_distractors(
        ax, trials, fname="make_rt_by_distractors",
        value_col=rt_col, agg="median", split_at=split_at,
        split_values=split_values, labels=labels, color=color,
        line_styles=line_styles, markers=markers,
        distractors_col=distractors_col, mode_col=mode_col,
        shown_mode=shown_mode, min_participants=min_participants,
        participant_col=participant_col,
        prepare=lambda df: _rt_frame(
            df, rt_col=rt_col, rt_scale=rt_scale, correct_only=correct_only,
            drop_timeouts=drop_timeouts),
        n_trials=n_trials, show_band=show_band, band_alpha=band_alpha,
        point_dodge=point_dodge, marker_size=marker_size, line_width=line_width,
        show_chance=show_chance, chance=chance, chance_ls=chance_ls,
        chance_lw=chance_lw, chance_color=chance_color, xlabel=xlabel,
        ylabel=ylabel, xlim=xlim, ylim=ylim, xticks=xticks, yticks=yticks,
        show_legend=show_legend, legend_loc=legend_loc,
        legend_ncol=legend_ncol, legend_title=legend_title,
        legend_fontsize=legend_fontsize, legend_bbox=legend_bbox,
        legend_frameon=legend_frameon, legend_framealpha=legend_framealpha)
