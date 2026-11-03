"""Experiment 1 test panels: accuracy and response time for every queried item pair.

One x position per unordered pair of queried items, laid out in blocks of increasing symbolic
distance (distance 1 first: AB, BC, ...; then distance 2: AC, BD, ...) with a gap between
blocks; points are connected within a block only. Both tests are drawn on one axes (IWL test
red, ICL test blue), dodged sideways so their error bars stay apart.

Item letters come from each test's own observed ranks: the lowest observed rank (the most
preferred item) becomes "A". On the ICL test the ranks are positions in that trial's novel
ordering, so the letters mean "position in the ordering shown" there. Each test must show
exactly ``len(pair_letters)`` consecutive ranks, the symbolic distance must equal the rank
difference on every row, and every test must query the same pairs, so a mislabeled slice
raises instead of drawing. The letters, pairs and positions come from all of a test's trials,
before any response-time filter, so a pair without a value leaves a gap in its block's line
instead of changing the layout.

Each participant is aggregated first (mean accuracy, or the median response time of their
correct, answered trials, per pair), then the mean and one standard error are taken across
participants. A pair holds only one to five trials per participant, so per-participant points
fall on a few values and are off by default.

Block labels are annotations a fixed number of points below the axis line, so they sit at the
same distance under the rotated pair labels whatever the panel height; ``xlabel_pad`` leaves
room for them.
"""

from __future__ import annotations

import numpy as np

from geo_alg_ti_humans.plots import _check_in_frame, _legend, _rounded_sem, _rt_frame
from geo_alg_ti_humans.plots.style import (
    PAIR_LETTERS,
    REFERENCE_LINE_COLOR,
    RESPONSE_TIME_LABEL,
    TEST_COLORS,
)
from geo_alg_ti_humans.summaries import participant_mean_sem

_DEFAULT_PHASES = ("iwl_test", "icl_test")
_DEFAULT_LABELS = {"iwl_test": "IWL test", "icl_test": "ICL test"}
_DEFAULT_COLORS = {
    "iwl_test": TEST_COLORS["iwl"],
    "icl_test": TEST_COLORS["icl"],
}


# Pair layout: observed ranks to letters, and pairs in distance blocks with a gap between blocks.
def _rank_letter_map(sub, pair_letters, *, fname):
    """{observed rank: letter}; lowest observed rank -> pair_letters[0]."""
    ranks = sorted(set(sub["rank_a"].tolist()) | set(sub["rank_b"].tolist()))
    n = len(pair_letters)
    if len(ranks) != n:
        raise ValueError(
            f"{fname}: expected exactly {n} distinct ranks for letters "
            f"{pair_letters!r}, found {len(ranks)} ({ranks})")
    if ranks != list(range(ranks[0], ranks[0] + n)):
        raise ValueError(f"{fname}: observed ranks are not consecutive ({ranks})")
    return {int(r): pair_letters[i] for i, r in enumerate(ranks)}


def _pair_positions(sub, d_values, block_gap, *, fname):
    """{(rank_a, rank_b): x}: blocks by ascending distance with ``block_gap`` empty x units
    between blocks; within a block ordered by rank_a (the more preferred item first)."""
    pos = {}
    x = 0.0
    for d in d_values:
        block = (sub[sub["d"] == d]
                 .drop_duplicates(["rank_a", "rank_b"])
                 .sort_values(["rank_a", "rank_b"]))
        if block.empty:
            raise ValueError(f"{fname}: no pairs at symbolic distance {d}")
        for a, b in zip(block["rank_a"], block["rank_b"]):
            pos[(int(a), int(b))] = x
            x += 1.0
        x += block_gap
    return pos


def _phase_frame(trials, phase, *, left_col, right_col, distance_col, fname):
    """Rows of one test with rank_a < rank_b and their distance."""
    sub = trials[trials["phase"] == phase]
    if sub.empty:
        raise ValueError(f"{fname}: no rows for phase {phase!r}")
    left = sub[left_col].astype(int).to_numpy()
    right = sub[right_col].astype(int).to_numpy()
    lo = np.minimum(left, right)
    hi = np.maximum(left, right)
    d = sub[distance_col].astype(int).to_numpy()
    if not (hi - lo == d).all():
        raise ValueError(f"{fname}: {phase}: symbolic distance != the rank "
                         "difference on some trials")
    out = sub.copy()
    out["rank_a"] = lo
    out["rank_b"] = hi
    out["d"] = d
    return out


def _make_by_pair(
    ax, trials, *, value_col, agg, fname, prepare,
    phases, labels, colors, left_col, right_col, distance_col, d_values,
    pair_letters, participant_col,
    block_gap, error_style, band_alpha, errorbar_lw, errorbar_capsize,
    show_points, point_size, point_alpha, point_dodge,
    jitter_width, jitter_seed, marker, marker_size, line_width,
    show_chance, chance, chance_ls, chance_lw, chance_color,
    xlabel, ylabel, xlabel_pad, tick_rotation, tick_fontsize,
    show_block_labels, block_label_fmt, block_label_offset_pt,
    block_label_fontsize, block_label_color,
    xlim, x_margin, ylim, xticks, yticks,
    show_legend, legend_loc, legend_ncol, legend_title, legend_fontsize,
    legend_bbox, legend_frameon, legend_framealpha,
):
    phases = tuple(phases)
    if not phases:
        raise ValueError(f"{fname}: phases must name at least one test")
    colors = {**_DEFAULT_COLORS, **(colors or {})}
    labels = {**_DEFAULT_LABELS, **(labels or {})}
    if error_style not in ("bars", "band", "none"):
        raise ValueError(f"{fname}: unknown error_style {error_style!r}")
    rng = np.random.default_rng(jitter_seed)

    frames, letter_maps, pair_sets = {}, {}, {}
    for phase in phases:
        frame = _phase_frame(trials, phase, left_col=left_col,
                             right_col=right_col, distance_col=distance_col,
                             fname=fname)
        letters = _rank_letter_map(frame, pair_letters, fname=f"{fname}/{phase}")
        frame["pair"] = [letters[int(a)] + letters[int(b)]
                         for a, b in zip(frame["rank_a"], frame["rank_b"])]
        frames[phase] = frame
        letter_maps[phase] = letters
        # Compared across tests as letter pairs: each test's letters come from its own ranks,
        # so tests whose ranks are consistently offset still name the same pairs.
        pair_sets[phase] = set(frame["pair"].tolist())
    first = phases[0]
    for phase in phases[1:]:
        if pair_sets[phase] != pair_sets[first]:
            raise ValueError(f"{fname}: phases {first!r} and {phase!r} do not "
                             "query the same set of item pairs "
                             f"({sorted(pair_sets[first] ^ pair_sets[phase])})")

    ref = frames[first]
    ds = (sorted(set(int(d) for d in ref["d"].unique())) if d_values is None
          else [int(d) for d in d_values])
    ref = ref[ref["d"].isin(ds)]
    pos = _pair_positions(ref, ds, block_gap, fname=fname)
    letters = letter_maps[first]
    label_of = {ab: f"{letters[ab[0]]}{letters[ab[1]]}" for ab in pos}
    ordered = list(pos.items())  # ascending x
    x_of_label = {label_of[ab]: x for ab, x in pos.items()}
    labels_by_d = {d: [label_of[(a, b)] for (a, b), _ in ordered if b - a == d] for d in ds}

    per_phase = {}
    n_rows_used = 0
    for i, phase in enumerate(phases):
        frame = frames[phase]
        frame = prepare(frame[frame["d"].isin(ds)])
        if frame.empty:
            raise ValueError(f"{fname}: no rows for phase {phase!r} after filtering")
        n_rows_used += int(len(frame))
        summary, wide = participant_mean_sem(
            frame, x_col="pair", value_col=value_col,
            participant_col=participant_col, agg=agg)
        summary = summary.copy()
        summary["x"] = summary["pair"].map(x_of_label)
        summary = summary.sort_values("x")
        _check_in_frame(summary["value_mean"], ylim, axis="y", fname=fname)
        if show_points:
            _check_in_frame(wide.to_numpy(dtype=float), ylim, axis="y", fname=fname)
        by_pair = summary.set_index("pair")
        offset = (i - (len(phases) - 1) / 2) * point_dodge
        col = colors[phase]
        lw = {} if line_width is None else {"lw": line_width}
        drawn_label = False
        for d in ds:
            # Every pair of the block, so a pair without a value breaks the line.
            seg = by_pair.reindex(labels_by_d[d])
            x = np.array([x_of_label[p] for p in labels_by_d[d]], dtype=float) + offset
            mean = seg["value_mean"].to_numpy()
            sem = seg["value_sem"].to_numpy()
            if error_style == "band":
                ax.fill_between(x, mean - sem, mean + sem, color=col,
                                alpha=band_alpha, lw=0, zorder=2)
            elif error_style == "bars":
                ax.errorbar(x, mean, yerr=sem, fmt="none", ecolor=col,
                            elinewidth=errorbar_lw, capsize=errorbar_capsize,
                            capthick=errorbar_lw, zorder=3)
            ax.plot(x, mean, color=col, marker=marker, markersize=marker_size,
                    label=(None if drawn_label else labels[phase]), zorder=4,
                    **lw)
            drawn_label = True
        if show_points:
            for pair_label in wide.index:
                vals = wide.loc[pair_label].dropna().to_numpy()
                jit = rng.uniform(-jitter_width, jitter_width, size=len(vals))
                ax.scatter(np.full(len(vals), x_of_label[pair_label] + offset) + jit,
                           vals, s=point_size, color=col, alpha=point_alpha,
                           lw=0, zorder=2)
        n_trials = frame.groupby("pair").size()
        per_phase[phase] = {
            "mean_by_pair": {str(r["pair"]): round(float(r["value_mean"]), 4)
                             for _, r in summary.iterrows()},
            "sem_by_pair": {str(r["pair"]): _rounded_sem(r["value_sem"])
                            for _, r in summary.iterrows()},
            "n_participants_by_pair": {str(r["pair"]): int(r["n_participants"])
                                       for _, r in summary.iterrows()},
            "n_trials_by_pair": {str(p): int(n) for p, n in n_trials.items()},
        }

    if show_chance:
        ax.axhline(chance, color=chance_color, ls=chance_ls, lw=chance_lw,
                   zorder=1)
    if xticks is None:
        ax.set_xticks([x for _, x in ordered])
        tick_kw = {} if tick_fontsize is None else {"fontsize": tick_fontsize}
        ax.set_xticklabels([label_of[ab] for ab, _ in ordered],
                           rotation=tick_rotation, **tick_kw)
    else:
        ax.set_xticks(list(xticks))
    if show_block_labels:
        text_kw = {}
        if block_label_fontsize is not None:
            text_kw["fontsize"] = block_label_fontsize
        if block_label_color is not None:
            text_kw["color"] = block_label_color
        for d in ds:
            xs_d = [x_of_label[p] for p in labels_by_d[d]]
            ax.annotate(block_label_fmt.format(d=d),
                        xy=(float(np.mean(xs_d)), 0.0),
                        xycoords=("data", "axes fraction"),
                        xytext=(0.0, -block_label_offset_pt),
                        textcoords="offset points",
                        ha="center", va="top", annotation_clip=False,
                        **text_kw)
    xlabel_kw = {} if xlabel_pad is None else {"labelpad": xlabel_pad}
    ax.set_xlabel(xlabel, **xlabel_kw)
    ax.set_ylabel(ylabel)
    if xlim is None:
        xs_all = [x for _, x in ordered]
        ax.set_xlim(min(xs_all) - x_margin, max(xs_all) + x_margin)
    else:
        ax.set_xlim(*xlim)
    if ylim is not None:
        ax.set_ylim(*ylim)
    if yticks is not None:
        ax.set_yticks(list(yticks))
    if show_legend:
        _legend(ax, legend_loc=legend_loc, legend_ncol=legend_ncol,
                legend_title=legend_title, legend_fontsize=legend_fontsize,
                legend_bbox=legend_bbox, legend_frameon=legend_frameon,
                legend_framealpha=legend_framealpha)
    return {
        "phases": list(phases),
        "d_values": [int(d) for d in ds],
        "rank_letters_by_phase": {p: {int(r): letter for r, letter in letter_maps[p].items()}
                                  for p in phases},
        "pairs_in_x_order": [label_of[ab] for ab, _ in ordered],
        "n_pairs": len(pos),
        "per_phase": per_phase,
        "error_style": error_style,
        "show_points": bool(show_points),
        "n_rows_used": int(n_rows_used),
    }


def make_pair_accuracy(
    ax, trials, *,
    phases=_DEFAULT_PHASES,
    labels=None,
    colors=None,
    left_col="query_left_rank", right_col="query_right_rank",
    distance_col="symbolic_distance", d_values=None,
    pair_letters=PAIR_LETTERS, participant_col="participant",
    block_gap=1.0,
    error_style="bars", band_alpha=0.25, errorbar_lw=0.8, errorbar_capsize=1.5,
    show_points=False, point_size=3.0, point_alpha=0.25, point_dodge=0.2,
    jitter_width=0.06, jitter_seed=0,
    marker="o", marker_size=3.5, line_width=None,
    show_chance=True, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel="Item pair", ylabel="Accuracy", xlabel_pad=None,
    tick_rotation=90, tick_fontsize=None,
    show_block_labels=True, block_label_fmt="Distance {d}",
    block_label_offset_pt=20.0, block_label_fontsize=None,
    block_label_color=None,
    xlim=None, x_margin=0.7, ylim=(-0.02, 1.02), xticks=None, yticks=None,
    show_legend=True, legend_loc="lower left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
) -> dict:
    """Accuracy for every queried item pair, one series per test.

    Each participant's accuracy on each pair (a trial that ran out of time counts as
    incorrect), then the mean and one standard error across participants. Pairs are blocked by
    symbolic distance and labeled by the letters of the two items (A = the most preferred
    item). ``error_style`` draws the standard errors as "bars", a "band" or "none";
    ``xticks=None`` keeps the pair labels.
    """
    return _make_by_pair(
        ax, trials, value_col="is_correct", agg="mean",
        fname="make_pair_accuracy", prepare=lambda df: df,
        phases=phases, labels=labels, colors=colors, left_col=left_col,
        right_col=right_col, distance_col=distance_col, d_values=d_values,
        pair_letters=pair_letters, participant_col=participant_col,
        block_gap=block_gap, error_style=error_style, band_alpha=band_alpha,
        errorbar_lw=errorbar_lw, errorbar_capsize=errorbar_capsize,
        show_points=show_points, point_size=point_size,
        point_alpha=point_alpha, point_dodge=point_dodge,
        jitter_width=jitter_width, jitter_seed=jitter_seed, marker=marker,
        marker_size=marker_size, line_width=line_width,
        show_chance=show_chance, chance=chance, chance_ls=chance_ls,
        chance_lw=chance_lw, chance_color=chance_color, xlabel=xlabel,
        ylabel=ylabel, xlabel_pad=xlabel_pad, tick_rotation=tick_rotation,
        tick_fontsize=tick_fontsize, show_block_labels=show_block_labels,
        block_label_fmt=block_label_fmt,
        block_label_offset_pt=block_label_offset_pt,
        block_label_fontsize=block_label_fontsize,
        block_label_color=block_label_color, xlim=xlim, x_margin=x_margin,
        ylim=ylim, xticks=xticks, yticks=yticks, show_legend=show_legend,
        legend_loc=legend_loc, legend_ncol=legend_ncol,
        legend_title=legend_title, legend_fontsize=legend_fontsize,
        legend_bbox=legend_bbox, legend_frameon=legend_frameon,
        legend_framealpha=legend_framealpha)


def make_pair_rt(
    ax, trials, *,
    phases=_DEFAULT_PHASES,
    labels=None,
    colors=None,
    left_col="query_left_rank", right_col="query_right_rank",
    distance_col="symbolic_distance", d_values=None,
    pair_letters=PAIR_LETTERS, participant_col="participant",
    rt_col="rt", rt_scale=0.001, correct_only=True, drop_timeouts=True,
    block_gap=1.0,
    error_style="bars", band_alpha=0.25, errorbar_lw=0.8, errorbar_capsize=1.5,
    show_points=False, point_size=3.0, point_alpha=0.25, point_dodge=0.2,
    jitter_width=0.06, jitter_seed=0,
    marker="o", marker_size=3.5, line_width=None,
    show_chance=False, chance=0.5, chance_ls="--", chance_lw=0.6,
    chance_color=REFERENCE_LINE_COLOR,
    xlabel="Item pair", ylabel=RESPONSE_TIME_LABEL, xlabel_pad=None,
    tick_rotation=90, tick_fontsize=None,
    show_block_labels=True, block_label_fmt="Distance {d}",
    block_label_offset_pt=20.0, block_label_fontsize=None,
    block_label_color=None,
    xlim=None, x_margin=0.7, ylim=None, xticks=None, yticks=None,
    show_legend=True, legend_loc="upper left", legend_ncol=1,
    legend_title=None, legend_fontsize=None, legend_bbox=None,
    legend_frameon=None, legend_framealpha=None,
) -> dict:
    """Response time for every queried item pair, one series per test.

    Each participant's median response time on each pair (correct, answered trials by
    default), then the mean and one standard error across participants. ``rt_scale`` rescales
    the values before aggregation (0.001 shows milliseconds as seconds). Layout and letters as
    in ``make_pair_accuracy``, from all of each test's trials.
    """
    stats = _make_by_pair(
        ax, trials, value_col=rt_col, agg="median", fname="make_pair_rt",
        prepare=lambda df: _rt_frame(df, rt_col=rt_col, rt_scale=rt_scale,
                                     correct_only=correct_only, drop_timeouts=drop_timeouts),
        phases=phases, labels=labels, colors=colors, left_col=left_col,
        right_col=right_col, distance_col=distance_col, d_values=d_values,
        pair_letters=pair_letters, participant_col=participant_col,
        block_gap=block_gap, error_style=error_style, band_alpha=band_alpha,
        errorbar_lw=errorbar_lw, errorbar_capsize=errorbar_capsize,
        show_points=show_points, point_size=point_size,
        point_alpha=point_alpha, point_dodge=point_dodge,
        jitter_width=jitter_width, jitter_seed=jitter_seed, marker=marker,
        marker_size=marker_size, line_width=line_width,
        show_chance=show_chance, chance=chance, chance_ls=chance_ls,
        chance_lw=chance_lw, chance_color=chance_color, xlabel=xlabel,
        ylabel=ylabel, xlabel_pad=xlabel_pad, tick_rotation=tick_rotation,
        tick_fontsize=tick_fontsize, show_block_labels=show_block_labels,
        block_label_fmt=block_label_fmt,
        block_label_offset_pt=block_label_offset_pt,
        block_label_fontsize=block_label_fontsize,
        block_label_color=block_label_color, xlim=xlim, x_margin=x_margin,
        ylim=ylim, xticks=xticks, yticks=yticks, show_legend=show_legend,
        legend_loc=legend_loc, legend_ncol=legend_ncol,
        legend_title=legend_title, legend_fontsize=legend_fontsize,
        legend_bbox=legend_bbox, legend_frameon=legend_frameon,
        legend_framealpha=legend_framealpha)
    stats["rt_scale"] = float(rt_scale)
    stats["correct_only"] = bool(correct_only)
    stats["drop_timeouts"] = bool(drop_timeouts)
    return stats
