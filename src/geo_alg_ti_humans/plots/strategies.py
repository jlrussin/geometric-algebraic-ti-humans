"""Experiment 2 strategy panels: questionnaire answers and per-participant response times.

After the main questions, Experiment 2 asked how many of the statements had been true of the
real world and how often the participant had answered from real-world knowledge instead of the
statements. This module draws those answers beside each participant's response-time measures
(``summaries.participant_rt_measures``):

- ``answer_counts`` / ``median_answer`` / ``attach_answers`` / ``gray_ramp``: counts of each
  answer per condition, the median answer on the ordered scale, a checked join of one
  questionnaire item onto the measures, and the light-to-dark gray ramp for ordered answers.
- ``make_answer_bars``: one 100%-stacked horizontal bar per condition, the ordered answers as a
  gray ramp (lightest = first option) and each off-scale answer ("I don't know") white with a
  gray hatch, drawn last.
- ``make_participant_scatter``: one point per participant on two measures, colored by
  condition, with a dashed reference line.
- ``make_category_violins``: one violin (matplotlib's kernel density estimate) per condition and
  ordered category, conditions dodged left and right within each category, with every
  participant drawn as a point jittered by a seeded generator and the median marked.

Nothing is averaged across participants: every point is one participant, and the conditions
are never pooled.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch
from matplotlib.ticker import FixedFormatter, FixedLocator, NullLocator

from geo_alg_ti_humans.plots import _check_in_frame, _legend
from geo_alg_ti_humans.plots.style import CONTEXT_COLORS, CONTEXT_LABELS, REFERENCE_LINE_COLOR
from geo_alg_ti_humans.summaries import spearman_rho

_DEFAULT_CONDITIONS = ("congruent", "shuffled")
_DEFAULT_COLORS = {c: CONTEXT_COLORS[c] for c in _DEFAULT_CONDITIONS}
_DEFAULT_LABELS = {c: CONTEXT_LABELS[c] for c in _DEFAULT_CONDITIONS}


def _round(value, ndigits=4):
    value = float(value)
    return None if np.isnan(value) else round(value, ndigits)


# Pure helpers

def answer_counts(responses: pd.DataFrame, *, item: str, options,
                  conditions=_DEFAULT_CONDITIONS,
                  condition_col="condition") -> dict:
    """Per condition, the count of each answer option to the questionnaire ``item``.

    Also ``n_answered`` (participants who chose one of ``options``), ``n_skipped`` (missing
    answers) and ``n_participants``. An answer outside ``options`` raises rather than being
    dropped.
    """
    fname = "answer_counts"
    out = {}
    for cond in conditions:
        group = responses[responses[condition_col] == cond]
        if group.empty:
            raise ValueError(f"{fname}: no participants in condition {cond!r}")
        values = group[item]
        answered = values[values.notna()].astype(str)
        stray = sorted(set(answered) - set(options))
        if stray:
            raise ValueError(f"{fname}: {item} has answers outside the options: {stray}")
        out[cond] = {
            "counts": {o: int((answered == o).sum()) for o in options},
            "n_answered": int(len(answered)),
            "n_skipped": int(values.isna().sum()),
            "n_participants": int(len(group)),
        }
    return out


def median_answer(counts: dict, scale) -> str | None:
    """The median answer on the ordered ``scale``.

    Off-scale answers are left out. The middle answer, or "<lower> to <upper>" when an even
    number of answers splits between two options; None without answers.
    """
    codes = np.repeat(np.arange(len(scale)), [counts[o] for o in scale])
    if len(codes) == 0:
        return None
    lo = scale[int(codes[(len(codes) - 1) // 2])]
    hi = scale[int(codes[len(codes) // 2])]
    return lo if lo == hi else f"{lo} to {hi}"


def gray_ramp(n: int, *, light: float, dark: float) -> list[str]:
    """``n`` grays from ``light`` (first) to ``dark`` (last).

    Levels are fractions of white (1.0 = white, 0.0 = black).
    """
    if n < 1:
        raise ValueError(f"gray_ramp: n must be at least 1, not {n}")
    levels = np.linspace(light, dark, n) if n > 1 else [(light + dark) / 2]
    return ["#%02x%02x%02x" % ((round(v * 255),) * 3) for v in levels]


def attach_answers(measures: pd.DataFrame, responses: pd.DataFrame, *,
                   item: str, participant_col="participant",
                   condition_col="condition") -> pd.DataFrame:
    """``measures`` with the answer to ``item`` joined by participant.

    Raises unless both frames hold the same participants, each once, with the same condition.
    """
    fname = "attach_answers"
    for name, frame in (("measures", measures), ("responses", responses)):
        if frame[participant_col].duplicated().any():
            raise ValueError(f"{fname}: duplicate participants in {name}")
    if set(measures[participant_col]) != set(responses[participant_col]):
        raise ValueError(f"{fname}: measures and responses hold different participants")
    merged = measures.merge(
        responses[[participant_col, condition_col, item]],
        on=participant_col, how="left", suffixes=("", "_responses"),
        validate="one_to_one")
    if (merged[condition_col] != merged[f"{condition_col}_responses"]).any():
        raise ValueError(f"{fname}: conditions disagree between the two frames")
    return merged.drop(columns=[f"{condition_col}_responses"])


# Panels

def _row_major(items: list, ncol: int) -> list:
    """Legend entries reordered so ``ncol`` columns, filled column by column, read row by row."""
    nrows = math.ceil(len(items) / max(1, ncol))
    return [items[r * ncol + c] for c in range(ncol) for r in range(nrows)
            if r * ncol + c < len(items)]


def make_answer_bars(
    ax, responses, *,
    item, options,
    off_scale=("I don't know",),
    conditions=_DEFAULT_CONDITIONS, condition_col="condition",
    condition_labels=None,
    option_labels=None,
    ramp_light=0.88, ramp_dark=0.12,
    off_face="#ffffff", off_hatch_color=REFERENCE_LINE_COLOR, off_hatch="////",
    hatch_lw=0.5,
    seg_edge="#ffffff", seg_lw=0.4,
    bar_height=0.6,
    tick_label="{name} (n = {n})",
    xlabel="Participants (%)", xlim=(0, 100), xticks=(0, 25, 50, 75, 100),
    ylim=None,
    show_legend=True, legend_title=None, legend_loc="upper left",
    legend_bbox=None, legend_ncol=2, legend_fontsize=None,
    legend_title_fontsize=None, legend_frameon=None,
    legend_alignment="left", legend_handlelength=1.4,
    legend_handleheight=1.0, legend_columnspacing=1.0,
    legend_handletextpad=None, legend_borderaxespad=None,
    legend_row_major=True,
) -> dict:
    """One 100%-stacked horizontal bar of questionnaire answers per condition, first on top.

    Shares are of the participants who answered the item (``n`` in the tick label); skipped
    answers are left out of the denominator, off-scale answers stay in it. Segments follow
    ``options`` in order: the ordered options (``options`` minus ``off_scale``) as a gray ramp
    from ``ramp_light`` to ``ramp_dark``, then each off-scale option white with a hatch in
    ``off_hatch_color``. Every segment is outlined in ``seg_edge`` at ``seg_lw``, so all
    segments have the same height; the legend patches use the same styles. ``ylim`` is in data
    units with the first condition at y = 0 and the axis inverted (``(bottom, top)``; for
    example ``(1.5, -1.6)`` leaves room above the bars for the legend); None shows the bars
    alone. The legend lists every option in order, read left to right row by row when
    ``legend_row_major`` (otherwise down each column).
    """
    fname = "make_answer_bars"
    options = list(options)
    missing = [o for o in off_scale if o not in options]
    if missing:
        raise ValueError(f"{fname}: off-scale options not among the options: {missing}")
    scale = [o for o in options if o not in off_scale]
    drawn = [*scale, *[o for o in options if o in off_scale]]
    colors = dict(zip(scale, gray_ramp(len(scale), light=ramp_light, dark=ramp_dark)))
    condition_labels = {**_DEFAULT_LABELS, **(condition_labels or {})}
    option_labels = option_labels or {}
    counts = answer_counts(responses, item=item, options=options,
                           conditions=conditions, condition_col=condition_col)

    def _style(o):
        if o in colors:
            return dict(facecolor=colors[o], edgecolor=seg_edge, linewidth=seg_lw)
        return dict(facecolor=off_face, edgecolor=seg_edge, hatch=off_hatch,
                    hatchcolor=off_hatch_color, hatch_linewidth=hatch_lw,
                    linewidth=seg_lw)

    for y, cond in enumerate(conditions):
        c = counts[cond]
        if c["n_answered"] == 0:
            raise ValueError(f"{fname}: nobody in {cond!r} answered {item}")
        left = 0.0
        c["percent"] = {}
        for o in drawn:
            share = 100.0 * c["counts"][o] / c["n_answered"]
            c["percent"][o] = round(share, 2)
            if share > 0:
                ax.barh(y, share, left=left, height=bar_height, **_style(o))
            left += share
        c["median_answer"] = median_answer(c["counts"], scale)
    ax.set_yticks(range(len(conditions)))
    ax.set_yticklabels([tick_label.format(name=condition_labels[c],
                                          n=counts[c]["n_answered"])
                        for c in conditions])
    ax.set_ylim(*(ylim if ylim is not None else (len(conditions) - 0.5, -0.5)))
    ax.set_xlim(*xlim)
    if xticks is not None:
        ax.set_xticks(list(xticks))
    ax.set_xlabel(xlabel)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    if show_legend:
        handles = [Patch(label=option_labels.get(o, o), **_style(o)) for o in drawn]
        if legend_row_major:
            handles = _row_major(handles, legend_ncol)
        _legend(ax, handles, legend_loc=legend_loc, legend_bbox=legend_bbox,
                legend_ncol=legend_ncol, legend_title=legend_title,
                legend_fontsize=legend_fontsize, legend_frameon=legend_frameon,
                title_fontsize=legend_title_fontsize, alignment=legend_alignment,
                handlelength=legend_handlelength, handleheight=legend_handleheight,
                columnspacing=legend_columnspacing, handletextpad=legend_handletextpad,
                borderaxespad=legend_borderaxespad)
    return {"item": item, "options": drawn, "off_scale": list(off_scale),
            "by_condition": counts}


def _scatter_kw(*, color, point_size, point_alpha, point_edge_color,
                point_edge_width, marker, label, rasterized):
    return dict(s=point_size, color=color, alpha=point_alpha,
                edgecolors=point_edge_color, linewidths=point_edge_width,
                marker=marker, label=label, zorder=3, rasterized=rasterized)


def make_participant_scatter(
    ax, measures, *,
    x_col="median_rt_s", y_col="rt_slope_pct",
    group_col="condition", groups=_DEFAULT_CONDITIONS,
    colors=None, labels=None,
    marker="o", point_size=10.0, point_alpha=0.85,
    point_edge_color="none", point_edge_width=0.0, rasterized=False,
    xscale="log", xlim=None, ylim=None, xticks=None, xticklabels=None,
    yticks=None, show_minor_xticks=False,
    show_ref=True, ref_y=0.0, ref_ls="--", ref_lw=0.6,
    ref_color=REFERENCE_LINE_COLOR,
    xlabel="Median response time (s, log scale)",
    ylabel="RT vs distance slope (% per unit)",
    show_legend=True, legend_loc="upper left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_handletextpad=None,
    legend_borderaxespad=None,
) -> dict:
    """One point per participant at two per-participant measures.

    Each row of ``measures`` is drawn at (``x_col``, ``y_col``), one color per group, with a
    dashed line at ``ref_y``. Raises if a point falls outside the drawn limits. Returns per
    group the number of points, the median, minimum and maximum on each axis, and Spearman's
    rho between the two measures.
    """
    fname = "make_participant_scatter"
    colors = {**_DEFAULT_COLORS, **(colors or {})}
    labels = {**_DEFAULT_LABELS, **(labels or {})}
    if measures[[x_col, y_col]].isna().any().any():
        raise ValueError(f"{fname}: missing values in {x_col} / {y_col}")
    stats = {"x_col": x_col, "y_col": y_col, "by_group": {}}
    for g in groups:
        sub = measures[measures[group_col] == g]
        if sub.empty:
            raise ValueError(f"{fname}: no rows for group {g!r}")
        xs = sub[x_col].to_numpy(float)
        ys = sub[y_col].to_numpy(float)
        _check_in_frame(xs, xlim, axis="x", fname=fname)
        _check_in_frame(ys, ylim, axis="y", fname=fname)
        ax.scatter(xs, ys, **_scatter_kw(
            color=colors[g], point_size=point_size, point_alpha=point_alpha,
            point_edge_color=point_edge_color, point_edge_width=point_edge_width,
            marker=marker, label=labels[g], rasterized=rasterized))
        stats["by_group"][g] = {
            "n": int(len(sub)),
            "x_median": _round(np.median(xs)), "x_min": _round(xs.min()),
            "x_max": _round(xs.max()),
            "y_median": _round(np.median(ys)), "y_min": _round(ys.min()),
            "y_max": _round(ys.max()),
            "spearman_rho": _round(spearman_rho(xs, ys)),
        }
    if show_ref:
        ax.axhline(ref_y, color=ref_color, ls=ref_ls, lw=ref_lw, zorder=1)
    ax.set_xscale(xscale)
    if xlim is not None:
        ax.set_xlim(*xlim)
    if ylim is not None:
        ax.set_ylim(*ylim)
    if xticks is not None:
        ax.xaxis.set_major_locator(FixedLocator(list(xticks)))
        ax.xaxis.set_major_formatter(FixedFormatter(
            list(xticklabels) if xticklabels is not None else [f"{t:g}" for t in xticks]))
    if not show_minor_xticks:
        ax.xaxis.set_minor_locator(NullLocator())
    if yticks is not None:
        ax.set_yticks(list(yticks))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if show_legend:
        _legend(ax, legend_loc=legend_loc, legend_bbox=legend_bbox, legend_ncol=legend_ncol,
                legend_title=legend_title, legend_fontsize=legend_fontsize,
                legend_frameon=legend_frameon, handletextpad=legend_handletextpad,
                borderaxespad=legend_borderaxespad)
    return stats


def make_category_violins(
    ax, measures, *,
    cat_col, categories, y_col="rt_slope_pct",
    group_col="condition", groups=_DEFAULT_CONDITIONS,
    colors=None, labels=None, category_labels=None,
    dodge=0.38,
    show_violins=True, violin_width=0.34, bw_method="scott", kde_points=200,
    min_violin_n=3, fill_alpha=0.22, violin_edge_alpha=1.0,
    violin_edge_width=0.6,
    show_medians=True, median_color=None, median_width=0.6,
    median_line_width=1.0,
    show_points=True, jitter_width=0.05, jitter_seed=0,
    marker="o", point_size=5.0, point_alpha=0.85,
    point_edge_color="none", point_edge_width=0.0, rasterized=False,
    xlim=None, ylim=None, yticks=None,
    show_ref=True, ref_y=0.0, ref_ls="--", ref_lw=0.6,
    ref_color=REFERENCE_LINE_COLOR,
    xlabel=None,
    ylabel="RT vs distance slope (% per unit)",
    show_legend=True, legend_loc="upper right", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_handletextpad=None,
    legend_borderaxespad=None, legend_handlelength=None,
    legend_handleheight=None,
) -> dict:
    """One violin per condition and answer category, with every participant drawn.

    Category ``k`` of ``categories`` sits at x = ``k``; within it the groups are dodged
    symmetrically (``dodge`` between neighboring centers, first group on the left). Each violin
    is matplotlib's ``violinplot``: a Gaussian kernel density estimate of ``y_col`` (bandwidth
    ``bw_method``, evaluated at ``kde_points`` heights between the group's own minimum and
    maximum, so no violin extends past its data), drawn at full width ``violin_width`` at its
    densest height, filled in the group color at ``fill_alpha`` and outlined in it. A violin
    needs at least ``min_violin_n`` points (smaller groups show their points only). With
    ``show_medians`` a horizontal line ``median_width`` violin widths wide marks the group's
    median. Points are jittered uniformly by up to ``jitter_width`` around the violin center
    with one ``np.random.default_rng(jitter_seed)`` drawn in group order. Rows without a
    category (a skipped answer) are left out and counted; a category outside ``categories``
    raises, as does a point outside the drawn limits. The legend shows one filled patch per
    group. Returns per group the points drawn, the rows without a category, per category the
    number of points, the median of ``y_col`` and whether a violin was drawn, and Spearman's
    rho between the category's position and ``y_col``.
    """
    fname = "make_category_violins"
    colors = {**_DEFAULT_COLORS, **(colors or {})}
    labels = {**_DEFAULT_LABELS, **(labels or {})}
    categories = list(categories)
    category_labels = category_labels or {}
    present = measures[cat_col].dropna().astype(str)
    stray = sorted(set(present) - set(categories))
    if stray:
        raise ValueError(f"{fname}: {cat_col} has values outside the categories: {stray}")
    if measures[y_col].isna().any():
        raise ValueError(f"{fname}: missing values in {y_col}")
    code = {c: k for k, c in enumerate(categories)}
    rng = np.random.default_rng(jitter_seed)
    stats = {"cat_col": cat_col, "y_col": y_col, "categories": categories,
             "by_group": {}}
    handles = []
    for i, g in enumerate(groups):
        sub = measures[measures[group_col] == g]
        if sub.empty:
            raise ValueError(f"{fname}: no rows for group {g!r}")
        has = sub[sub[cat_col].notna()]
        xs = has[cat_col].astype(str).map(code).to_numpy(int)
        ys = has[y_col].to_numpy(float)
        _check_in_frame(ys, ylim, axis="y", fname=fname)
        offset = (i - (len(groups) - 1) / 2) * dodge
        face = to_rgba(colors[g], fill_alpha)
        edge = to_rgba(colors[g], violin_edge_alpha)
        per_cat = {}
        for k, c in enumerate(categories):
            vals = ys[xs == k]
            drawn = bool(show_violins and len(vals) >= min_violin_n)
            if drawn:
                parts = ax.violinplot(
                    [vals], positions=[k + offset], widths=violin_width,
                    showmeans=False, showextrema=False, showmedians=False,
                    points=kde_points, bw_method=bw_method)
                for body in parts["bodies"]:
                    body.set_facecolor(face)
                    body.set_edgecolor(edge)
                    body.set_linewidth(violin_edge_width)
                    body.set_alpha(None)
                    body.set_zorder(2)
            if show_medians and len(vals):
                ax.plot([k + offset - median_width * violin_width / 2,
                         k + offset + median_width * violin_width / 2],
                        [np.median(vals)] * 2,
                        color=median_color if median_color is not None else colors[g],
                        lw=median_line_width, solid_capstyle="butt", zorder=4)
            per_cat[c] = {"n": int(len(vals)),
                          "y_median": _round(np.median(vals)) if len(vals) else None,
                          "violin_drawn": drawn}
        if show_points:
            jit = rng.uniform(-jitter_width, jitter_width, size=len(xs))
            ax.scatter(xs + offset + jit, ys, **_scatter_kw(
                color=colors[g], point_size=point_size, point_alpha=point_alpha,
                point_edge_color=point_edge_color,
                point_edge_width=point_edge_width, marker=marker, label=None,
                rasterized=rasterized))
        handles.append(Patch(facecolor=face, edgecolor=edge,
                             linewidth=violin_edge_width, label=labels[g]))
        stats["by_group"][g] = {
            "n": int(len(has)),
            "n_without_category": int(len(sub) - len(has)),
            "by_category": per_cat,
            "spearman_rho": _round(spearman_rho(xs, ys)),
        }
    if show_ref:
        ax.axhline(ref_y, color=ref_color, ls=ref_ls, lw=ref_lw, zorder=1)
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels([category_labels.get(c, c) for c in categories])
    ax.set_xlim(*(xlim if xlim is not None else (-0.5, len(categories) - 0.5)))
    if ylim is not None:
        ax.set_ylim(*ylim)
    if yticks is not None:
        ax.set_yticks(list(yticks))
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if show_legend:
        _legend(ax, handles, legend_loc=legend_loc, legend_bbox=legend_bbox,
                legend_ncol=legend_ncol, legend_title=legend_title,
                legend_fontsize=legend_fontsize, legend_frameon=legend_frameon,
                handletextpad=legend_handletextpad, borderaxespad=legend_borderaxespad,
                handlelength=legend_handlelength, handleheight=legend_handleheight)
    return stats
