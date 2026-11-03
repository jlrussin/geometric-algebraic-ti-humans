"""Write the synthetic data tables that the tests and ``geo-alg-ti-humans smoke`` run on.

The tables have the columns and types of the data tables (``geo_alg_ti_humans.tables.SCHEMAS``;
the codebooks are in ``data/``) and are written as ``<experiment>/<table>.parquet`` with a
``MANIFEST.yaml``, so ``tables.load(table, experiment, root=Path("tests/synthetic"))`` reads
them. Each session's trials are the planned trials of its assignment, built by the experiment's
own code in Node (``regenerate.planned_rows``), so ``regenerate.run`` reproduces them. Every
session runs as a local session does (stream offset 0) and passes each practice block at the
first attempt, so no retry block runs. The responses are random, drawn from one seeded generator
per experiment: mostly correct, with response times from a lognormal distribution and a few
timeouts.

Experiment 1: ten sessions of nine people, on assignments 0-9. Seven people complete their
session; one of them first started a session that ended during the learning phase. One session
ends when the person fails, on both attempts, the comprehension check that follows the query-only
practice, and one ends before the first trial. The sessions did not start in the order of the
participant keys, which follow each person's primary assignment.

Experiment 2: thirteen sessions of twelve people, on assignments 0-11 (six congruent, six
shuffled). One shuffled participant answers at random. The last person's first session ends after
a few questions; the page was reloaded on the same assignment and the second session is complete.

Run from the repository root, with Node 22 on the PATH:

    uv run python tests/synthetic/make_tables.py [--out DIR]

The tables go to ``tests/synthetic/`` (or ``DIR``). Running the script again writes the same
tables (with the locked package versions, the same bytes).
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
import yaml

from geo_alg_ti_humans import REPO_ROOT, regenerate, tables

OUT_DIR = Path(__file__).resolve().parent
# One generator per experiment: changing one experiment's sessions leaves the other's draws alone.
SEEDS = {"experiment1": 1, "experiment2": 2}

# How a session ended.
COMPLETED = "completed"
UNFINISHED = "unfinished"                       # left partway through
FAILED_COMPREHENSION = "failed_comprehension"   # Experiment 1: after the query-only practice
NO_TRIALS = "no_trials"                         # Experiment 1: before the first trial


class Session1(NamedTuple):
    participant: str
    assignment_id: int
    ending: str = COMPLETED


class Session2(NamedTuple):
    participant: str
    assignment_id: int
    wave: int
    allocation_round: int | None
    # The questionnaire answers of a completed session; None: skipped.
    statements_true: str | None
    knowledge_use: str | None
    ending: str = COMPLETED
    at_random: bool = False       # answers at random instead of mostly correctly


# Sessions in the order they started.
EXPERIMENT1_SESSIONS = (
    Session1("P002", 1),
    Session1("P001", 0),
    Session1("P003", 2, UNFINISHED),
    Session1("P004", 4, FAILED_COMPREHENSION),
    Session1("P003", 3),
    Session1("P005", 5, NO_TRIALS),
    Session1("P007", 7),
    Session1("P006", 6),
    Session1("P008", 8),
    Session1("P009", 9),
)
# The five shuffled participants who pass every rule give each answer to knowledge_use once.
EXPERIMENT2_SESSIONS = (
    Session2("P001", 0, 1, None, "All of them", "Never"),
    Session2("P002", 1, 1, None, "About half of them", "Never"),
    Session2("P003", 2, 1, None, "All of them", "Rarely"),
    Session2("P004", 3, 1, None, "Few of them", "Rarely"),
    Session2("P005", 4, 1, None, "I don't know", "Sometimes"),
    Session2("P006", 5, 1, None, "Most of them", None),
    Session2("P007", 6, 2, 1, "All of them", "Rarely"),
    Session2("P008", 7, 2, 1, "About half of them", "Often"),
    Session2("P009", 8, 2, 1, "Most of them", "Never"),
    Session2("P010", 9, 2, 1, "None of them", "Always"),
    Session2("P011", 10, 2, 1, "I don't know", "Sometimes", at_random=True),
    Session2("P012", 11, 2, 2, None, None, UNFINISHED),
    Session2("P012", 11, 2, 2, "All of them", "Never"),
)

# Experiment 1 screens, numbered by trial_index from 0: SCREENS_BEFORE_PHASE before the first
# trial of each phase (consent, instructions, comprehension checks, practice summaries), a break
# of BREAK_SCREENS after every BREAK_EVERY trials within a phase (js/config.js), and
# SCREENS_AFTER_TESTS after the last test trial (questionnaire, debriefing).
SCREENS_BEFORE_PHASE = 9
BREAK_EVERY = 20
BREAK_SCREENS = 2
SCREENS_AFTER_TESTS = 4
# An unfinished Experiment 1 session ends after this many learning trials.
UNFINISHED_LEARNING_TRIALS = 30
# Experiment 2 records besides the questions: SCREENS_BEFORE_QUESTIONS before the first, a break
# before each later block of questions, and SCREENS_AFTER_QUESTIONS after the last (the
# questionnaire and the end of the session).
SCREENS_BEFORE_QUESTIONS = 5
SCREENS_AFTER_QUESTIONS = 11
# An unfinished Experiment 2 session ends after this many questions.
UNFINISHED_QUESTIONS = 7

# Responses. A trial times out with probability P_TIMEOUT, or when its response time reaches
# the deadline; otherwise the answer is correct with the probability given. In Experiment 1's
# arbitrage test, the response follows the context with probability P_FOLLOW_CONTEXT and the trained
# ordering otherwise. A practice block is drawn again until its accuracy reaches the threshold
# below which a retry block would run.
P_TIMEOUT = 0.01
P_CORRECT_1 = 0.9
P_FOLLOW_CONTEXT = 0.7
PRACTICE_THRESHOLD = 0.7
P_CORRECT_2 = {"congruent": 0.95, "shuffled": 0.85}
P_AT_RANDOM = 0.5
DEADLINE_MS = {"experiment1": 60000.0, "experiment2": 50000.0}
# Response time (ms): the median times the person's speed factor exp(N(0, PERSON_SD)) times
# exp(N(0, RT_SD)). In Experiment 2 the median grows by the factor exp(slope) per unit of
# symbolic distance, centered on the middle distance.
PERSON_SD = 0.25
RT_SD = 0.5
MEDIAN_RT_MS_1 = 3000.0
MEDIAN_RT_MS_2 = {"congruent": 2000.0, "shuffled": 8000.0}
RT_SLOPE_2 = {"congruent": 0.0, "shuffled": 0.08}
MIDDLE_DISTANCE = 3.5

ARBITRAGE = "arbitrage_test"
PRACTICE = ("practice_query_only", "practice_single_hop", "practice_multihop")
_OTHER = {"left": "right", "right": "left"}


def _response_time(rng: np.random.Generator, median_ms: float) -> float:
    return float(round(median_ms * math.exp(RT_SD * rng.normal())))


def _answer(rng: np.random.Generator, intended: str, p: float, median_ms: float,
            deadline_ms: float) -> tuple[str | None, float]:
    """The side chosen (None on a timeout) and the response time (NaN on a timeout)."""
    rt = _response_time(rng, median_ms)
    timed_out = rng.random() < P_TIMEOUT or rt >= deadline_ms
    side = intended if rng.random() < p else _OTHER[intended]
    return (None, math.nan) if timed_out else (side, rt)


def _speed(rng: np.random.Generator, people: dict, participant: str) -> float:
    """The person's speed factor, drawn at their first session."""
    if participant not in people:
        people[participant] = math.exp(PERSON_SD * rng.normal())
    return people[participant]


# Experiment 1

def _trial_indices(phases: Sequence[str]) -> list[int]:
    """The trial_index of each trial of a session, from the phases of its trials in order."""
    indices, index, in_phase = [], -1, 0
    for i, phase in enumerate(phases):
        if i == 0 or phase != phases[i - 1]:
            index += SCREENS_BEFORE_PHASE
            in_phase = 0
        elif in_phase % BREAK_EVERY == 0:
            index += BREAK_SCREENS
        index += 1
        in_phase += 1
        indices.append(index)
    return indices


def _saved_rows(planned: pd.DataFrame, ending: str) -> pd.DataFrame:
    """The planned trials a session saved: no retry block, and only as far as it went."""
    rows = planned[~planned["is_retry"].astype(bool)].reset_index(drop=True)
    if ending == UNFINISHED:
        learning = np.flatnonzero(rows["phase"] == "learning")
        return rows.iloc[: learning[UNFINISHED_LEARNING_TRIALS - 1] + 1]
    if ending == FAILED_COMPREHENSION:
        return rows[rows["phase"] == PRACTICE[0]]
    return rows


def _responses1(rows: pd.DataFrame, rng: np.random.Generator, speed: float) -> pd.DataFrame:
    """``rows`` with the response columns of the trials table."""
    deadline = DEADLINE_MS["experiment1"]
    phases = list(rows["phase"])
    starts = [i for i in range(len(phases)) if i == 0 or phases[i] != phases[i - 1]]
    out = []
    for start, end in zip(starts, [*starts[1:], len(phases)]):
        block = rows.iloc[start:end]
        while True:
            answers = []
            for r in block.itertuples(index=False):
                correct_side = "left" if r.query_left_rank < r.query_right_rank else "right"
                arbitrage = r.phase == ARBITRAGE
                intended = r.icl_consistent_side if arbitrage else correct_side
                p = P_FOLLOW_CONTEXT if arbitrage else P_CORRECT_1
                side, rt = _answer(rng, intended, p, MEDIAN_RT_MS_1 * speed, deadline)
                answers.append({
                    "response": side, "rt": rt, "is_correct": side == correct_side,
                    "is_timed_out": side is None,
                    "is_icl_consistent": side == r.icl_consistent_side if arbitrage else None,
                    "is_iwl_consistent": side == correct_side if arbitrage else None,
                })
            accuracy = np.mean([a["is_correct"] for a in answers])
            if block["phase"].iloc[0] not in PRACTICE or accuracy >= PRACTICE_THRESHOLD:
                break
        out += answers
    return pd.concat([rows, pd.DataFrame(out, index=rows.index)], axis=1)


def experiment1(rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """The sessions and trials tables of Experiment 1."""
    path = REPO_ROOT / "experiments" / "experiment1" / "data" / "assignments.json"
    test_orders = {row["assignment_id"]: ",".join(row["test_block_order"])
                   for row in json.loads(path.read_text())["assignments"]}
    sessions, trials, people, count = [], [], {}, {}
    for start_order, s in enumerate(EXPERIMENT1_SESSIONS, start=1):
        count[s.participant] = count.get(s.participant, 0) + 1
        key = {"participant": s.participant, "session_index": count[s.participant],
               "assignment_id": s.assignment_id}
        speed = _speed(rng, people, s.participant)
        n_saved_rows, stream_offset = 1, None
        if s.ending != NO_TRIALS:
            planned = regenerate.planned_rows("experiment1", s.assignment_id, stream_offset=0)
            rows = _saved_rows(planned, s.ending)
            rows = rows.assign(trial_index=_trial_indices(list(rows["phase"])))
            trials.append(_responses1(rows, rng, speed).assign(**key))
            after = {COMPLETED: SCREENS_AFTER_TESTS, UNFINISHED: 0,
                     FAILED_COMPREHENSION: SCREENS_BEFORE_PHASE}[s.ending]
            n_saved_rows = int(rows["trial_index"].iloc[-1]) + 1 + after
            stream_offset = 0
        sessions.append({
            **key, "start_order": start_order, "test_order": test_orders[s.assignment_id],
            "is_completed": s.ending in (COMPLETED, FAILED_COMPREHENSION),
            "failed_comprehension": {COMPLETED: False, FAILED_COMPREHENSION: True}.get(s.ending),
            "n_saved_rows": n_saved_rows, "stream_offset": stream_offset,
        })
    return {
        "sessions": pd.DataFrame(sessions),
        "trials": pd.concat(trials, ignore_index=True),
    }


# Experiment 2

def experiment2(rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """The sessions, trials and questionnaire tables of Experiment 2."""
    deadline = DEADLINE_MS["experiment2"]
    sessions, trials, answers, people, count = [], [], [], {}, {}
    for s in EXPERIMENT2_SESSIONS:
        count[s.participant] = count.get(s.participant, 0) + 1
        key = {"participant": s.participant, "session_index": count[s.participant]}
        speed = _speed(rng, people, s.participant)
        planned = regenerate.planned_rows("experiment2", s.assignment_id)
        digest = planned.pop("schedule_sha256").iloc[0]
        condition = planned["condition"].iloc[0]
        n = len(planned) if s.ending == COMPLETED else UNFINISHED_QUESTIONS
        rows = planned.iloc[:n]
        p = P_AT_RANDOM if s.at_random else P_CORRECT_2[condition]
        out = []
        for r in rows.itertuples(index=False):
            slope = RT_SLOPE_2[condition] * (r.symbolic_distance - MIDDLE_DISTANCE)
            median = MEDIAN_RT_MS_2[condition] * speed * math.exp(slope)
            side, rt = _answer(rng, r.correct_answer, p, median, deadline)
            out.append({
                "response_side": side, "rt": rt, "is_timed_out": side is None,
                "is_correct": side == r.correct_answer,
                "is_real_world_consistent": None if side is None else side == r.real_world_answer,
            })
        trials.append(pd.concat([rows, pd.DataFrame(out, index=rows.index)], axis=1).assign(
            **key, assignment_id=s.assignment_id))
        breaks = rows["block"].nunique() - 1
        after = SCREENS_AFTER_QUESTIONS if s.ending == COMPLETED else 0
        sessions.append({
            **key, "assignment_id": s.assignment_id, "condition": condition, "wave": s.wave,
            "allocation_round": s.allocation_round, "is_completed": s.ending == COMPLETED,
            "n_saved_rows": SCREENS_BEFORE_QUESTIONS + n + breaks + after,
            "n_main_questions": n, "schedule_sha256": digest,
        })
        if s.ending == COMPLETED:
            answers.append({**key, "condition": condition, "statements_true": s.statements_true,
                            "knowledge_use": s.knowledge_use})
    return {
        "sessions": pd.DataFrame(sessions),
        "trials": pd.concat(trials, ignore_index=True),
        "questionnaire": pd.DataFrame(answers),
    }


# Writing

# The order of the rows of each table, after the session key.
ROW_ORDER = {("experiment1", "trials"): ["trial_index"],
             ("experiment2", "trials"): ["question_number"]}
MANIFEST_HEADER = ("# sha256 digest, number of rows and columns of every synthetic table, by path"
                   " under\n# tests/synthetic/. Written by tests/synthetic/make_tables.py.\n")


def _table(df: pd.DataFrame, experiment: str, table: str) -> pd.DataFrame:
    """``df`` as the table: its columns in order, its dtypes, its row order; then validated."""
    schema = tables.SCHEMAS[(experiment, table)]
    order = [*tables.SESSION_KEY, *ROW_ORDER.get((experiment, table), [])]
    df = df.sort_values(order, kind="stable").reset_index(drop=True)
    df = pd.DataFrame({column: df[column].astype(dtype) for column, dtype in schema.items()})
    return tables.validate(df, table, experiment)


def write(frames: dict[tuple[str, str], pd.DataFrame], out_dir: Path) -> list[Path]:
    """Write each table and the manifest under ``out_dir``; return the paths written."""
    manifest, paths = {}, []
    for (experiment, table), df in frames.items():
        name = f"{experiment}/{table}.parquet"
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _table(df, experiment, table).to_parquet(path, index=False)
        manifest[name] = tables._entry(path)
        paths.append(path)
    path = out_dir / tables.MANIFEST
    path.write_text(MANIFEST_HEADER + yaml.safe_dump(manifest, sort_keys=False))
    return [*paths, path]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="write the synthetic data tables")
    parser.add_argument("--out", type=Path, default=OUT_DIR,
                        help="directory the tables are written to (default: tests/synthetic/)")
    args = parser.parse_args(argv)
    frames = {}
    for experiment, build in (("experiment1", experiment1), ("experiment2", experiment2)):
        for table, df in build(np.random.default_rng(SEEDS[experiment])).items():
            frames[(experiment, table)] = df
    for path in write(frames, args.out):
        print(path)


if __name__ == "__main__":
    main()
