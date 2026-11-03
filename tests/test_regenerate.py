"""Replaying every session's trial sequence and comparing it with the saved trials."""

from __future__ import annotations

import json
import shutil
import subprocess
import time

import pandas as pd
import pytest

from geo_alg_ti_humans import REPO_ROOT, regenerate, tables

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")


def _experiment1_saved_row(phase, **fields):
    """A saved Experiment 1 task row with the design fields set to neutral values."""
    row = {
        "phase": phase, "ordinal_distance": 1, "query_left": "cup", "query_right": "fork",
        "query_left_rank": 2, "query_right_rank": 3, "context_display": "shown",
        "context_hops": 1, "num_context_pairs": 6, "chain_order_json": "[]",
        "slot_assignment_json": "[]", "inserted_distractor_ids_json": "[]",
        "swapped_item_id": None, "swap_distractor_id": None, "icl_ordering": None,
        "icl_consistent_side": None,
    }
    row.update(fields)
    return row


def test_report_is_ok_only_when_every_session_is_accounted_for():
    """A report is ok only if a session matched, none differed, and each matched or had no plan."""
    assert regenerate.Report("experiment1", n_sessions=3, n_matched=2, n_without_plan=1).ok
    assert not regenerate.Report("experiment1").ok
    assert not regenerate.Report("experiment1", n_sessions=2, n_without_plan=2).ok
    assert not regenerate.Report("experiment1", n_sessions=3, n_matched=2).ok
    differing = regenerate.Report(
        "experiment1", n_sessions=1, n_matched=1, differences=["row 5, symbolic_distance: 2 vs 3"])
    assert not differing.ok


def test_compare_reports_a_changed_design_value():
    """Changing one design value in the saved rows produces exactly one difference line."""
    planned = pd.DataFrame({"question_number": [1, 2, 3], "symbolic_distance": [1, 4, 6]})
    saved = planned.copy()
    saved.loc[1, "symbolic_distance"] = 5
    assert regenerate.compare(planned, planned) == []
    assert len(regenerate.compare(planned, saved)) == 1


def test_compare_treats_two_nulls_as_equal():
    """A null matches a null and nothing else."""
    planned = pd.DataFrame({"swapped_item": pd.Series(["cup", None], dtype="string")})
    assert regenerate.compare(planned, planned.copy()) == []
    saved = pd.DataFrame({"swapped_item": pd.Series(["cup", "fork"], dtype="string")})
    assert regenerate.compare(planned, saved) == ["row 2, swapped_item: null vs 'fork'"]


def test_compare_reports_missing_rows_and_columns():
    """A different number of rows and a column the saved rows lack are one line each."""
    planned = pd.DataFrame({"block": [1, 1, 2], "symbolic_distance": [1, 2, 3]})
    saved = pd.DataFrame({"block": [1, 1]})
    assert regenerate.compare(planned, saved) == [
        "rows: 3 planned vs 2 saved", "column symbolic_distance: not in the saved rows"]


def test_experiment1_saved_fields_map_to_the_design_columns():
    """Phases, retries, the context display and intervening distractors follow the name map."""
    rows = [
        _experiment1_saved_row("practice_query_extra", context_display="query_only",
                               context_hops=None, num_context_pairs=0),
        _experiment1_saved_row("training", context_hops=3),
        _experiment1_saved_row("test_icl", ordinal_distance=4, context_hops=4, icl_ordering=2),
        _experiment1_saved_row("test_iwl", context_display="masked", context_hops=None),
    ]
    frame = regenerate.design_frame("experiment1", rows)
    schema = tables.SCHEMAS[("experiment1", "trials")]
    assert all(str(frame[c].dtype) == schema[c] for c in frame.columns)
    assert frame["phase"].tolist() == ["practice_query_only", "learning", "icl_test", "iwl_test"]
    assert frame["is_retry"].tolist() == [True, False, False, False]
    assert frame["context_display"].tolist() == [pd.NA, "shown", "shown", "masked"]
    assert frame["intervening_distractors"].tolist() == [pd.NA, 2, 0, pd.NA]
    assert frame["icl_ordering"].tolist() == [pd.NA, pd.NA, 2, pd.NA]


def test_experiment2_saved_fields_map_to_the_design_columns():
    """Every design column of an Experiment 2 question comes from its saved field."""
    row = {
        "ordering_type": "shuffled", "trial_number": 7, "block_index": 1, "context_distance": 3,
        "knowledge_distance": 5, "query_congruence": "conflict", "item_pair_key": "ant|cat",
        "query_left_item": "cat", "query_right_item": "ant", "correct_answer_context": "right",
        "knowledge_answer": "left", "statements_text_json": "[]", "context_ordering_json": "[]",
    }
    frame = regenerate.design_frame("experiment2", [row])
    assert frame.iloc[0].to_dict() == {
        "condition": "shuffled", "question_number": 7, "block": 1, "symbolic_distance": 3,
        "real_world_distance": 5, "question_type": "conflict", "item_pair": "ant|cat",
        "query_left": "cat", "query_right": "ant", "correct_answer": "right",
        "real_world_answer": "left", "statements_text": "[]", "context_ordering": "[]",
    }


def test_realized_order_repeats_each_retry_block_as_often_as_it_ran():
    """A retry block run twice appears twice; the sequence stops where the saved rows stop."""
    planned = regenerate.design_frame("experiment1", [
        _experiment1_saved_row("practice_singlehop", query_left="a"),
        _experiment1_saved_row("practice_singlehop_extra", query_left="b"),
        _experiment1_saved_row("practice_singlehop_extra", query_left="c"),
        _experiment1_saved_row("practice_multihop_extra", query_left="d"),
        _experiment1_saved_row("training", query_left="e"),
        _experiment1_saved_row("training", query_left="f"),
    ])
    saved = planned.iloc[[0, 1, 2, 1, 2, 4]].reset_index(drop=True)
    realized = regenerate.realized_order(planned, saved)
    assert realized["query_left"].tolist() == ["a", "b", "c", "b", "c", "e"]
    assert regenerate.compare(realized, saved) == []


def _serve_tables(monkeypatch, **frames):
    """Make ``tables.load`` return ``frames[table]`` for every experiment."""
    monkeypatch.setattr(tables, "load", lambda table, experiment, root=None: frames[table])


def _sessions_and_trials(experiment, planned):
    """Tables of three sessions: one matching its plan, one without planned rows, one differing."""
    sessions = pd.DataFrame({
        "participant": ["P001", "P002", "P003"],
        "session_index": [1, 1, 1],
        "assignment_id": [0, 1, 2],
        "stream_offset": pd.Series([11, None, 17], dtype="Int64"),
        "schedule_sha256": ["d0", None, "d2"],
    })
    first = planned.assign(participant="P001", session_index=1, trial_index=[1, 2])
    if experiment == "experiment1":
        third = first.assign(participant="P003", query_left=["fork", "fork"])
    else:
        third = first.assign(participant="P003")
    return sessions, pd.concat([first, third], ignore_index=True)


@pytest.mark.parametrize("experiment", ["experiment1", "experiment2"])
def test_run_accounts_for_every_session(monkeypatch, experiment):
    """Matched, without planned rows, or differing: the report counts each session once."""
    if experiment == "experiment1":
        planned = regenerate.design_frame("experiment1", [
            _experiment1_saved_row("training"), _experiment1_saved_row("training")])
    else:
        planned = pd.DataFrame({"question_number": [1, 2], "query_left": ["cup", "fork"]})
    sessions, trials = _sessions_and_trials(experiment, planned)
    _serve_tables(monkeypatch, sessions=sessions, trials=trials)
    calls = []

    def fake_planned_rows(exp, assignment_id, stream_offset=0, *, code_dir=None):
        calls.append((assignment_id, stream_offset))
        if exp == "experiment1":
            return planned.copy()
        return planned.assign(schedule_sha256="d0")

    monkeypatch.setattr(regenerate, "planned_rows", fake_planned_rows)
    report = regenerate.run(experiment)
    assert (report.n_sessions, report.n_matched, report.n_without_plan) == (3, 1, 1)
    assert not report.ok
    assert all(line.startswith("P003 session 1 (assignment 2): ") for line in report.differences)
    if experiment == "experiment1":
        assert sorted(calls) == [(0, 11), (2, 17)]
        assert len(report.differences) == 2
    else:
        assert report.differences == [
            "P003 session 1 (assignment 2): schedule_sha256: 'd0' vs 'd2'"]


def test_experiment2_reports_a_missing_question(monkeypatch):
    """A missing question is a difference: planned rows are cut at the last saved question."""
    planned = pd.DataFrame({"question_number": [1, 2, 3, 4],
                            "query_left": ["cup", "fork", "ant", "cat"]})
    sessions = pd.DataFrame({
        "participant": ["P001", "P002"],
        "session_index": [1, 1],
        "assignment_id": [0, 1],
        "schedule_sha256": ["d0", "d0"],
    })
    trials = pd.concat([planned.iloc[[0, 1, 3]].assign(participant="P001", session_index=1),
                        planned.iloc[[0, 1]].assign(participant="P002", session_index=1)],
                       ignore_index=True)
    _serve_tables(monkeypatch, sessions=sessions, trials=trials)
    monkeypatch.setattr(regenerate, "planned_rows", lambda exp, assignment_id, *, code_dir=None:
                        planned.assign(schedule_sha256="d0"))
    report = regenerate.run("experiment2")
    assert (report.n_sessions, report.n_matched) == (2, 1)
    assert report.differences[0] == "P001 session 1 (assignment 0): rows: 4 planned vs 3 saved"


def test_run_stops_replaying_after_a_failed_replay(monkeypatch):
    """A failed replay raises without starting the remaining sessions.

    The failure comes while an earlier session is still replaying, so waiting for the sessions
    in order would replay all the others first.
    """
    n = 20
    sessions = pd.DataFrame({
        "participant": [f"P{i + 1:03d}" for i in range(n)],
        "session_index": [1] * n,
        "assignment_id": list(range(n)),
        "schedule_sha256": ["d0"] * n,
    })
    trials = pd.DataFrame({"participant": pd.Series(dtype="string"),
                           "session_index": pd.Series(dtype="Int64"),
                           "question_number": pd.Series(dtype="Int64")})
    _serve_tables(monkeypatch, sessions=sessions, trials=trials)
    monkeypatch.setattr(regenerate.os, "cpu_count", lambda: 2)
    calls = []

    def fake_planned_rows(exp, assignment_id, *, code_dir=None):
        calls.append(assignment_id)
        if assignment_id == 1:
            raise RuntimeError("replaying experiment2 assignment 1 failed")
        time.sleep(0.5 if assignment_id == 0 else 0.02)
        return pd.DataFrame({"question_number": [1], "schedule_sha256": ["d0"]})

    monkeypatch.setattr(regenerate, "planned_rows", fake_planned_rows)
    with pytest.raises(RuntimeError, match="assignment 1 failed"):
        regenerate.run("experiment2")
    assert len(calls) < n // 2


def test_an_experiment1_session_without_task_trials_is_never_matched(monkeypatch):
    """No saved task trials: nothing to compare if it has no stream offset, a difference if it has.

    Nothing is replayed for either session, so neither can count as matched.
    """
    sessions = pd.DataFrame({
        "participant": ["P001", "P002"],
        "session_index": [1, 1],
        "assignment_id": [0, 1],
        "stream_offset": pd.Series([None, 11], dtype="Int64"),
    })
    trials = regenerate.design_frame("experiment1", []).assign(
        participant=pd.Series(dtype="string"), session_index=pd.Series(dtype="Int64"))
    _serve_tables(monkeypatch, sessions=sessions, trials=trials)

    def no_replay(*args, **kwargs):
        raise AssertionError("a session without task trials was replayed")

    monkeypatch.setattr(regenerate, "planned_rows", no_replay)
    report = regenerate.run("experiment1")
    assert (report.n_sessions, report.n_matched, report.n_without_plan) == (2, 0, 1)
    assert report.differences == [
        "P002 session 1 (assignment 1): no saved task trials but a stream offset"]


def test_regenerate_command_fails_on_a_difference_or_a_failed_replay(monkeypatch, capsys):
    """The command returns 0 only when both experiments are ok, and reports a failed replay."""
    from geo_alg_ti_humans import cli

    reports = {
        "experiment1": regenerate.Report(
            "experiment1", n_sessions=2, n_matched=1, n_without_plan=1),
        "experiment2": regenerate.Report("experiment2", n_sessions=1, n_matched=1),
    }
    monkeypatch.setattr(regenerate, "run", lambda experiment: reports[experiment])
    assert cli.main(["regenerate"]) == 0
    reports["experiment2"] = regenerate.Report(
        "experiment2", n_sessions=1, differences=[f"row {i}, block: 1 vs 2" for i in range(25)])
    assert cli.main(["regenerate"]) == 1
    assert "... and 5 more" in capsys.readouterr().out

    def failing(experiment):
        raise FileNotFoundError("no experiment code to replay")

    monkeypatch.setattr(regenerate, "run", failing)
    assert cli.main(["regenerate"]) == 1
    assert "no experiment code to replay" in capsys.readouterr().err


@pytest.mark.parametrize("error", [RuntimeError, KeyError])
def test_regenerate_command_compares_experiment2_after_experiment1_fails(monkeypatch, capsys,
                                                                         error):
    """A failed Experiment 1 replay, or a table without a column it needs, is reported, and
    Experiment 2 is still compared."""
    from geo_alg_ti_humans import cli

    def run(experiment):
        if experiment == "experiment1":
            raise error("replaying experiment1 assignment 3 failed")
        return regenerate.Report(experiment, n_sessions=1, n_matched=1)

    monkeypatch.setattr(regenerate, "run", run)
    assert cli.main(["regenerate"]) == 1
    out, err = capsys.readouterr()
    assert err == "regenerate: experiment1: replaying experiment1 assignment 3 failed\n"
    assert out == ("experiment2: 1 sessions, 1 matched, 0 without planned rows, "
                   "0 differences\n")


def test_planned_rows_fails_when_the_replay_prints_no_rows(monkeypatch, tmp_path):
    """A replay that exits cleanly without rows is a failure, not an empty session."""
    (tmp_path / "js").mkdir()
    _replay_printing(monkeypatch, [])
    with pytest.raises(RuntimeError, match="printed no rows"):
        regenerate.planned_rows("experiment1", 0, code_dir=tmp_path)


def _replay_printing(monkeypatch, lines):
    """Make every replay exit cleanly after printing ``lines``."""
    monkeypatch.setattr(regenerate, "_node", lambda: "node")
    monkeypatch.setattr(regenerate.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, stdout="\n".join(lines), stderr=""))


def test_planned_rows_fails_when_the_replay_runs_too_long(monkeypatch, tmp_path):
    """Each replay has a time limit; running past it is a failure."""
    (tmp_path / "js").mkdir()
    monkeypatch.setattr(regenerate, "_node", lambda: "node")

    def too_long(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(regenerate.subprocess, "run", too_long)
    with pytest.raises(RuntimeError, match="did not finish within"):
        regenerate.planned_rows("experiment1", 0, code_dir=tmp_path)


@pytest.mark.parametrize(("experiment", "line", "message"), [
    ("experiment1", json.dumps(_experiment1_saved_row("questionnaire")), "not a task phase"),
    ("experiment1", json.dumps({k: v for k, v in _experiment1_saved_row("training").items()
                                if k != "ordinal_distance"}), "no field 'ordinal_distance'"),
    ("experiment2", "replay finished", "not JSON"),
])
def test_planned_rows_refuses_unexpected_replay_output(monkeypatch, tmp_path, experiment, line,
                                                       message):
    """A row outside the task phases, a row missing a design field, or a line that is not JSON
    fails with a message naming the assignment."""
    (tmp_path / "js").mkdir()
    _replay_printing(monkeypatch, [line])
    with pytest.raises(RuntimeError, match=f"assignment 3.*{message}"):
        regenerate.planned_rows(experiment, 3, code_dir=tmp_path)


def test_regenerate_command_reports_unexpected_replay_output(monkeypatch, tmp_path, capsys):
    """A replay printing a row outside the task phases ends the command with a message."""
    from geo_alg_ti_humans import cli

    (tmp_path / "experiments" / "experiment1" / "js").mkdir(parents=True)
    monkeypatch.setattr(regenerate, "REPO_ROOT", tmp_path)
    planned = regenerate.design_frame("experiment1", [_experiment1_saved_row("training")] * 2)
    sessions, trials = _sessions_and_trials("experiment1", planned)
    _serve_tables(monkeypatch, sessions=sessions, trials=trials)
    _replay_printing(monkeypatch, [json.dumps(_experiment1_saved_row("questionnaire"))])
    assert cli.main(["regenerate"]) == 1
    assert "regenerate: experiment1: replaying experiment1 assignment" in capsys.readouterr().err


def test_planned_rows_needs_the_experiment_code(tmp_path):
    """Replaying a folder without the experiment's code fails before Node starts."""
    with pytest.raises(FileNotFoundError):
        regenerate.planned_rows("experiment1", 0, code_dir=tmp_path)


# A small experiment in the shape of Experiment 1: it seeds its stream from the assignment, draws
# its stimuli, waits for an image, builds a timeline with one library trial and two trials of its
# own plugin (the second with its delay parameter left to the default), and hands it to jsPsych.
SMALL_EXPERIMENT_PAGE = """<!DOCTYPE html>
<script src="https://unpkg.com/jspsych@8.2.3"></script>
<script src="https://unpkg.com/@jspsych/plugin-html-keyboard-response@2.1.0"></script>
"""
SMALL_EXPERIMENT_CODE = """
class ItemPlugin {
  static info = { name: 'item', parameters: { item: { default: null }, phase: { default: '' },
    delay: { default: 300 } } };
  constructor(jsPsych) { this.jsPsych = jsPsych; }
  trial(display, trial) {
    display.innerHTML = `<p>${trial.item}</p>`;
    this.jsPsych.pluginAPI.setTimeout(() => this.jsPsych.finishTrial({
      item: trial.item, phase: trial.phase, delay: trial.delay, ended_at: performance.now() }),
    trial.delay);
  }
}
async function start() {
  let state = Number(new URLSearchParams(window.location.search).get('assignment'));
  Math.random = () => { state += 1; return state; };
  const stimulus = Math.random();
  await new Promise((done) => { const image = new Image(); image.onload = done; image.src = 'a'; });
  const built = Math.random();
  initJsPsych({}).run([
    { type: jsPsychHtmlKeyboardResponse, stimulus: 'welcome' },
    { timeline: [{ type: ItemPlugin, item: `s${stimulus}`, phase: 'practice', delay: 100 }] },
    { type: ItemPlugin, item: `b${built}`, phase: 'learning' },
  ]);
}
start();
"""


def _run_replay(script, *args):
    """Run a replay script with ``args``; return the rows it printed and its standard error."""
    result = subprocess.run([regenerate._node(), str(script), *args],
                            capture_output=True, text=True, check=True)
    return [json.loads(line) for line in result.stdout.splitlines()], result.stderr


def _linked(tmp_path, script):
    """A symbolic link to ``script`` in a folder of its own, as an installed copy might be."""
    link = tmp_path / "bin" / script.name
    link.parent.mkdir()
    link.symlink_to(script)
    return link


@needs_node
@pytest.mark.parametrize(("offset", "through_link"), [(0, False), (3, False), (3, True)])
def test_experiment1_replay_runs_the_startup_and_each_trial_plugin(tmp_path, offset, through_link):
    """The offset draws fall between the stimuli and the build; each trial runs in its plugin."""
    code = tmp_path / "code"
    (code / "js").mkdir(parents=True)
    (code / "index.html").write_text(SMALL_EXPERIMENT_PAGE)
    (code / "js" / "experiment.js").write_text(SMALL_EXPERIMENT_CODE)
    script = REPO_ROOT / "experiments/experiment1/replay.mjs"
    if through_link:
        script = _linked(tmp_path, script)
    rows, stderr = _run_replay(script, "--assignment-id", "10", "--stream-offset", str(offset),
                               "--code", str(code))
    assert rows == [
        {"item": "s11", "phase": "practice", "delay": 100, "ended_at": 100},
        {"item": f"b{12 + offset}", "phase": "learning", "delay": 300, "ended_at": 300},
    ]
    assert stderr == "seeded draws before the stream offset: 1\n"


# A small experiment in the shape of Experiment 2: one assignment row, and a build that makes two
# main questions and one practice question from it.
SMALL_EXPERIMENT2_LOGIC = (
    "export function resolveAssignmentRow(rows, id) {\n"
    "  return { ...rows.find((r) => r.assignment_id === id) };\n"
    "}\n"
    "export async function buildSession(row, cfg) {\n"
    "  const main = Array.from({ length: cfg.questions }, (_, i) => ({\n"
    "    record: { trial_number: i + 1, ordering_type: row.condition } }));\n"
    "  const practice = [{ record: { trial_number: 0, ordering_type: 'practice' } }];\n"
    "  return { practice, main, schedule_sha256: `digest${row.assignment_id}` };\n"
    "}\n")


def _small_experiment2(tmp_path, logic: str = SMALL_EXPERIMENT2_LOGIC):
    """The folder of a small Experiment 2 whose ``js/trial-logic.js`` is ``logic``."""
    code = tmp_path / "code"
    (code / "js").mkdir(parents=True)
    (code / "data").mkdir()
    (code / "data" / "assignments.json").write_text(json.dumps(
        {"assignments": [{"assignment_id": 4, "condition": "shuffled"}]}))
    (code / "js" / "config.js").write_text(
        "export const CONFIG = { questions: 2 };\nexport function validateConfig() {}\n")
    (code / "js" / "item-tables.js").write_text(
        "export async function loadStimuli() { return { tables: {} }; }\n")
    (code / "js" / "trial-logic.js").write_text(logic)
    return code


@needs_node
@pytest.mark.parametrize("through_link", [False, True])
def test_experiment2_replay_prints_each_question_with_the_schedule_digest(tmp_path, through_link):
    """Each line is a main question's record from the experiment's own build, plus the digest."""
    code = _small_experiment2(tmp_path)
    script = REPO_ROOT / "experiments/experiment2/replay.mjs"
    if through_link:
        script = _linked(tmp_path, script)
    rows, _ = _run_replay(script, "--assignment-id", "4", "--code", str(code))
    assert rows == [
        {"trial_number": 1, "ordering_type": "shuffled", "schedule_sha256": "digest4"},
        {"trial_number": 2, "ordering_type": "shuffled", "schedule_sha256": "digest4"},
    ]


@needs_node
def test_experiment2_replay_names_a_function_the_code_lacks(tmp_path):
    """Code without ``resolveAssignmentRow`` ends the replay with one line naming it."""
    code = _small_experiment2(tmp_path, SMALL_EXPERIMENT2_LOGIC.replace(
        "function resolveAssignmentRow", "function findRow"))
    script = REPO_ROOT / "experiments/experiment2/replay.mjs"
    result = subprocess.run([regenerate._node(), str(script), "--assignment-id", "4", "--code",
                             str(code)], capture_output=True, text=True, check=False)
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == (
        f"replay: {code / 'js' / 'trial-logic.js'} does not export resolveAssignmentRow\n")


@needs_node
def test_experiment2_replay_never_draws_a_row():
    """Without an assignment id the replay fails; it never falls back to a random row."""
    replay = (REPO_ROOT / "experiments/experiment2/replay.mjs").as_uri()
    program = (f"import {{ replay }} from {json.dumps(replay)};\n"
               "for (const id of [null, undefined]) {\n"
               "  try { await replay({ assignmentId: id }); console.log('a row'); }\n"
               "  catch (error) { console.log(error.message); }\n"
               "}\n")
    result = subprocess.run([regenerate._node(), "--input-type=module", "-e", program],
                            capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == ["replay needs an assignment id"] * 2


@needs_node
@pytest.mark.parametrize("experiment", ["experiment1", "experiment2"])
@pytest.mark.parametrize("option", ["--code", "--assignment-id"])
@pytest.mark.parametrize("value", [[], [""], ["--code"]])
def test_replay_refuses_an_option_without_a_value(experiment, option, value):
    """An option given last, given an empty value, or followed by another option has no value:
    the replay ends with a message on standard error."""
    script = REPO_ROOT / "experiments" / experiment / "replay.mjs"
    result = subprocess.run([regenerate._node(), str(script), "--assignment-id", "0", option,
                             *value], capture_output=True, text=True, check=False)
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == f"replay: {option} takes a value\n"


@needs_node
@pytest.mark.parametrize(("experiment", "counts"), [
    ("experiment1", (10, 9, 1)), ("experiment2", (13, 13, 0))])
def test_synthetic_sessions_regenerate(synthetic_root, experiment, counts):
    """The synthetic trials are their assignments' planned trials: every session with trials
    matches, and the one Experiment 1 session without trials has nothing to compare."""
    report = regenerate.run(experiment, synthetic_root)
    assert report.ok, report.differences[:5]
    assert (report.n_sessions, report.n_matched, report.n_without_plan) == counts


@needs_node
def test_experiment1_sessions_regenerate(data_root):
    """All 61 sessions with planned rows match; the other 13 have nothing to compare."""
    report = regenerate.run("experiment1", data_root)
    assert report.ok, report.differences[:5]
    assert (report.n_sessions, report.n_matched, report.n_without_plan) == (74, 61, 13)


@needs_node
def test_experiment2_sessions_regenerate(data_root):
    """All 134 sessions match."""
    report = regenerate.run("experiment2", data_root)
    assert report.ok, report.differences[:5]
    assert (report.n_sessions, report.n_matched) == (134, 134)
