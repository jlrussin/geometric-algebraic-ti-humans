"""The LaTeX tables of the mixed-effects models: formats, row order, and the committed tables."""

from __future__ import annotations

import re

import pandas as pd
import pytest

from geo_alg_ti_humans import stats_tables

MODEL_COLUMNS = ["experiment", "model", "set", "formula", "rung", "term", "estimate", "std_error",
                 "df", "statistic", "p_value", "conf_low", "conf_high"]


def _fixed(rows, df=""):
    """``models.csv`` rows of one model ``m``, set ``""``, from (term, estimate, p) triples."""
    return pd.DataFrame([
        {"experiment": "1", "model": "m", "set": "", "formula": "", "rung": "1", "term": term,
         "estimate": str(estimate), "std_error": "0.0123", "df": df, "statistic": "-2.345",
         "p_value": str(p), "conf_low": "-0.5", "conf_high": "1.25"}
        for term, estimate, p in rows], columns=MODEL_COLUMNS)


def _random(rows, observations="1600", participants="40"):
    """``random_effects.csv`` rows of model ``m`` from (group, term1, term2, estimate)."""
    return pd.DataFrame([
        {"experiment": "1", "model": "m", "set": "", "group": group, "term1": term1,
         "term2": term2, "estimate": str(estimate), "observations": observations,
         "participants": participants}
        for group, term1, term2, estimate in rows])


LOGISTIC = _fixed([("(Intercept)", 0.75944, 0.0004), ("symbolic_distance", -0.3869, 0.4421)])
LINEAR = _fixed([("(Intercept)", 8.1802, 0.0499)], df="40.2757")
RANDOM = _random([("participant", "(Intercept)", "", 0.672), ("participant", "symbolic_distance",
                  "", 0.058), ("participant", "(Intercept)", "symbolic_distance", -0.8366)])


def test_a_logistic_model_has_z_and_no_df_column():
    text = stats_tables.table_text(LOGISTIC, RANDOM, 1, "m", "")
    assert r"\begin{tabular}{lrrcrr}" in text
    assert r"Effect & Estimate & \textit{SE} & 95\% CI & $z$ & $p$ \\" in text
    assert r"\quad Intercept & 0.759 & 0.012 & [$-$0.500, 1.250] & $-$2.35 & $<$.001 \\" in text
    assert r"\quad Symbolic distance & $-$0.387 & 0.012 & [$-$0.500, 1.250] & $-$2.35 & .442 \\" \
        in text


def test_a_linear_model_has_t_and_its_df():
    residual = _random([("participant", "(Intercept)", "", 0.5), ("residual", "", "", 0.54)])
    text = stats_tables.table_text(LINEAR, residual, 1, "m", "")
    assert r"\begin{tabular}{lrrcrrr}" in text
    assert "& $t$ & \\textit{df} & $p$ \\\\" in text
    assert r"& $-$2.35 & 40.28 & .050 \\" in text
    assert r"\quad Residual & 0.540 \\" in text
    assert "correlations" not in text


def test_sds_come_before_correlations_and_sizes_close_the_table():
    text = stats_tables.table_text(LOGISTIC, RANDOM, 1, "m", "")
    order = [text.index(s) for s in (r"\textit{Random effects (SD)}",
                                     r"\quad Symbolic distance & 0.058",
                                     r"\textit{Random-effect correlations}",
                                     r"\quad Intercept, symbolic distance & $-$.84 \\",
                                     r"Participants & 40 \\", r"Observations & 1,600 \\")]
    assert order == sorted(order)


def test_uncorrelated_random_effects_say_so():
    uncorrelated = _random([("participant", "(Intercept)", "", 0.672),
                            ("participant", "symbolic_distance", "", 0.058)])
    text = stats_tables.table_text(LOGISTIC, uncorrelated, 1, "m", "")
    assert r"\textit{Random-effect correlations}" in text
    assert r"\quad None (uncorrelated random effects) \\" in text
    single = _random([("participant", "(Intercept)", "", 0.672)])
    assert "correlations" not in stats_tables.table_text(LOGISTIC, single, 1, "m", "")


def test_experiment2_slopes_follow_the_model_terms():
    fixed = _fixed([("(Intercept)", 2.5, 0.0001), ("condition", -2.4, 0.0001),
                    ("slope_congruent", 0.845, 0.0001), ("slope_shuffled", -0.48, 0.0001)])
    text = stats_tables.table_text(fixed, RANDOM, 1, "m", "")
    assert text.index("Condition (shuffled)") < text.index("Distance slope within condition") \
        < text.index(r"\quad Congruent") < text.index(r"\quad Shuffled")


def test_a_missing_value_or_unknown_term_fails():
    with pytest.raises(ValueError):
        stats_tables.table_text(_fixed([("(Intercept)", "", 0.01)]), RANDOM, 1, "m", "")
    with pytest.raises(KeyError):
        stats_tables.table_text(_fixed([("unknown_term", 1.0, 0.01)]), RANDOM, 1, "m", "")
    with pytest.raises(KeyError):
        stats_tables.table_text(LOGISTIC, RANDOM, 1, "another_model", "")
    with pytest.raises(ValueError):
        stats_tables.table_text(LOGISTIC, _random([("item_pair", "(Intercept)", "", 0.1)]), 1,
                                "m", "")


def test_the_committed_tables_are_the_written_ones(repo_root, tmp_path):
    """Writing the tables from the committed results reproduces the committed tables, and no
    other table is committed."""
    committed = repo_root / "results" / "stats_tables"
    written = stats_tables.write_tables(repo_root / "results", tmp_path)
    names = {stats_tables.table_name(e, m) for e, m, _ in stats_tables.TABLES}
    assert {p.name for p in written} == names
    assert {p.name for p in committed.iterdir()} == names
    for path in written:
        assert path.read_bytes() == (committed / path.name).read_bytes(), path.name


def test_the_committed_tables_set_in_plain_latex(repo_root):
    """ASCII only; "<" and the minus sign only in math; every "%" escaped but the first line's."""
    for path in sorted((repo_root / "results" / "stats_tables").glob("*.tex")):
        text = path.read_text()
        assert text.isascii(), path.name
        first, *rest = text.splitlines()
        assert first.startswith("% ")
        body = "\n".join(rest)
        assert "<" not in body.replace("$<$", ""), path.name
        assert re.search(r"(?<!\\)%", body) is None, path.name
        assert re.search(r"(?<![$])-(?=\d)", body) is None, path.name
