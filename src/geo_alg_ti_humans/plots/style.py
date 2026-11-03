"""Figure style: fonts, sizes and colors shared by every human panel.

Figures are built at their final physical size in inches with fonts in real points, so a saved
PDF is placed in the paper at full scale and never resized. Text is embedded as TrueType
(``pdf.fonttype`` 42), constrained layout manages the margins, and figures are saved without a
tight bounding box, which would change the declared page size.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

# Page width of a full-width figure, in inches.
DOUBLE_COL_W: float = 7.0

# Typography, in points at print size.
FONT_FAMILY: list[str] = ["Helvetica", "Arial", "DejaVu Sans"]
FONT_SIZE: float = 7.0
AXES_LABEL_SIZE: float = 7.0
TICK_LABEL_SIZE: float = 6.0
LEGEND_SIZE: float = 6.0
TITLE_SIZE: float = 7.0
PANEL_LABEL_SIZE: float = 9.0

# Line weights, in points.
AXES_LINEWIDTH: float = 0.6
DATA_LINEWIDTH: float = 1.0
TICK_WIDTH: float = 0.6
TICK_LENGTH: float = 2.5

# Resolution of the PNG preview, and of rasterized artists inside a PDF.
PREVIEW_DPI: int = 200
RASTER_DPI: int = 600

# The IWL and ICL tests of Experiment 1: in-weight (IWL) red, in-context (ICL) blue.
TEST_COLORS: dict[str, str] = {
    "iwl": "#d62728",
    "icl": "#1f77b4",
}
# Chance lines and other references.
REFERENCE_LINE_COLOR: str = "#7f7f7f"

# Item letters of the per-pair panels, the most preferred item first.
PAIR_LETTERS: str = "ABCDEFG"

# What the context showed on a learning trial. The masked display is the IWL test's display, so it
# takes the IWL red; the context-shown series is a dark gray, distinct from the reference gray.
LEARNING_DISPLAY_ORDER: tuple[str, ...] = ("shown", "masked")
LEARNING_DISPLAY_COLORS: dict[str, str] = {
    "shown": "#333333",
    "masked": TEST_COLORS["iwl"],
}
LEARNING_DISPLAY_LABELS: dict[str, str] = {
    "shown": "Context shown",
    "masked": "Context masked",
}

# First and second half of the learning phase: one hue, told apart by line style and marker,
# each named by its first and last trial ("Trials 1–50").
LEARNING_HALF_ORDER: tuple[str, ...] = ("first", "second")
LEARNING_HALF_LABEL: str = "Trials {first}–{last}"
LEARNING_HALF_LS: dict[str, str] = {"first": "-", "second": "--"}
LEARNING_HALF_MARKER: dict[str, str] = {"first": "o", "second": "s"}

# Axis labels shared by the Experiment 1 figures.
TRIAL_AXIS_LABEL: str = "Trial"
INTERVENING_DISTRACTORS_LABEL: str = "Intervening distractors"
RESPONSE_TIME_LABEL: str = "Response time (s)"
# The short form, on panels too small for the full label.
RESPONSE_TIME_SHORT_LABEL: str = "RT (s)"

# The arbitrage test's two response classes, keyed by the trials table's columns: a response
# follows either the trained ordering (red) or the ordering shown in context (blue).
ARBITRAGE_OUTCOME_COLORS: dict[str, str] = {
    "is_iwl_consistent": TEST_COLORS["iwl"],
    "is_icl_consistent": TEST_COLORS["icl"],
}
ARBITRAGE_OUTCOME_DISPLAY: dict[str, str] = {
    "is_iwl_consistent": "Trained ordering",
    "is_icl_consistent": "Context ordering",
}

# Experiment 2's conditions, and the shuffled condition split into agree and conflict questions
# (light and dark shades on either side of the shuffled brown).
CONTEXT_COLORS: dict[str, str] = {
    "congruent": "#3fb780",
    "shuffled": "#875a5a",
    "shuffled_agree": "#eac2c7",
    "shuffled_conflict": "#54332d",
}
CONTEXT_LABELS: dict[str, str] = {
    "congruent": "Congruent",
    "shuffled": "Shuffled",
    "shuffled_agree": "Shuffled (agree)",
    "shuffled_conflict": "Shuffled (conflict)",
}


def apply_style() -> None:
    """Set the matplotlib parameters every figure is drawn with.

    Call it before creating a figure. It also resets the legend handle length and label
    spacing, so a change made to them elsewhere in the same process does not reach the figure.
    """
    plt.rcParams.update({
        # Text embedded as TrueType, editable in vector-graphics editors.
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "font.family": "sans-serif",
        "font.sans-serif": FONT_FAMILY,
        "font.size": FONT_SIZE,
        "axes.titlesize": TITLE_SIZE,
        "axes.labelsize": AXES_LABEL_SIZE,
        "xtick.labelsize": TICK_LABEL_SIZE,
        "ytick.labelsize": TICK_LABEL_SIZE,
        "legend.fontsize": LEGEND_SIZE,
        "mathtext.fontset": "dejavusans",
        "axes.linewidth": AXES_LINEWIDTH,
        "lines.linewidth": DATA_LINEWIDTH,
        "xtick.major.width": TICK_WIDTH,
        "ytick.major.width": TICK_WIDTH,
        "xtick.major.size": TICK_LENGTH,
        "ytick.major.size": TICK_LENGTH,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "legend.handlelength": 2.0,
        "legend.labelspacing": 0.5,
        # Constrained layout keeps the declared figure size, unlike a tight bounding box.
        "figure.constrained_layout.use": True,
        "figure.dpi": PREVIEW_DPI,
        "savefig.dpi": PREVIEW_DPI,
        "savefig.bbox": "standard",
    })


def add_panel_label(
    ax,
    letter: str,
    *,
    x_pt: float = -14.0,
    y_pt: float = 2.0,
    fontsize: float | None = None,
    fontweight: str = "bold",
    anchor: tuple[float, float] = (0.0, 1.0),
) -> None:
    """A bold panel letter, offset in points from an axes' top-left corner.

    ``anchor`` is the point, in axes fractions, the offsets are measured from; ``fontsize``
    None uses ``PANEL_LABEL_SIZE``.
    """
    ax.annotate(
        letter,
        xy=anchor, xycoords="axes fraction",
        xytext=(x_pt, y_pt), textcoords="offset points",
        fontsize=PANEL_LABEL_SIZE if fontsize is None else fontsize,
        fontweight=fontweight,
        ha="left", va="bottom", annotation_clip=False,
    )
