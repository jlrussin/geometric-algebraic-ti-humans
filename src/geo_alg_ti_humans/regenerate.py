"""Replay every session's trial sequence from its assignment and compare it with the saved trials.

Each sequence is rebuilt by the experiment's own code, run in Node by
``experiments/<experiment>/replay.mjs``. Experiment 1 runs in a harness that stands in for the
browser and jsPsych, builds the session for an ``assignment_id``, and emits the planned rows.
Experiment 2's sequence is a pure function of the assignment row, rebuilt from the experiment's
configuration and checked against each session's ``schedule_sha256`` as well as row by row. In
Experiment 1, the deployed sessions drew ``stream_offset`` extra numbers from the seeded random
stream while saving data over the network, between building the stimuli and building the
practice blocks; the replay draws the same number at the same point. An Experiment 1 session that
saved no task trials has nothing to compare. Every Experiment 2 session saved its
``schedule_sha256``, so each is compared, including those that ended before the first question.
Draws made while the session runs, such as the order of comprehension-check options, are not
part of the rebuilt sequence.

The replay prints the rows under the field names the experiment saves. ``DESIGN_COLUMNS`` maps
those fields to the columns of the trials table.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from geo_alg_ti_humans import REPO_ROOT, tables

# Seconds one session's replay may run before it counts as failed.
_REPLAY_TIMEOUT_S = 120

# Saved Experiment 1 phase -> (phase column, is_retry).
_PHASE_MAP = {
    "practice_query": ("practice_query_only", False),
    "practice_query_extra": ("practice_query_only", True),
    "practice_singlehop": ("practice_single_hop", False),
    "practice_singlehop_extra": ("practice_single_hop", True),
    "practice_multihop": ("practice_multihop", False),
    "practice_multihop_extra": ("practice_multihop", True),
    "training": ("learning", False),
    "test_icl": ("icl_test", False),
    "test_iwl": ("iwl_test", False),
    "test_arbitrage": ("arbitrage_test", False),
}


def _task_phase(row: Mapping) -> tuple[str, bool]:
    """The phase column and ``is_retry`` of a saved Experiment 1 row; raises for other phases."""
    phase = row["phase"]
    if phase not in _PHASE_MAP:
        raise RuntimeError(f"phase {phase!r} is not a task phase")
    return _PHASE_MAP[phase]


def _context_display(saved_display: str) -> str | None:
    """The context row as shown: ``shown`` or ``masked`` as saved; null for ``query_only`` (the
    query-only practice, which has no context row)."""
    return None if saved_display == "query_only" else saved_display


def _intervening_distractors(row: Mapping) -> int | None:
    """Distractors displayed between the two queried items.

    The pairs of the displayed chain between the two items, less their symbolic distance; null
    when the chain is masked or absent.
    """
    pairs_between = row.get("context_hops")
    return None if pairs_between is None else pairs_between - row["ordinal_distance"]


# Trials-table column -> its value in a saved row, for every design column a session's plan fixes.
DESIGN_COLUMNS: Mapping[str, Mapping[str, Callable[[Mapping], object]]] = {
    "experiment1": {
        "phase": lambda r: _task_phase(r)[0],
        "is_retry": lambda r: _task_phase(r)[1],
        "symbolic_distance": lambda r: r["ordinal_distance"],
        "query_left": lambda r: r["query_left"],
        "query_right": lambda r: r["query_right"],
        "query_left_rank": lambda r: r["query_left_rank"],
        "query_right_rank": lambda r: r["query_right_rank"],
        "context_display": lambda r: _context_display(r["context_display"]),
        "intervening_distractors": _intervening_distractors,
        "n_context_pairs": lambda r: r.get("num_context_pairs"),
        "displayed_chain": lambda r: r["chain_order_json"],
        "display_slots": lambda r: r["slot_assignment_json"],
        "inserted_distractors": lambda r: r["inserted_distractor_ids_json"],
        "swapped_item": lambda r: r.get("swapped_item_id"),
        "swap_distractor": lambda r: r.get("swap_distractor_id"),
        "icl_ordering": lambda r: r.get("icl_ordering"),
        "icl_consistent_side": lambda r: r.get("icl_consistent_side"),
    },
    "experiment2": {
        "condition": lambda r: r["ordering_type"],
        "question_number": lambda r: r["trial_number"],
        "block": lambda r: r["block_index"],
        "symbolic_distance": lambda r: r["context_distance"],
        "real_world_distance": lambda r: r["knowledge_distance"],
        "question_type": lambda r: r["query_congruence"],
        "item_pair": lambda r: r["item_pair_key"],
        "query_left": lambda r: r["query_left_item"],
        "query_right": lambda r: r["query_right_item"],
        "correct_answer": lambda r: r["correct_answer_context"],
        "real_world_answer": lambda r: r["knowledge_answer"],
        "statements_text": lambda r: r["statements_text_json"],
        "context_ordering": lambda r: r["context_ordering_json"],
    },
}


@dataclass
class Report:
    """The outcome of comparing planned and saved rows for one experiment."""

    experiment: str
    n_sessions: int = 0
    n_matched: int = 0
    n_without_plan: int = 0
    differences: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when sessions were compared, none differed, and every session is accounted for.

        At least one session must have matched its planned rows.
        """
        return (
            self.n_matched > 0
            and not self.differences
            and self.n_matched + self.n_without_plan == self.n_sessions
        )


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        raise FileNotFoundError("Node.js (node) is not on the PATH; the replay needs Node 22")
    return node


def design_frame(experiment: str, rows: list[Mapping]) -> pd.DataFrame:
    """Saved-row records as the design columns of the trials table, with the table's dtypes.

    Raises ``RuntimeError`` for an Experiment 1 row whose phase is not a task phase, and for a
    row without a field that a design column is read from.
    """
    columns = DESIGN_COLUMNS[experiment]
    schema = tables.SCHEMAS[(experiment, "trials")]
    data = {}
    for name, value in columns.items():
        data[name] = []
        for i, r in enumerate(rows, start=1):
            try:
                data[name].append(value(r))
            except KeyError as error:
                raise RuntimeError(f"row {i} has no field {error.args[0]!r}") from None
    return pd.DataFrame({
        name: pd.Series(values, dtype=schema[name]) for name, values in data.items()
    })


def planned_rows(
    experiment: str,
    assignment_id: int,
    stream_offset: int = 0,
    *,
    code_dir: Path | None = None,
) -> pd.DataFrame:
    """The planned rows of one session, built by the experiment's code in Node.

    One row per planned task trial (Experiment 1) or main question (Experiment 2), in session
    order; in Experiment 1 each practice block's retry block is listed once. The columns are the
    design columns of the trials table (``tables.SCHEMAS``); Experiment 2's frame also has the
    session's ``schedule_sha256`` (the same on every row). ``stream_offset`` applies to
    Experiment 1 only. ``code_dir`` is the experiment folder to run (default:
    ``experiments/<experiment>/`` in the repository).

    Raises ``FileNotFoundError`` when the folder has no ``js/`` or Node is not on the PATH,
    ``ValueError`` for a stream offset in Experiment 2, and ``RuntimeError`` when the replay fails,
    runs longer than two minutes, or prints rows that are not the planned rows (no rows, a line
    that is not JSON, or a row ``design_frame`` refuses).
    """
    script = REPO_ROOT / "experiments" / experiment / "replay.mjs"
    code = Path(code_dir) if code_dir is not None else script.parent
    if not (code / "js").is_dir():
        raise FileNotFoundError(f"no experiment code to replay: {code / 'js'} does not exist")
    command = [_node(), str(script), "--assignment-id", str(assignment_id), "--code", str(code)]
    if experiment == "experiment1":
        command += ["--stream-offset", str(stream_offset)]
    elif stream_offset:
        raise ValueError(f"{experiment} has no stream offset")
    replay = f"replaying {experiment} assignment {assignment_id}"
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False,
                                timeout=_REPLAY_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{replay} did not finish within {_REPLAY_TIMEOUT_S} s") from None
    if result.returncode != 0:
        raise RuntimeError(f"{replay} failed: {result.stderr.strip()}")
    try:
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{replay} printed a line that is not JSON: {error}") from None
    if not rows:
        raise RuntimeError(f"{replay} printed no rows")
    try:
        frame = design_frame(experiment, rows)
    except RuntimeError as error:
        raise RuntimeError(f"{replay}: {error}") from None
    if experiment != "experiment1":
        digests = [r.get("schedule_sha256") for r in rows]
        frame["schedule_sha256"] = pd.Series(digests, dtype="string")
    return frame


def _show(value) -> str:
    if pd.isna(value):
        return "null"
    return repr(value) if isinstance(value, str) else str(value)


def _same(a, b) -> bool:
    a_na, b_na = pd.isna(a), pd.isna(b)
    return bool(a_na and b_na) or (not a_na and not b_na and a == b)


def compare(planned: pd.DataFrame, saved: pd.DataFrame) -> list[str]:
    """Compare one session's planned rows with its saved rows, design column by design column.

    Rows are compared in order, over every column of ``planned``. Returns one line per difference
    (row, column, planned value, saved value); empty if none. A column missing from ``saved``
    and a difference in the number of rows are one line each.
    """
    lines = []
    if len(planned) != len(saved):
        lines.append(f"rows: {len(planned)} planned vs {len(saved)} saved")
    columns = [c for c in planned.columns if c in saved.columns]
    lines += [f"column {c}: not in the saved rows" for c in planned.columns if c not in columns]
    for i, (p, s) in enumerate(zip(planned[columns].itertuples(index=False),
                                   saved[columns].itertuples(index=False)), start=1):
        for column, a, b in zip(columns, p, s):
            if not _same(a, b):
                lines.append(f"row {i}, {column}: {_show(a)} vs {_show(b)}")
    return lines


def realized_order(planned: pd.DataFrame, saved: pd.DataFrame) -> pd.DataFrame:
    """Experiment 1's planned rows in the order a session showed them, as far as it saved rows.

    Each practice retry block is repeated as many times as the session ran it (zero to two),
    judged from the saved rows of that block; the result is cut at the number of saved rows.
    """
    keys = list(zip(planned["phase"], planned["is_retry"]))
    parts, start = [], 0
    for end in range(1, len(keys) + 1):
        if end < len(keys) and keys[end] == keys[start]:
            continue
        rows = planned.iloc[start:end]
        phase, is_retry = keys[start]
        repeats = 1
        if is_retry:
            ran = int(((saved["phase"] == phase) & saved["is_retry"]).sum())
            repeats = -(-ran // len(rows))
        parts += [rows] * repeats
        start = end
    out = pd.concat(parts, ignore_index=True) if parts else planned.iloc[:0]
    return out.iloc[: len(saved)].reset_index(drop=True)


def _session_differences(
    experiment: str,
    session,
    saved: pd.DataFrame,
    code_dir: Path | None,
) -> list[str] | None:
    """Differences of one session, or None when it has no planned rows to compare.

    An Experiment 1 session without saved task trials has none, and then has no stream offset.
    """
    if experiment == "experiment1":
        if saved.empty:
            if pd.isna(session.stream_offset):
                return None
            return ["no saved task trials but a stream offset"]
        if pd.isna(session.stream_offset):
            return ["has planned rows but no stream offset"]
        planned = planned_rows(experiment, int(session.assignment_id),
                               int(session.stream_offset), code_dir=code_dir)
        saved = saved.sort_values("trial_index").reset_index(drop=True)
        return compare(realized_order(planned, saved), saved)
    if pd.isna(session.schedule_sha256) and saved.empty:
        return None
    planned = planned_rows(experiment, int(session.assignment_id), code_dir=code_dir)
    digest = planned.pop("schedule_sha256").iloc[0]
    lines = []
    if not _same(digest, session.schedule_sha256):
        lines.append(f"schedule_sha256: {_show(digest)} vs {_show(session.schedule_sha256)}")
    # Planned questions up to the last saved one, so a missing question shows as a difference.
    saved = saved.sort_values("question_number").reset_index(drop=True)
    last = saved["question_number"].max() if not saved.empty else 0
    planned = planned[planned["question_number"] <= last]
    return lines + compare(planned.reset_index(drop=True), saved)


def run(
    experiment: str,
    tables_root: Path | None = None,
    *,
    code_dir: Path | None = None,
) -> Report:
    """Replay and compare every session of ``experiment`` in the tables under ``tables_root``.

    ``tables_root`` defaults to ``tables.data_root()``; ``code_dir`` is the experiment folder to
    replay (default: ``experiments/<experiment>/``). Sessions are replayed in parallel, one Node
    process each. A replay that fails raises (see ``planned_rows``) instead of being reported as
    a difference, and the sessions not yet started are not replayed.
    """
    sessions = tables.load("sessions", experiment, tables_root)
    trials = tables.load("trials", experiment, tables_root)
    by_session = dict(tuple(trials.groupby(list(tables.SESSION_KEY), sort=False)))
    empty = trials.iloc[:0]

    def one(session):
        saved = by_session.get((session.participant, session.session_index), empty)
        return session, _session_differences(experiment, session, saved, code_dir)

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        futures = [pool.submit(one, s) for s in sessions.itertuples(index=False)]
        done, _ = wait(futures, return_when=FIRST_EXCEPTION)
        failed = [f for f in futures if f in done and f.exception() is not None]
        if failed:
            # Cancel the replays not yet started, wait for the running ones, then raise.
            pool.shutdown(cancel_futures=True)
            failed[0].result()

    report = Report(experiment)
    for session, lines in (f.result() for f in futures):
        report.n_sessions += 1
        if lines is None:
            report.n_without_plan += 1
        elif not lines:
            report.n_matched += 1
        else:
            name = (f"{session.participant} session {session.session_index} "
                    f"(assignment {session.assignment_id})")
            report.differences += [f"{name}: {line}" for line in lines]
    return report
