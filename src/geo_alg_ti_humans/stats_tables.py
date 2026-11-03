"""LaTeX tables of the paper's main mixed-effects models.

One table per model: its fixed effects (estimate, standard error, 95% confidence interval, test
statistic, degrees of freedom for a linear model, p), the distance slope within each condition
for Experiment 2, the participant SDs and correlations of its random effects (stated as none when
its several participant terms are uncorrelated) and, for a linear model, the residual SD, and the
numbers of participants and observations. Each table is a ``tabular`` set in booktabs rules,
without a caption, read from ``models.csv`` and
``random_effects.csv`` under ``results/experiment<k>/``. Numbers are written as the paper writes
them: three decimals for estimates, standard errors, intervals and SDs; two for test statistics
and degrees of freedom; two without a leading zero for correlations; and p to three decimals
without a leading zero ("<.001" below .001).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from geo_alg_ti_humans.summaries import _format_like

# The tabulated models, in the paper's order: (experiment, model, participant set).
TABLES = (
    (1, "iwl_accuracy", ""),
    (1, "icl_accuracy", ""),
    (1, "accuracy_by_test", ""),
    (1, "iwl_rt", ""),
    (1, "icl_rt", ""),
    (1, "rt_by_test", ""),
    (2, "accuracy", "retained"),
    (2, "rt", "retained"),
)

TERM_LABELS = {
    "(Intercept)": "Intercept",
    "symbolic_distance": "Symbolic distance",
    "phase": "Test (IWL)",
    "symbolic_distance:phase": r"Symbolic distance $\times$ test (IWL)",
    "condition": "Condition (shuffled)",
    "log_distance": "Log symbolic distance",
    "trial": "Trial number (per 10 questions)",
    "condition:log_distance": r"Condition $\times$ log symbolic distance",
}
# Experiment 2's distance slope within each condition, a combination of the fixed effects.
SLOPE_LABELS = {"slope_congruent": "Congruent", "slope_shuffled": "Shuffled"}


def table_name(experiment: int, model: str) -> str:
    """The file name of a model's table."""
    return f"experiment{experiment}_{model}.tex"


def _number(value: float, printed: str) -> str:
    """``value`` written as ``printed`` writes its number, with a typographic minus sign."""
    text = _format_like(float(value), printed)
    if text == "nan":
        raise ValueError(f"a missing value where {printed!r} is written")
    return "$-$" + text[1:] if text.startswith("-") else text


def _p(value: float) -> str:
    """A p value: three decimals without a leading zero, or "<.001"."""
    text = _number(value, "< .001")
    return "$<$.001" if text == "< .001" else text


def _lower_first(label: str) -> str:
    return label[0].lower() + label[1:]


def _row(entries: list[str]) -> str:
    return " & ".join(entries) + r" \\"


def table_text(models: pd.DataFrame, random_effects: pd.DataFrame, experiment: int,
               model: str, participant_set: str) -> str:
    """The table of one model, from the rows of ``models.csv`` and ``random_effects.csv`` (all
    fields read as text)."""
    fixed = models[(models["model"] == model) & (models["set"] == participant_set)]
    random = random_effects[(random_effects["model"] == model)
                            & (random_effects["set"] == participant_set)]
    if fixed.empty or random.empty:
        raise KeyError(f"no results for model {model!r} of experiment {experiment}")
    linear = (fixed["df"] != "").all()
    if not linear and (fixed["df"] != "").any():
        raise ValueError(f"model {model!r} has degrees of freedom for only some terms")
    width = 7 if linear else 6
    statistic = "$t$" if linear else "$z$"
    header = ["Effect", "Estimate", r"\textit{SE}", r"95\% CI", statistic]
    header += [r"\textit{df}", "$p$"] if linear else ["$p$"]

    def heading(text: str) -> str:
        return _row([rf"\multicolumn{{{width}}}{{l}}{{\textit{{{text}}}}}"])

    def fixed_row(label: str, r) -> str:
        entries = [rf"\quad {label}", _number(r["estimate"], "0.000"),
                 _number(r["std_error"], "0.000"),
                 f"[{_number(r['conf_low'], '0.000')}, {_number(r['conf_high'], '0.000')}]",
                 _number(r["statistic"], "0.00")]
        if linear:
            entries.append(_number(r["df"], "0.00"))
        return _row(entries + [_p(r["p_value"])])

    lines = [rf"\begin{{tabular}}{{l{'rrcrrr' if linear else 'rrcrr'}}}", r"\toprule",
             _row(header), r"\midrule", heading("Fixed effects")]
    slopes = []
    for _, r in fixed.iterrows():
        if r["term"] in SLOPE_LABELS:
            slopes.append(fixed_row(SLOPE_LABELS[r["term"]], r))
        else:
            lines.append(fixed_row(TERM_LABELS[r["term"]], r))
    if slopes:
        lines += [heading("Distance slope within condition")] + slopes

    unknown = set(random["group"]) - {"participant", "residual"}
    if unknown:
        raise ValueError(f"model {model!r} has random effects of {sorted(unknown)}")
    sds = random[(random["group"] == "participant") & (random["term2"] == "")]
    residual = random[random["group"] == "residual"]
    correlations = random[random["term2"] != ""]
    lines.append(heading("Random effects (SD)"))
    for _, r in sds.iterrows():
        lines.append(_row([rf"\quad {TERM_LABELS[r['term1']]}", _number(r["estimate"], "0.000")]))
    for _, r in residual.iterrows():
        lines.append(_row([r"\quad Residual", _number(r["estimate"], "0.000")]))
    if len(sds) > 1:
        lines.append(heading("Random-effect correlations"))
        if correlations.empty:
            lines.append(_row([r"\quad None (uncorrelated random effects)"]))
        for _, r in correlations.iterrows():
            pair = f"{TERM_LABELS[r['term1']]}, {_lower_first(TERM_LABELS[r['term2']])}"
            lines.append(_row([rf"\quad {pair}", _number(r["estimate"], ".00")]))

    sizes = random[["participants", "observations"]].drop_duplicates()
    if len(sizes) != 1:
        raise ValueError(f"model {model!r} has several counts of participants or observations")
    lines += [r"\midrule",
              _row(["Participants", _number(sizes["participants"].iloc[0], "1,000")]),
              _row(["Observations", _number(sizes["observations"].iloc[0], "1,000")]),
              r"\bottomrule", r"\end{tabular}"]
    first = f"% Written by geo-alg-ti-humans stats-tables from results/experiment{experiment}/."
    return "\n".join([first] + lines) + "\n"


def _read(results_dir: Path, experiment: int, name: str) -> pd.DataFrame:
    path = Path(results_dir) / f"experiment{experiment}" / name
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing: run the R models first")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def write_tables(results_dir: Path, out_dir: Path) -> list[Path]:
    """Write the table of every model in ``TABLES`` into ``out_dir``; return the paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for experiment in sorted({t[0] for t in TABLES}):
        models = _read(results_dir, experiment, "models.csv")
        random_effects = _read(results_dir, experiment, "random_effects.csv")
        for _, model, participant_set in (t for t in TABLES if t[0] == experiment):
            path = out_dir / table_name(experiment, model)
            path.write_text(table_text(models, random_effects, experiment, model,
                                       participant_set))
            written.append(path)
    return written
