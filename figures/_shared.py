"""Shared plumbing for the figure scripts: the frames each figure draws, sizing, saving, and the
command line.

Each ``fig_<topic>.py`` redraws one human figure of the paper from the data tables and writes it
to ``figures/out/``. A script's ``draw`` takes the prepared frames and returns the figure and
the statistics it drew; its ``build`` loads the frames from the tables and calls ``draw``.
Figures are built at their final physical size in inches with constrained layout and saved
without a tight bounding box, so a PDF is placed in the paper at full scale and never resized.
The participant box figures place their panels at fixed positions in inches instead
(``_participants.py``).
"""

from __future__ import annotations

import argparse
import io
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from geo_alg_ti_humans import prepare, tables
from geo_alg_ti_humans.plots import style

OUT_DIR: Path = Path(__file__).resolve().parent / "out"
PREVIEW_FORMAT: str = "png"
# The constrained-layout settings every figure is drawn with: the space between the panels and
# the page edge, in inches, and the gap between neighboring panels as a fraction of their width
# or height.
W_PAD_IN: float = 0.042
H_PAD_IN: float = 0.042
WSPACE: float = 0.06
HSPACE: float = 0.08
# The panel letters' offset in points from each axes' top-left corner.
LETTER_OFFSET_PT: tuple[float, float] = (-14.0, 2.0)
# The file contract every saved figure meets: TrueType text in PDF and PostScript output, and the
# declared page size kept.
SAVE_RC: dict[str, object] = {"pdf.fonttype": 42, "ps.fonttype": 42, "savefig.bbox": "standard"}
# The attribute of a figure that holds the matplotlib parameters it was drawn with
# (``styled_figure``), so that ``save`` writes it under them.
_RC_ATTR: str = "_drawn_with_rc"

# Experiment 2: the boolean column marking the retained participants within all finishers, and
# the sessions table's count of the main questions each session saved, carried on its questions.
RETAINED_COL: str = "retained"
QUESTIONS_COL: str = "n_main_questions"


def experiment1_trials(data_root: Path | None = None) -> pd.DataFrame:
    """The learning and test trials of the sessions the Experiment 1 exclusions keep.

    One session per kept participant; rows in trial order within each participant.
    """
    sessions = tables.load("sessions", "experiment1", data_root)
    trials = tables.load("trials", "experiment1", data_root)
    rows = prepare.kept_rows(trials, prepare.exclusions_experiment1(sessions, trials))
    rows = rows[rows["phase"].isin(prepare.TASK_PHASES)]
    order = [*tables.SESSION_KEY, "trial_index"]
    return rows.sort_values(order, kind="stable").reset_index(drop=True)


def experiment2_frames(data_root: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Experiment 2's main questions and questionnaire answers of all finishers.

    Both frames carry the boolean ``RETAINED_COL``, true for the retained participants (who
    pass every exclusion rule). The questions carry ``log_rt``, the response-time outlier flag
    ``rt_trimmed`` (``prepare.rt_trimmed_experiment2``) and their session's ``QUESTIONS_COL``,
    and are in question order within each participant; the answers are in participant order.
    """
    sessions = tables.load("sessions", "experiment2", data_root)
    trials = tables.load("trials", "experiment2", data_root)
    questionnaire = tables.load("questionnaire", "experiment2", data_root)
    sets = prepare.participant_sets_experiment2(sessions, trials)

    def with_retained(df: pd.DataFrame) -> pd.DataFrame:
        df = df.reset_index(drop=True)
        retained_rows = prepare.kept_rows(df, sets["retained"])
        return df.assign(**{RETAINED_COL: df.index.isin(retained_rows.index)})

    finishers = sets["all_finishers"]
    rows = with_retained(prepare.rt_trimmed_experiment2(prepare.kept_rows(trials, finishers)))
    rows = rows.merge(sessions[[*tables.SESSION_KEY, QUESTIONS_COL]], on=list(tables.SESSION_KEY),
                      how="left", validate="many_to_one")
    if rows[QUESTIONS_COL].isna().any():
        raise ValueError(f"experiment2_frames: {_without_count(rows)}")
    rows = rows.sort_values(["participant", "question_number"], kind="stable")
    answers = with_retained(prepare.kept_rows(questionnaire, finishers))
    answers = answers.sort_values("participant", kind="stable")
    return rows.reset_index(drop=True), answers.reset_index(drop=True)


def _without_count(rows: pd.DataFrame) -> str:
    missing = rows.loc[rows[QUESTIONS_COL].isna(), list(tables.SESSION_KEY)].drop_duplicates()
    return (f"no {QUESTIONS_COL} for {len(missing)} of the questions' sessions: the sessions "
            "table does not list them")


def questions_per_session(rows: pd.DataFrame) -> int:
    """The number of main questions every session of ``rows`` saved: the sessions table's
    ``QUESTIONS_COL``, which ``experiment2_frames`` carries on every question.

    Raises if ``rows`` is empty or lacks the column, if a question's session is missing from
    the sessions table, or unless every session saved the same number.
    """
    if QUESTIONS_COL not in rows.columns:
        raise KeyError(f"questions_per_session: the questions carry no {QUESTIONS_COL} column "
                       "(experiment2_frames adds it from the sessions table)")
    if rows.empty:
        raise ValueError("questions_per_session: no questions")
    counts = rows[QUESTIONS_COL]
    if counts.isna().any():
        raise ValueError(f"questions_per_session: {_without_count(rows)}")
    if counts.nunique() != 1:
        raise ValueError("questions_per_session: the sessions saved different numbers of main "
                         f"questions: {sorted(int(n) for n in counts.unique())}")
    return int(counts.iloc[0])


def retained(df: pd.DataFrame) -> pd.DataFrame:
    """The rows of the retained participants; raises if ``RETAINED_COL`` has nulls."""
    flag = df[RETAINED_COL]
    if flag.isna().any():
        raise ValueError(f"{RETAINED_COL} has nulls")
    return df[flag.astype(bool)]


def participants_by_condition(df: pd.DataFrame, conditions: Sequence[str]) -> dict[str, int]:
    """The number of distinct participants in each of ``conditions`` (0 when absent)."""
    return {c: int(df.loc[df["condition"] == c, "participant"].nunique()) for c in conditions}


@contextmanager
def styled_figure(rc: Mapping[str, object] | None = None, **options) -> Iterator[Figure]:
    """A new figure (``plt.figure(**options)``) for the body of a ``with`` statement that draws
    it, under ``style.apply_style`` and the figure's own ``rc`` on top.

    ``rc`` applies inside the ``with`` statement only, so it never reaches another figure; it is
    also kept on the figure (``figure_rc``), and ``save`` applies it again while the figure is
    written. If the body raises, the figure is closed.
    """
    style.apply_style()
    with matplotlib.rc_context(rc):
        fig = plt.figure(**options)
        setattr(fig, _RC_ATTR, dict(rc or {}))
        try:
            yield fig
        except BaseException:
            plt.close(fig)
            raise


def figure_rc(fig: Figure) -> dict[str, object]:
    """The matplotlib parameters ``fig`` was drawn with on top of the style (``styled_figure``);
    empty for a figure made otherwise."""
    return dict(getattr(fig, _RC_ATTR, {}))


@contextmanager
def mosaic_figure(
    mosaic: Sequence[Sequence[str]],
    *,
    width_in: float,
    height_in: float,
    height_ratios: Sequence[float] | None = None,
    width_ratios: Sequence[float] | None = None,
    rc: Mapping[str, object] | None = None,
) -> Iterator[tuple[Figure, dict[str, Axes]]]:
    """A figure at exact physical size with constrained layout and one axes per mosaic name,
    for the body of a ``with`` statement that draws its panels.

    ``mosaic`` lists the rows of panel names ("." leaves a slot empty). ``rc`` holds matplotlib
    parameters for this figure on top of ``style.apply_style``, such as the legend handle
    length, applied as ``styled_figure`` applies them. Yields the figure and its axes by name;
    if the body raises, the figure is closed.
    """
    with styled_figure(rc, figsize=(width_in, height_in)) as fig:
        axes = fig.subplot_mosaic(
            [list(row) for row in mosaic],
            height_ratios=list(height_ratios) if height_ratios is not None else None,
            width_ratios=list(width_ratios) if width_ratios is not None else None,
            empty_sentinel=".",
        )
        fig.get_layout_engine().set(w_pad=W_PAD_IN, h_pad=H_PAD_IN, wspace=WSPACE, hspace=HSPACE)
        yield fig, axes


def letter_panels(axes: Mapping[str, Axes], letters: Mapping[str, str]) -> None:
    """Add a bold letter to each named axes, in the order of ``letters``."""
    x_pt, y_pt = LETTER_OFFSET_PT
    for name, letter in letters.items():
        style.add_panel_label(axes[name], letter, x_pt=x_pt, y_pt=y_pt)


@contextmanager
def _quiet_font_subsetting() -> Iterator[None]:
    """Hold back the font subsetting reports while a figure is written; they describe the fonts."""
    logger = logging.getLogger("fontTools")
    level = logger.level
    logger.setLevel(max(level, logging.ERROR))
    try:
        yield
    finally:
        logger.setLevel(level)


def save(fig: Figure, name: str, *, out_dir: Path = OUT_DIR,
         formats: Sequence[str] = ("pdf",)) -> list[Path]:
    """Write the figure in each format plus a PNG preview, close it, and return the paths.

    The PDF is always rendered first (in memory when ``formats`` does not ask for it), then the
    preview, then any other format. Constrained layout settles only after the first rendering,
    so this order gives the same preview whatever ``formats`` asks for. The parameters the
    figure was drawn with (``figure_rc``) are in force while it is written, and the files meet
    ``SAVE_RC`` whatever they are. The PDF embeds rasterized artists at ``style.RASTER_DPI``;
    the preview is rendered at ``style.PREVIEW_DPI``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    others = [fmt for fmt in dict.fromkeys(formats) if fmt not in ("pdf", PREVIEW_FORMAT)]
    paths = []
    with matplotlib.rc_context({**figure_rc(fig), **SAVE_RC}), _quiet_font_subsetting():
        if "pdf" in formats:
            paths.append(out_dir / f"{name}.pdf")
            fig.savefig(paths[-1], dpi=style.RASTER_DPI)
        else:
            fig.savefig(io.BytesIO(), format="pdf", dpi=style.RASTER_DPI)
        for fmt in (PREVIEW_FORMAT, *others):
            paths.append(out_dir / f"{name}.{fmt}")
            dpi = style.PREVIEW_DPI if fmt == PREVIEW_FORMAT else style.RASTER_DPI
            fig.savefig(paths[-1], dpi=dpi)
    plt.close(fig)
    return paths


def main(build: Callable[[argparse.Namespace], Figure], *, name: str,
         argv: Sequence[str] | None = None) -> list[Path]:
    """Parse ``--data``, ``--out`` and ``--format``, build the figure, save it, print the paths
    of the files written, and return them.

    ``argv`` is the list of arguments to parse (default: the command line).
    """
    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(
        description=f"redraw the {name.replace('_', ' ')} figure from the data tables")
    parser.add_argument(
        "--data", type=Path, default=None,
        help=f"directory of the data tables (default: ${tables.DATA_ENV} if set, else data/)")
    parser.add_argument("--out", type=Path, default=OUT_DIR,
                        help="directory the figure files are written to")
    parser.add_argument("--format", action="append", default=None,
                        help="an output format; repeat for several (pdf)")
    args = parser.parse_args(argv)
    fig = build(args)
    paths = save(fig, name, out_dir=args.out, formats=tuple(args.format or ("pdf",)))
    for path in paths:
        print(path)
    return paths
