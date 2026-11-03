"""Per-participant panels: one participant's accuracy or response time by symbolic distance, and
the participants' symbolic distance slopes on two tests against each other.

- ``slowest_first``: participant keys ordered from the slowest to the fastest median response
  time.
- ``make_participant_by_distance``: one participant's series on one axes, from the long frames
  of ``summaries.participant_accuracy_by_distance`` and ``participant_rt_by_distance``, each
  point with its band over the participant's own trials.
- ``make_slope_scatter``: one point per participant at their slopes on two tests, with
  whiskers of one bootstrap standard deviation and an optional tinted region.

Nothing is averaged across participants.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.ticker import FixedFormatter, FixedLocator

from geo_alg_ti_humans.plots import _check_in_frame
from geo_alg_ti_humans.plots.style import REFERENCE_LINE_COLOR, TEST_COLORS

_DISTANCES = (1, 2, 3, 4, 5, 6)
# The regions a slope scatter can tint: the open x and y ranges on the two slopes, None
# standing for the drawn limit on that side.
_REGIONS = {
    "lower_right": ((0.0, None), (None, 0.0)),
    "upper_half": ((None, None), (0.0, None)),
}


def _round(value, ndigits=4):
    value = float(value)
    return None if np.isnan(value) else round(value, ndigits)


def _by_distance(distances, values, drawn) -> dict:
    return {int(d): _round(v) for d, v, ok in zip(distances, values, drawn) if ok}


def _within(values: np.ndarray, open_range, tol: float, *, closed: bool = False) -> np.ndarray:
    """True where ``values`` lie inside ``open_range`` by more than ``tol`` (None: no bound on
    that side); with ``closed``, by at least ``tol``, so a negative ``tol`` widens the closed
    range by ``-tol``."""
    lo, hi = open_range
    lo = -np.inf if lo is None else lo
    hi = np.inf if hi is None else hi
    if closed:
        return (values >= lo + tol) & (values <= hi - tol)
    return (values > lo + tol) & (values < hi - tol)


def _drawn(open_range, lim) -> tuple[float, float]:
    """``open_range`` with each missing bound replaced by the drawn limit on that side."""
    return (lim[0] if open_range[0] is None else open_range[0],
            lim[1] if open_range[1] is None else open_range[1])


def slowest_first(median_rt: pd.Series) -> list:
    """The index of ``median_rt`` (participant keys) from the largest to the smallest value.

    Ties keep the participant keys in sorted order. Raises on a missing value.
    """
    if median_rt.isna().any():
        raise ValueError("slowest_first: missing median response times")
    frame = pd.DataFrame({"key": median_rt.index, "value": median_rt.to_numpy(float)})
    frame = frame.sort_values("key", kind="stable").sort_values(
        "value", ascending=False, kind="stable")
    return frame["key"].tolist()


def make_participant_by_distance(
    ax, rows, *,
    series, series_col, colors, offsets=None,
    distance_col="symbolic_distance", distances=_DISTANCES,
    show_band=True, band_alpha=0.25,
    marker="o", marker_size=2.4, line_width=0.9,
    show_chance=False, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlim=(0.5, 6.5), ylim=None, yticks=None, ytick_format="{:g}",
    show_xticklabels=True, show_yticklabels=True,
    xlabel=None, ylabel=None,
) -> dict:
    """One participant's estimate at each symbolic distance, one line per series.

    ``rows`` are the participant's rows of a long frame with the columns ``series_col``,
    ``distance_col``, ``value``, ``low``, ``high`` and ``n_trials``. Each series is drawn at
    its distances plus ``offsets[series]``, with a band from ``low`` to ``high``; a distance
    without a row leaves a gap in the line. Raises if a value falls outside ``ylim``; a band
    reaching past ``ylim`` is cut at the frame and counted. Returns, per series, the values,
    band edges and trial counts by distance, the distances without a value, the number of
    points on a single trial, and the number of bands cut at the frame.
    """
    fname = "make_participant_by_distance"
    offsets = offsets or {}
    stats = {"per_series": {}}
    for s in series:
        sub = rows[rows[series_col] == s].set_index(distance_col)
        if sub.index.duplicated().any():
            raise ValueError(f"{fname}: more than one row per distance in series {s!r}")
        extra = sorted(set(sub.index) - set(distances))
        if extra:
            raise ValueError(f"{fname}: series {s!r} has distances {extra} outside {distances}")
        sub = sub.reindex(list(distances))
        x = np.asarray(distances, dtype=float) + offsets.get(s, 0.0)
        value = sub["value"].to_numpy(float)
        low, high = sub["low"].to_numpy(float), sub["high"].to_numpy(float)
        drawn = ~np.isnan(value)
        n_cut = 0
        if ylim is not None:
            _check_in_frame(value, ylim, axis="y", fname=f"{fname}: series {s!r}")
            lo, hi = min(ylim), max(ylim)
            n_cut = int((drawn & ((low < lo) | (high > hi))).sum())
        if show_band:
            ax.fill_between(x, low, high, color=colors[s], alpha=band_alpha, lw=0, zorder=2)
        ax.plot(x, value, color=colors[s], lw=line_width, marker=marker,
                markersize=marker_size, markeredgewidth=0, zorder=3, clip_on=False)
        n_trials = sub["n_trials"]
        stats["per_series"][s] = {
            "value_by_distance": _by_distance(distances, value, drawn),
            "low_by_distance": _by_distance(distances, low, drawn),
            "high_by_distance": _by_distance(distances, high, drawn),
            "n_trials_by_distance": {int(d): int(n) for d, n in n_trials.dropna().items()},
            "missing_distances": [int(d) for d, ok in zip(distances, drawn) if not ok],
            "n_single_trial_points": int((n_trials == 1).sum()),
            "n_bands_cut_at_frame": n_cut,
        }
    if show_chance:
        ax.axhline(chance, color=chance_color, ls=chance_ls, lw=chance_lw, zorder=1)
    ax.set_xlim(*xlim)
    ax.xaxis.set_major_locator(FixedLocator(list(distances)))
    ax.xaxis.set_major_formatter(FixedFormatter(
        [str(d) for d in distances] if show_xticklabels else [""] * len(distances)))
    if ylim is not None:
        ax.set_ylim(*ylim)
    if yticks is not None:
        ax.yaxis.set_major_locator(FixedLocator(list(yticks)))
        ax.yaxis.set_major_formatter(FixedFormatter(
            [ytick_format.format(t) for t in yticks] if show_yticklabels
            else [""] * len(yticks)))
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    return stats


def make_slope_scatter(
    ax, slopes, *,
    x_col, y_col, x_err_col=None, y_err_col=None,
    shade=None, shade_color=TEST_COLORS["icl"], shade_alpha=0.08,
    point_color="#333333", point_size=12.0, point_alpha=1.0,
    error_color="#333333", error_alpha=0.45, error_lw=0.6,
    show_ref=True, ref_ls="--", ref_lw=0.6, ref_color=REFERENCE_LINE_COLOR,
    xlim, ylim, xticks=None, yticks=None,
    xlabel=None, ylabel=None, title=None, title_weight="bold", square=True,
    edge_tol=1e-9,
) -> dict:
    """One point per participant at two slopes, with whiskers and a tinted region.

    Each row of ``slopes`` is drawn at (``x_col``, ``y_col``) with whiskers of
    ``x_err_col`` / ``y_err_col`` on either side. ``shade`` tints a region of the drawn
    range: "lower_right" (x > 0 and y < 0) or "upper_half" (y > 0). Dashed lines mark zero
    on both axes. Raises on a missing value or a point outside the drawn limits; a whisker
    reaching past them is cut at the frame and counted. A point within ``edge_tol`` of the
    region's boundary, such as a slope that is zero but for rounding, is counted on its edge,
    not inside it. Returns the number of points, the numbers inside the tinted region and on its
    edge, the median, minimum and maximum on each axis, the cut whiskers, and each
    participant's values.
    """
    fname = "make_slope_scatter"
    if edge_tol < 0:
        raise ValueError(f"{fname}: edge_tol must not be negative, not {edge_tol}")
    cols = [c for c in (x_col, y_col, x_err_col, y_err_col) if c is not None]
    if slopes[cols].isna().any().any():
        raise ValueError(f"{fname}: missing values in {cols}")
    x = slopes[x_col].to_numpy(float)
    y = slopes[y_col].to_numpy(float)
    xe = slopes[x_err_col].to_numpy(float) if x_err_col else np.zeros_like(x)
    ye = slopes[y_err_col].to_numpy(float) if y_err_col else np.zeros_like(y)
    _check_in_frame(x, xlim, axis="x", fname=fname)
    _check_in_frame(y, ylim, axis="y", fname=fname)
    (x0, x1), (y0, y1) = sorted(xlim), sorted(ylim)
    stats = {"x_col": x_col, "y_col": y_col, "n": int(len(slopes)), "shade": shade}
    if shade is not None:
        if shade not in _REGIONS:
            raise ValueError(f"{fname}: shade must be one of {sorted(_REGIONS)}, not {shade!r}")
        x_range, y_range = _REGIONS[shade]
        (rx0, rx1), (ry0, ry1) = _drawn(x_range, (x0, x1)), _drawn(y_range, (y0, y1))
        ax.fill_between((rx0, rx1), ry0, ry1, color=shade_color, alpha=shade_alpha, lw=0,
                        zorder=0)
        inside = _within(x, x_range, edge_tol) & _within(y, y_range, edge_tol)
        closed = (_within(x, x_range, -edge_tol, closed=True)
                  & _within(y, y_range, -edge_tol, closed=True))
        stats["n_in_shaded_region"] = int(inside.sum())
        stats["n_on_shaded_region_edge"] = int((closed & ~inside).sum())
    if show_ref:
        ax.axhline(0.0, color=ref_color, ls=ref_ls, lw=ref_lw, zorder=1)
        ax.axvline(0.0, color=ref_color, ls=ref_ls, lw=ref_lw, zorder=1)
    ax.errorbar(x, y, xerr=xe, yerr=ye, fmt="none", ecolor=error_color, alpha=error_alpha,
                elinewidth=error_lw, capsize=0, zorder=2)
    ax.scatter(x, y, s=point_size, color=point_color, alpha=point_alpha, lw=0, zorder=3)
    stats["n_whiskers_cut_at_frame"] = int(
        ((x - xe < x0) | (x + xe > x1) | (y - ye < y0) | (y + ye > y1)).sum())
    for axis, values in (("x", x), ("y", y)):
        stats[f"{axis}_median"] = _round(np.median(values))
        stats[f"{axis}_min"] = _round(values.min())
        stats[f"{axis}_max"] = _round(values.max())
    keys = slopes.index if "participant" not in slopes.columns else slopes["participant"]
    stats["per_participant"] = {
        str(k): {"x": _round(a), "y": _round(b), "x_sd": _round(c), "y_sd": _round(d)}
        for k, a, b, c, d in zip(keys, x, y, xe, ye)}
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    if xticks is not None:
        ax.set_xticks(list(xticks))
    if yticks is not None:
        ax.set_yticks(list(yticks))
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    if title is not None:
        ax.set_title(title, fontweight=title_weight)
    if square:
        ax.set_box_aspect(1)
    return stats
