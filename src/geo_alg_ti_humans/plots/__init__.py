"""Panel functions for the human figures.

Each ``make_<name>(ax, df, **settings)`` draws one panel on ``ax`` and returns a dict of the
statistics it drew. Participant means follow ``summaries.participant_mean_sem``; individual
points are jittered with one seeded generator per call, drawn in the order of series, then
sorted x values, then sorted participant keys. A panel given a fixed ``ylim`` raises if a value
it draws (a mean, a participant's point, a bar) falls outside it; a band or error bar reaching
past it is cut at the frame.
"""

import numpy as np


def _rounded_sem(value):
    """A standard error for the statistics: rounded to 4 places, or None when it is not finite,
    as with a single participant."""
    value = float(value)
    return round(value, 4) if np.isfinite(value) else None


def _rt_frame(df, *, rt_col, rt_scale, correct_only, drop_timeouts):
    """The rows a response-time panel aggregates, with ``rt_col`` rescaled by ``rt_scale``.

    Drops timed-out trials (``drop_timeouts``), incorrect trials (``correct_only``), then rows
    without a response time; 0.001 rescales milliseconds to seconds.
    """
    if rt_col not in df.columns:
        raise KeyError(f"no response-time column {rt_col!r}")
    sub = df
    if drop_timeouts:
        sub = sub[~sub["is_timed_out"].fillna(False).astype(bool)]
    if correct_only:
        sub = sub[sub["is_correct"].astype(bool)]
    sub = sub[sub[rt_col].notna()]
    if rt_scale != 1.0:
        sub = sub.assign(**{rt_col: sub[rt_col] * rt_scale})
    return sub


def _finish_axes(ax, *, xlabel, ylabel, xlim, ylim, xticks, yticks, x_values):
    """Axis labels, ticks and limits; ``xticks="auto"`` puts one tick at each of ``x_values``."""
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if xticks == "auto":
        ax.set_xticks(sorted(x_values))
    elif xticks is not None:
        ax.set_xticks(list(xticks))
    if yticks is not None:
        ax.set_yticks(list(yticks))
    if xlim is not None:
        ax.set_xlim(*xlim)
    if ylim is not None:
        ax.set_ylim(*ylim)


def _legend(ax, handles=None, *, legend_loc, legend_ncol, legend_title, legend_fontsize,
            legend_bbox, legend_frameon=None, legend_framealpha=None, **options):
    """The legend of ``handles`` (None: the labeled artists on ``ax``).

    ``options`` are further ``Axes.legend`` keywords, such as ``handlelength``; options left at
    None keep the style's. A frame (``legend_frameon``) with ``legend_framealpha`` below 1
    keeps a legend readable when no corner is free of data.
    """
    given = {"bbox_to_anchor": legend_bbox, "fontsize": legend_fontsize,
             "frameon": legend_frameon, "framealpha": legend_framealpha, **options}
    ax.legend(handles=handles, loc=legend_loc, ncol=legend_ncol, title=legend_title,
              **{key: value for key, value in given.items() if value is not None})


def _draw_series(ax, x, mean, sem, *, color, label, show_band, band_alpha, marker,
                 marker_size, line_width, line_style, ylim, fname, line_zorder=3,
                 band_zorder=None):
    """One series: the means at ``x`` as a line with markers, under it a band of one standard
    error when ``show_band`` and any standard error is finite.

    Raises if a mean falls outside ``ylim`` (None: the range follows the data); a band reaching
    past it is cut at the frame. ``line_width`` and ``line_style`` None keep the style's;
    ``band_zorder`` None keeps matplotlib's default.
    """
    mean = np.asarray(mean, dtype=float)
    sem = np.asarray(sem, dtype=float)
    _check_in_frame(mean, ylim, axis="y", fname=fname)
    if show_band and np.isfinite(sem).any():
        band = {} if band_zorder is None else {"zorder": band_zorder}
        ax.fill_between(x, mean - sem, mean + sem, color=color, alpha=band_alpha, lw=0, **band)
    line = {key: value for key, value in (("lw", line_width), ("ls", line_style))
            if value is not None}
    ax.plot(x, mean, color=color, marker=marker, markersize=marker_size, label=label,
            zorder=line_zorder, **line)


def _check_in_frame(values, lim, *, axis, fname):
    """Raise if any of ``values`` falls outside the drawn range ``lim`` (None: no check);
    missing values are not drawn and pass."""
    if lim is None:
        return
    values = np.asarray(values, dtype=float)
    lo, hi = min(lim), max(lim)
    bad = int(((values < lo) | (values > hi)).sum())
    if bad:
        raise ValueError(f"{fname}: {bad} points fall outside the drawn {axis} range {lim}")
