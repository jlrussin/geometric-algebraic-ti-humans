"""Table schemas, the data directory, validation, the manifest, the codebooks, and the synthetic
tables."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

import pandas as pd
import pytest
import yaml

from geo_alg_ti_humans import tables

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")

# Rows of each table, and people in each experiment.
SIZES = {
    ("experiment1", "sessions"): 74,
    ("experiment1", "trials"): 10621,
    ("experiment2", "sessions"): 134,
    ("experiment2", "trials"): 5747,
    ("experiment2", "questionnaire"): 118,
}
PEOPLE = {"experiment1": 65, "experiment2": 132}

# The assignment rows of the Experiment 2 participants analyzed under the all-finishers rules
# (a superset of the retained participants), in the order of their participant keys. Plots
# draw each participant's jitter in this order.
EXPERIMENT2_KEY_ORDER = (
    55, 58, 61, 62, 60, 65, 57, 64, 68, 69, 70, 71, 72, 73, 67, 75, 77, 78, 82, 83, 84, 85, 87,
    88, 92, 89, 86, 97, 90, 98, 80, 99, 101, 100, 103, 102, 108, 112, 110, 111, 114, 113, 116,
    115, 117, 118, 120, 121, 119, 122, 163, 128, 129, 131, 133, 134, 140, 141, 143, 139, 146,
    144, 147, 148, 153, 154, 157, 167, 169, 170, 173, 177, 180, 145, 191, 195, 194, 183, 198,
    196, 193, 199, 204, 203, 161, 207, 209, 210, 213, 214, 188, 219, 221, 217, 225, 218, 192,
    237, 228, 233, 232, 240, 234, 245, 246, 249, 251, 253, 256, 266, 265, 258, 270, 272, 269,
)


def _empty(experiment: str, table: str) -> pd.DataFrame:
    schema = tables.SCHEMAS[(experiment, table)]
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in schema.items()})


def _questionnaire(answers: list[str | None]) -> pd.DataFrame:
    n = len(answers)
    return tables.validate(pd.DataFrame({
        "participant": pd.array([f"P{i:03d}" for i in range(1, n + 1)], dtype="string"),
        "session_index": pd.array([1] * n, dtype="Int64"),
        "condition": pd.array(["congruent"] * n, dtype="string"),
        "statements_true": pd.array(answers, dtype="string"),
        "knowledge_use": pd.array(["Never"] * n, dtype="string"),
    }), "questionnaire", "experiment2")


def _write_manifest(root, names):
    entries = {name: tables._entry(root / name) for name in names}
    (root / tables.MANIFEST).write_text(yaml.safe_dump(entries, sort_keys=False))


def _codebook_rows(repo_root, experiment, table):
    text = (repo_root / "data" / experiment / f"{table}.md").read_text()
    return re.findall(r"^\| `([a-z0-9_]+)` \| ([A-Za-z0-9]+) \|", text, flags=re.MULTILINE)


def test_schemas_cover_every_table():
    """Two tables per experiment, plus the Experiment 2 questionnaire."""
    assert set(tables.SCHEMAS) == {
        ("experiment1", "sessions"),
        ("experiment1", "trials"),
        ("experiment2", "sessions"),
        ("experiment2", "trials"),
        ("experiment2", "questionnaire"),
    }


def test_every_table_starts_with_the_person_and_session_keys():
    """Rows identify a person and that person's session before anything else."""
    for key, schema in tables.SCHEMAS.items():
        assert tuple(schema)[:2] == tables.SESSION_KEY == ("participant", "session_index"), key


def test_data_root_follows_the_environment_variable(monkeypatch, tmp_path):
    """``GEO_ALG_TI_HUMANS_DATA`` overrides the repository's ``data/`` directory."""
    monkeypatch.setenv(tables.DATA_ENV, str(tmp_path))
    assert tables.data_root() == tmp_path
    monkeypatch.delenv(tables.DATA_ENV)
    assert tables.data_root().name == "data"


def test_data_root_refuses_to_guess_outside_a_checkout(monkeypatch, tmp_path):
    """Without the variable and without a repository checkout, the data directory is unknown."""
    monkeypatch.delenv(tables.DATA_ENV, raising=False)
    monkeypatch.setattr(tables, "REPO_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        tables.data_root()


def test_validate_accepts_a_frame_with_the_schema():
    """A frame with exactly the schema's columns and dtypes passes unchanged."""
    df = _empty("experiment2", "questionnaire")
    assert tables.validate(df, "questionnaire", "experiment2") is df


def test_validate_rejects_missing_or_unexpected_columns():
    """A missing column or an undeclared one fails validation."""
    df = _empty("experiment2", "questionnaire")
    with pytest.raises(ValueError):
        tables.validate(df.drop(columns="condition"), "questionnaire", "experiment2")
    with pytest.raises(ValueError):
        tables.validate(df.assign(extra=1), "questionnaire", "experiment2")


def test_validate_rejects_a_wrong_dtype():
    """A column whose dtype differs from the schema fails validation."""
    df = _empty("experiment2", "questionnaire").astype({"session_index": "float64"})
    with pytest.raises(ValueError):
        tables.validate(df, "questionnaire", "experiment2")


def test_validate_rejects_columns_out_of_order():
    """The schema fixes the column order."""
    df = _empty("experiment2", "questionnaire")
    with pytest.raises(ValueError, match="order"):
        tables.validate(df[df.columns[::-1]], "questionnaire", "experiment2")


def test_manifest_digest_detects_a_changed_table(tmp_path):
    """Editing a table after the manifest was written makes the check fail, naming the table."""
    name = "experiment2/questionnaire.parquet"
    (tmp_path / "experiment2").mkdir()
    _questionnaire(["All of them", None]).to_parquet(tmp_path / name, index=False)
    _write_manifest(tmp_path, [name])
    manifest = tables.manifest_digest(tmp_path)
    assert manifest[name]["rows"] == 2
    assert manifest[name]["columns"] == list(tables.SCHEMAS[("experiment2", "questionnaire")])
    pd.testing.assert_frame_equal(
        tables.load("questionnaire", "experiment2", root=tmp_path), _questionnaire(
            ["All of them", None]))

    _questionnaire(["All of them", "Few of them"]).to_parquet(tmp_path / name, index=False)
    with pytest.raises(ValueError, match="experiment2/questionnaire.parquet"):
        tables.manifest_digest(tmp_path)
    with pytest.raises(ValueError, match="experiment2/questionnaire.parquet"):
        tables.load("questionnaire", "experiment2", root=tmp_path)


def test_manifest_digest_requires_every_listed_table_and_only_those(tmp_path):
    """A listed table that is missing, or a table the manifest does not list, fails the check."""
    (tmp_path / "experiment2").mkdir()
    first = "experiment2/questionnaire.parquet"
    _questionnaire(["None of them"]).to_parquet(tmp_path / first, index=False)
    _write_manifest(tmp_path, [first])
    _questionnaire(["Most of them"]).to_parquet(tmp_path / "experiment2/extra.parquet", index=False)
    with pytest.raises(ValueError, match="extra.parquet"):
        tables.manifest_digest(tmp_path)
    (tmp_path / "experiment2/extra.parquet").unlink()
    (tmp_path / "experiment2/deeper").mkdir()
    _questionnaire(["Few of them"]).to_parquet(tmp_path / "experiment2/deeper/t.parquet")
    with pytest.raises(ValueError, match="deeper/t.parquet"):
        tables.manifest_digest(tmp_path)
    (tmp_path / "experiment2/deeper/t.parquet").unlink()
    (tmp_path / first).unlink()
    with pytest.raises(FileNotFoundError):
        tables.manifest_digest(tmp_path)


def test_manifest_entries_must_be_mappings(tmp_path):
    """An entry without its digest, rows and columns is a malformed manifest."""
    (tmp_path / tables.MANIFEST).write_text("experiment2/questionnaire.parquet: abc\n")
    with pytest.raises(ValueError, match="not a mapping"):
        tables.manifest_digest(tmp_path)


def test_codebooks_list_the_schema_columns_and_types(repo_root):
    """Each codebook ``data/<experiment>/<table>.md`` lists the schema's columns, in order.

    A codebook is a Markdown table with one row per column: the column name in backticks, then
    the column's dtype in the schema.
    """
    for (experiment, table), schema in tables.SCHEMAS.items():
        assert _codebook_rows(repo_root, experiment, table) == list(schema.items()), table


def test_manifest_lists_every_table_with_the_schema_columns(repo_root):
    """The committed manifest lists each table once, with the schema's columns in order."""
    manifest = yaml.safe_load((repo_root / "data" / tables.MANIFEST).read_text())
    assert set(manifest) == {f"{e}/{t}.parquet" for e, t in tables.SCHEMAS}
    for (experiment, table), schema in tables.SCHEMAS.items():
        entry = manifest[f"{experiment}/{table}.parquet"]
        assert entry["columns"] == list(schema), (experiment, table)
        assert entry["rows"] == SIZES[(experiment, table)], (experiment, table)
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])


# The synthetic tables

def _assert_rows_belong_to_sessions(rows, sessions, label):
    """Every row joins one session and carries that session's assignment and condition."""
    keys = list(tables.SESSION_KEY)
    shared = [c for c in ("assignment_id", "condition") if c in rows.columns]
    merged = rows[keys + shared].merge(sessions[keys + shared], on=keys, how="left",
                                       suffixes=("", "_session"), indicator=True)
    assert (merged["_merge"] == "both").all(), label
    for c in shared:
        assert (merged[c] == merged[f"{c}_session"]).all(), (label, c)


def _assert_timeouts_have_no_response(trials, response):
    """A timeout has no response and no response time and is never correct."""
    timed_out = trials["is_timed_out"].astype(bool)
    assert (trials[response].isna() == timed_out).all()
    assert (trials["rt"].isna() == timed_out).all()
    assert not trials.loc[timed_out, "is_correct"].any()


def test_synthetic_tables_load_and_agree_with_one_another(synthetic_root):
    """The synthetic tables match their manifest and schemas, and hold together as the data do.

    Every trial and questionnaire row belongs to a session with that session's values; question
    counts, questionnaire rows and stream offsets follow the trials; a timeout has no response
    and no response time and is never correct, and each experiment has timeouts.
    """
    assert set(tables.manifest_digest(synthetic_root)) == {
        f"{e}/{t}.parquet" for e, t in tables.SCHEMAS}
    keys = list(tables.SESSION_KEY)
    loaded = {(e, t): tables.load(t, e, root=synthetic_root) for e, t in tables.SCHEMAS}
    for experiment in tables.EXPERIMENTS:
        sessions = loaded[(experiment, "sessions")]
        assert not sessions.duplicated(keys).any()
        assert (sessions.groupby("participant")["session_index"].min() == 1).all()
        for table in ("trials", "questionnaire"):
            if (experiment, table) not in loaded:
                continue
            _assert_rows_belong_to_sessions(loaded[(experiment, table)], sessions,
                                            (experiment, table))
        trials = loaded[(experiment, "trials")]
        n = trials.groupby(keys).size().reindex(pd.MultiIndex.from_frame(sessions[keys]),
                                                 fill_value=0).to_numpy()
        if experiment == "experiment1":
            assert (sessions["stream_offset"].isna() == (n == 0)).all()
            assert (sessions["stream_offset"].dropna() == 0).all()
            assert sorted(sessions["start_order"]) == list(range(1, len(sessions) + 1))
        else:
            assert (sessions["n_main_questions"].to_numpy() == n).all()
            answered = loaded[(experiment, "questionnaire")].set_index(keys).index
            completed = sessions[sessions["is_completed"].astype(bool)].set_index(keys).index
            assert answered.equals(completed)
        assert trials["is_timed_out"].astype(bool).any()
        _assert_timeouts_have_no_response(
            trials, "response" if experiment == "experiment1" else "response_side")


@needs_node
def test_make_tables_writes_the_committed_synthetic_tables(repo_root, synthetic_root, tmp_path):
    """``tests/synthetic/make_tables.py`` writes the committed tables: the same columns, types
    and values, and a manifest with the same rows and columns."""
    result = subprocess.run(
        [sys.executable, str(synthetic_root / "make_tables.py"), "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    names = [*(f"{e}/{t}.parquet" for e, t in tables.SCHEMAS), tables.MANIFEST]
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == sorted(names)
    for experiment, table in tables.SCHEMAS:
        pd.testing.assert_frame_equal(tables.load(table, experiment, root=tmp_path),
                                      tables.load(table, experiment, root=synthetic_root))

    def without_digests(root):
        manifest = yaml.safe_load((root / tables.MANIFEST).read_text())
        return {name: {k: v for k, v in entry.items() if k != "sha256"}
                for name, entry in manifest.items()}

    assert without_digests(tmp_path) == without_digests(synthetic_root)


def test_every_table_loads_and_validates(data_root):
    """Every table matches the manifest and its schema; each has its expected number of rows."""
    assert set(tables.manifest_digest(data_root)) == {f"{e}/{t}.parquet" for e, t in SIZES}
    for experiment, table in tables.SCHEMAS:
        df = tables.load(table, experiment, root=data_root)
        assert len(df) == SIZES[(experiment, table)], (experiment, table)


def test_person_keys_are_contiguous(data_root):
    """``participant`` runs P001, P002, ... with no gaps, and ``session_index`` starts at 1."""
    for experiment in tables.EXPERIMENTS:
        sessions = tables.load("sessions", experiment, root=data_root)
        keys = sorted(sessions["participant"].unique())
        assert keys == [f"P{i:03d}" for i in range(1, len(keys) + 1)]
        assert len(keys) == PEOPLE[experiment]
        assert (sessions.groupby("participant")["session_index"].min() == 1).all()
        n = sessions.groupby("participant")["session_index"].agg(["max", "size", "nunique"])
        assert (n["max"] == n["size"]).all() and (n["size"] == n["nunique"]).all()


def test_rows_point_to_a_session_of_the_same_assignment(data_root):
    """Every trial and questionnaire row belongs to one session, with that session's values."""
    for experiment in tables.EXPERIMENTS:
        sessions = tables.load("sessions", experiment, root=data_root)
        keys = list(tables.SESSION_KEY)
        assert not sessions.duplicated(keys).any()
        for table in ("trials", "questionnaire"):
            if (experiment, table) not in tables.SCHEMAS:
                continue
            _assert_rows_belong_to_sessions(tables.load(table, experiment, root=data_root),
                                            sessions, (experiment, table))


def test_experiment2_question_counts_agree_with_the_trials(data_root):
    """``n_main_questions`` equals the session's rows in the trials table."""
    sessions = tables.load("sessions", "experiment2", root=data_root)
    trials = tables.load("trials", "experiment2", root=data_root)
    n = trials.groupby(list(tables.SESSION_KEY)).size()
    got = sessions.set_index(list(tables.SESSION_KEY))["n_main_questions"]
    assert (got == n.reindex(got.index, fill_value=0)).all()


def test_experiment1_stream_offsets(data_root):
    """Sessions with task trials replay with 11, 17 or 19 extra draws; the others have none."""
    sessions = tables.load("sessions", "experiment1", root=data_root)
    trials = tables.load("trials", "experiment1", root=data_root)
    with_trials = sessions.set_index(list(tables.SESSION_KEY)).index.isin(
        trials.set_index(list(tables.SESSION_KEY)).index)
    assert (sessions["stream_offset"].isna() == ~with_trials).all()
    assert sessions["stream_offset"].value_counts().to_dict() == {11: 42, 17: 15, 19: 4}


def test_experiment1_start_order_numbers_the_sessions_by_start(data_root):
    """``start_order`` numbers the 74 sessions once each, consistently with ``session_index``."""
    sessions = tables.load("sessions", "experiment1", root=data_root)
    assert sorted(sessions["start_order"]) == list(range(1, len(sessions) + 1))
    by_start = sessions.sort_values("start_order")
    assert (by_start.groupby("participant")["session_index"].diff().dropna() == 1).all()


def test_experiment1_keys_follow_the_primary_sessions_assignments(data_root):
    """People are numbered in the order of their primary session's ``assignment_id``.

    The primary session has the most saved rows (ties: the lowest ``assignment_id``). The
    analysis keeps only primary sessions, so its participants sort by key as by ``assignment_id``.
    """
    sessions = tables.load("sessions", "experiment1", root=data_root)
    assert sessions["assignment_id"].is_unique
    primary = (sessions.sort_values(["n_saved_rows", "assignment_id"], ascending=[False, True])
               .groupby("participant").head(1).sort_values("participant"))
    assert primary["assignment_id"].is_monotonic_increasing


def test_experiment2_keys_follow_the_record_order(data_root):
    """Each assignment row belongs to one person, and the keys of the all-finishers participants
    ascend in the order of ``EXPERIMENT2_KEY_ORDER``."""
    sessions = tables.load("sessions", "experiment2", root=data_root)
    person = sessions.groupby("assignment_id")["participant"].agg(set)
    assert (person.map(len) == 1).all()
    keys = [next(iter(person[a])) for a in EXPERIMENT2_KEY_ORDER]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)


def test_experiment2_waves_and_rounds(data_root):
    """57 sessions in wave 1; 68 in round 1 and 9 in round 2 of wave 2."""
    sessions = tables.load("sessions", "experiment2", root=data_root)
    counts = sessions.groupby(["wave", sessions["allocation_round"].fillna(0)]).size().to_dict()
    assert counts == {(1, 0): 57, (2, 1): 68, (2, 2): 9}


def test_timeouts_have_no_response_and_count_as_incorrect(data_root):
    """A timeout has no response and no response time and is never correct."""
    for experiment, response in (("experiment1", "response"), ("experiment2", "response_side")):
        _assert_timeouts_have_no_response(tables.load("trials", experiment, root=data_root),
                                          response)


def test_experiment1_arbitrage_responses_follow_one_ordering(data_root):
    """In the arbitrage test a response follows exactly one of the two orderings."""
    trials = tables.load("trials", "experiment1", root=data_root)
    arbitrage = trials["phase"] == "arbitrage_test"
    for column in ("is_icl_consistent", "is_iwl_consistent"):
        assert trials.loc[~arbitrage, column].isna().all()
    rows = trials[arbitrage & ~trials["is_timed_out"].astype(bool)]
    assert (rows["is_icl_consistent"] != rows["is_iwl_consistent"]).all()
    assert (rows["is_iwl_consistent"] == rows["is_correct"]).all()


def test_experiment1_counts_intervening_distractors_only_where_shown(data_root):
    """Intervening distractors are counted only where the context was shown."""
    trials = tables.load("trials", "experiment1", root=data_root)
    shown = trials["context_display"] == "shown"
    assert trials.loc[~shown.fillna(False), "intervening_distractors"].isna().all()
    learning = trials[(trials["phase"] == "learning") & shown]
    assert set(learning["intervening_distractors"]) == {0, 1, 2}
    assert (trials.loc[shown & (trials["phase"] != "learning"),
                       "intervening_distractors"] == 0).all()
    masked = trials[trials["context_display"] == "masked"]
    assert set(masked["phase"]) == {"learning", "iwl_test"}
