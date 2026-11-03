"""The committed results of the R models: columns, models, terms, sets and rungs, and the
random effects in random_effects.csv."""

from __future__ import annotations

import math

import pandas as pd
import pytest

COLUMNS = ["experiment", "model", "set", "formula", "rung", "term", "estimate", "std_error", "df",
           "statistic", "p_value", "conf_low", "conf_high"]
RANDOM_COLUMNS = ["experiment", "model", "set", "group", "term1", "term2", "estimate",
                  "observations", "participants"]

# Experiment 1: each model's formula, terms in the order of the table, and rung.
DISTANCE = "symbolic_distance + (1 + symbolic_distance | participant)"
BY_TEST = "symbolic_distance * phase + (1 + symbolic_distance * phase | participant)"
BY_TEST_UNCORRELATED = "symbolic_distance * phase + (1 + symbolic_distance * phase || participant)"
DISTANCE_TERMS = ["(Intercept)", "symbolic_distance"]
BY_TEST_TERMS = DISTANCE_TERMS + ["phase", "symbolic_distance:phase"]
EXPERIMENT1_MODELS = {
    "accuracy_by_test": (f"is_correct ~ {BY_TEST}", BY_TEST_TERMS, "1"),
    "icl_accuracy": (f"is_correct ~ {DISTANCE}", DISTANCE_TERMS, "1"),
    "icl_rt": (f"log_rt ~ {DISTANCE}", DISTANCE_TERMS, "1"),
    "iwl_accuracy": (f"is_correct ~ {DISTANCE}", DISTANCE_TERMS, "1"),
    "iwl_rt": (f"log_rt ~ {DISTANCE}", DISTANCE_TERMS, "1"),
    "rt_by_test": (f"log_rt ~ {BY_TEST_UNCORRELATED}", BY_TEST_TERMS, "2"),
}
# The models with random effects in random_effects.csv, by experiment: (model, set).
RANDOM_EFFECT_MODELS = {
    1: {(model, "") for model in EXPERIMENT1_MODELS},
    2: {(model, s) for model in ("accuracy", "rt") for s in ("all_finishers", "retained")},
}
EXPERIMENT1_NUMBERS = ["estimate", "std_error", "statistic", "p_value", "conf_low", "conf_high"]

# Experiment 2: each model's participant sets and the rung of its random effects (empty: not a
# model fit).
BOTH = ("all_finishers", "retained")
RETAINED = ("retained",)
EXPERIMENT2_MODELS = {
    "accuracy": (BOTH, "3"),
    "rt": (BOTH, "3"),
    "accuracy_waves": (RETAINED, "3"),
    "rt_waves": (RETAINED, "3"),
    "accuracy_without_round_2": (RETAINED, "3"),
    "rt_without_round_2": (RETAINED, "3"),
    "accuracy_timeouts_dropped": (RETAINED, "3"),
    "rt_all_answered": (RETAINED, "3"),
    "accuracy_leave_one_out": (RETAINED, "3"),
    "rt_leave_one_out": (RETAINED, "3"),
    "accuracy_distance_codings": (RETAINED, "3"),
    "rt_distance_codings": (RETAINED, "3"),
    "accuracy_participant_level": (BOTH, ""),
    "rt_participant_level": (BOTH, ""),
    "accuracy_lee_bounds": (BOTH, ""),
    "rt_lee_bounds": (BOTH, ""),
    "agree_conflict_accuracy": (BOTH, "5"),
    "agree_conflict_rt": (BOTH, "5"),
    "agree_conflict_accuracy_waves": (RETAINED, "5"),
    "agree_conflict_rt_waves": (RETAINED, "5"),
    "agree_conflict_accuracy_timeouts_dropped": (RETAINED, "5"),
    "agree_conflict_rt_all_answered": (RETAINED, "5"),
    "agree_conflict_accuracy_participant_level": (RETAINED, ""),
    "agree_conflict_rt_participant_level": (RETAINED, ""),
    "agree_conflict_rt_all_answered_participant_level": (RETAINED, ""),
    "manipulation_check": (BOTH, ""),
}


def _results(repo_root, experiment: int) -> pd.DataFrame:
    path = repo_root / "results" / f"experiment{experiment}" / "models.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False)


@pytest.fixture(scope="module")
def experiment1(repo_root) -> pd.DataFrame:
    return _results(repo_root, 1)


@pytest.fixture(scope="module")
def experiment2(repo_root) -> pd.DataFrame:
    return _results(repo_root, 2)


@pytest.mark.parametrize("experiment", [1, 2])
def test_columns_follow_the_results_schema(repo_root, experiment):
    results = _results(repo_root, experiment)
    assert list(results.columns) == COLUMNS
    assert set(results["experiment"]) == {str(experiment)}


def test_experiment1_models_hold_every_term_of_the_six_models(experiment1):
    """One row per term of each model, in model order and then in the order of the fit."""
    assert list(zip(experiment1["model"], experiment1["term"])) == [
        (model, term) for model, (_, terms, _) in EXPERIMENT1_MODELS.items() for term in terms
    ]
    for _, r in experiment1.iterrows():
        formula, _, rung = EXPERIMENT1_MODELS[r["model"]]
        assert (r["set"], r["formula"], r["rung"]) == ("", formula, rung)
        assert all(math.isfinite(float(r[column])) for column in EXPERIMENT1_NUMBERS)
        assert float(r["conf_low"]) < float(r["estimate"]) < float(r["conf_high"])
        # Satterthwaite df for the linear models of log RT; none for the logistic models.
        if formula.startswith("log_rt"):
            assert float(r["df"]) > 0
        else:
            assert r["df"] == ""


def test_experiment2_every_model_has_its_sets_and_rung(experiment2):
    assert set(experiment2["model"]) == set(EXPERIMENT2_MODELS)
    for model, (sets, rung) in EXPERIMENT2_MODELS.items():
        rows = experiment2[experiment2["model"] == model]
        assert tuple(sorted(set(rows["set"]))) == sets, model
        assert set(rows["rung"]) == {rung}, model
        assert ((rows["formula"] != "") == (rung != "")).all(), model


def test_experiment2_one_row_per_model_set_and_term_sorted_by_model_and_set(experiment2):
    assert not experiment2.duplicated(["model", "set", "term"]).any()
    keys = list(zip(experiment2["model"], experiment2["set"]))
    assert keys == sorted(keys)


def test_experiment2_reported_rungs_use_participant_distance_slopes(experiment2):
    fitted = experiment2[experiment2["rung"] != ""]
    assert fitted["formula"].str.endswith("+ (1 + log_distance | participant)").all()


def test_experiment2_every_refit_leaving_one_out_passes_strict_mode(experiment2):
    """99 refits per model, each at the reported formula; none fails strict mode."""
    for model in ("accuracy_leave_one_out", "rt_leave_one_out"):
        rows = experiment2[experiment2["model"] == model].set_index("term")["estimate"]
        assert rows["refits"] == "99"
        assert rows["refits_failing_strict_mode"] == "0"


@pytest.mark.parametrize("experiment", [1, 2])
def test_random_effects_hold_the_sds_correlations_and_sizes_of_each_model(repo_root, experiment):
    """Each model's participant SDs, then the correlations of its correlated terms, then the
    residual SD of a linear model, with one count of observations and of participants."""
    path = repo_root / "results" / f"experiment{experiment}" / "random_effects.csv"
    effects = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert list(effects.columns) == RANDOM_COLUMNS
    assert set(effects["experiment"]) == {str(experiment)}
    assert set(zip(effects["model"], effects["set"])) == RANDOM_EFFECT_MODELS[experiment]
    assert set(effects["group"]) <= {"participant", "residual"}
    for _, rows in effects.groupby(["model", "set"], sort=False):
        kind = [0 if g == "participant" and t2 == "" else 1 if g == "participant" else 2
                for g, t2 in zip(rows["group"], rows["term2"])]
        assert kind == sorted(kind)
        assert len(set(zip(rows["observations"], rows["participants"]))) == 1
        assert int(rows["observations"].iloc[0]) > int(rows["participants"].iloc[0]) > 0
        values = rows["estimate"].astype(float)
        assert (values[rows["term2"] == ""] >= 0).all()
        assert (values[rows["term2"] != ""].abs() <= 1).all()
        assert (rows.loc[rows["group"] == "residual", "term1"] == "").all()
