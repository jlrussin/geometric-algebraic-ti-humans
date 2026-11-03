"""Load the de-identified data tables and check them against their codebooks and manifest.

Each experiment has a ``sessions`` table (one row per session, including sessions that did not
finish or were excluded) and a ``trials`` table (every saved task trial); Experiment 2 also has
a ``questionnaire`` table (one row per completed session). The tables live under
``data/<experiment>/<table>.parquet`` with a codebook ``<table>.md`` beside each, and
``data/MANIFEST.yaml`` records the sha256 digest, row count and columns of every table.

``participant`` is a pseudonymous person key (``P001``, ...). Each person's primary session is
the one with the most saved rows, then the lowest ``assignment_id``, then the earliest start;
people are numbered by their primary session's ``assignment_id`` in Experiment 1 and by its
start time in Experiment 2. ``session_index`` numbers a person's sessions by start time
(1 = earliest).

The data directory is ``data/`` in the repository, or the directory named by the environment
variable ``GEO_ALG_TI_HUMANS_DATA``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import yaml

from geo_alg_ti_humans import REPO_ROOT

DATA_ENV = "GEO_ALG_TI_HUMANS_DATA"
EXPERIMENTS = ("experiment1", "experiment2")
MANIFEST = "MANIFEST.yaml"
# A session is identified by its person and the person's session number.
SESSION_KEY: tuple[str, str] = ("participant", "session_index")

# Column order and pandas dtype of every table, keyed by (experiment, table).
# Nullable dtypes ("Int64", "boolean", "string") hold the nulls the codebooks describe.
SCHEMAS: Mapping[tuple[str, str], Mapping[str, str]] = {
    ("experiment1", "sessions"): {
        "participant": "string",
        "session_index": "Int64",
        "assignment_id": "Int64",
        "start_order": "Int64",  # 1 = the first of the 74 sessions to start
        "test_order": "string",  # icl,iwl,arbitrage or iwl,icl,arbitrage
        "is_completed": "boolean",  # also true for sessions that failed the comprehension checks
        "failed_comprehension": "boolean",
        "n_saved_rows": "Int64",
        "stream_offset": "Int64",  # null when the session saved no task trials
    },
    ("experiment1", "trials"): {
        "participant": "string",
        "session_index": "Int64",
        "assignment_id": "Int64",
        "phase": "string",
        "is_retry": "boolean",
        "trial_index": "Int64",
        "symbolic_distance": "Int64",
        "query_left": "string",
        "query_right": "string",
        "query_left_rank": "Int64",  # 1 = top of the ordering
        "query_right_rank": "Int64",
        "context_display": "string",  # shown or masked
        "intervening_distractors": "Int64",  # 0-2
        "n_context_pairs": "Int64",
        "displayed_chain": "string",  # JSON list: the chain the clues show
        "display_slots": "string",  # JSON
        "inserted_distractors": "string",  # JSON list of item names
        "swapped_item": "string",
        "swap_distractor": "string",
        "icl_ordering": "Int64",  # 0-4
        "icl_consistent_side": "string",
        "response": "string",  # left, right, or null on timeout
        "rt": "float64",  # ms; null on timeout
        "is_correct": "boolean",  # false on timeout; on arbitrage, followed the trained ordering
        "is_timed_out": "boolean",
        "is_icl_consistent": "boolean",  # arbitrage only
        "is_iwl_consistent": "boolean",  # arbitrage only
    },
    ("experiment2", "sessions"): {
        "participant": "string",
        "session_index": "Int64",
        "assignment_id": "Int64",
        "condition": "string",  # congruent or shuffled
        "wave": "Int64",  # 1 or 2
        "allocation_round": "Int64",  # null, 1 or 2
        "is_completed": "boolean",
        "n_saved_rows": "Int64",
        "n_main_questions": "Int64",
        "schedule_sha256": "string",
    },
    ("experiment2", "trials"): {
        "participant": "string",
        "session_index": "Int64",
        "assignment_id": "Int64",
        "condition": "string",
        "question_number": "Int64",  # 1-48
        "block": "Int64",  # 1-4
        "symbolic_distance": "Int64",
        "real_world_distance": "Int64",
        "question_type": "string",  # agree or conflict
        "item_pair": "string",
        "query_left": "string",
        "query_right": "string",
        "correct_answer": "string",  # left or right, by the statements
        "real_world_answer": "string",  # left or right, by the real-world order
        "response_side": "string",  # left, right, or null on timeout
        "rt": "float64",  # ms; null on timeout
        "is_timed_out": "boolean",
        "is_correct": "boolean",  # false on timeout
        "is_real_world_consistent": "boolean",  # null on timeout
        "statements_text": "string",  # JSON list of the eight statements as shown
        "context_ordering": "string",  # JSON list of the nine animals in order
    },
    ("experiment2", "questionnaire"): {
        "participant": "string",
        "session_index": "Int64",
        "condition": "string",
        "statements_true": "string",  # All, Most, About half, Few, None, I don't know
        "knowledge_use": "string",  # Never ... Always
    },
}


def data_root() -> Path:
    """The data directory: ``$GEO_ALG_TI_HUMANS_DATA`` if set, else ``data/`` in the repository.

    Raises ``FileNotFoundError`` when the variable is unset and the package is not running from
    a checkout of the repository.
    """
    env = os.environ.get(DATA_ENV)
    if env:
        return Path(env).expanduser()
    if not (REPO_ROOT / "pyproject.toml").is_file():
        raise FileNotFoundError(
            f"the package is not running from a repository checkout; set {DATA_ENV} to the "
            "directory of the data tables")
    return REPO_ROOT / "data"


def _entry(path: Path) -> dict:
    """The manifest entry of one table file: its sha256 digest, row count and column names."""
    with open(path, "rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    meta = pq.read_metadata(path)
    return {"sha256": digest, "rows": meta.num_rows, "columns": meta.schema.names}


def _read_manifest(root: Path) -> dict:
    path = root / MANIFEST
    if not path.is_file():
        raise FileNotFoundError(f"no {MANIFEST} in {root}")
    manifest = yaml.safe_load(path.read_text()) or {}
    if not isinstance(manifest, dict):
        raise ValueError(f"{path}: expected a mapping from table path to its entry")
    for name, entry in manifest.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{name}: the {MANIFEST} entry is not a mapping")
    return manifest


def _check(root: Path, name: str, expected: dict) -> None:
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(f"{name} is listed in {MANIFEST} but missing from {root}")
    found = _entry(path)
    for field in ("sha256", "rows", "columns"):
        if found[field] != expected.get(field):
            raise ValueError(f"{name}: {field} differs from {MANIFEST}")


def manifest_digest(root: Path | None = None) -> dict:
    """Check every table under ``root`` against ``MANIFEST.yaml`` and return the manifest.

    The manifest maps each table's path under ``root`` (``<experiment>/<table>.parquet``) to its
    ``sha256`` digest, number of ``rows`` and ``columns``. Raises ``ValueError`` naming the first
    table whose sha256 digest, row count or columns differ from the manifest, or a table that
    the manifest does not list, and ``FileNotFoundError`` if a listed table is missing.
    """
    root = Path(root) if root is not None else data_root()
    manifest = _read_manifest(root)
    for name, expected in manifest.items():
        _check(root, name, expected)
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*.parquet")}
    unlisted = sorted(on_disk - manifest.keys())
    if unlisted:
        raise ValueError(f"{unlisted[0]} is not listed in {MANIFEST}")
    return manifest


def load(table: str, experiment: str, root: Path | None = None) -> pd.DataFrame:
    """Read one table after checking the manifest, then validate it against ``SCHEMAS``.

    Raises ``KeyError`` for a table that is not in ``SCHEMAS``, ``ValueError`` when the manifest
    does not list the table or its entry differs from the file, and ``FileNotFoundError`` when
    the manifest or the table is missing.
    """
    if (experiment, table) not in SCHEMAS:
        raise KeyError(f"no table {table!r} in {experiment!r}")
    root = Path(root) if root is not None else data_root()
    name = f"{experiment}/{table}.parquet"
    manifest = _read_manifest(root)
    if name not in manifest:
        raise ValueError(f"{name} is not listed in {MANIFEST}")
    _check(root, name, manifest[name])
    return validate(pd.read_parquet(root / name), table, experiment)


def validate(df: pd.DataFrame, table: str, experiment: str) -> pd.DataFrame:
    """Return ``df`` if it has exactly the schema's columns, in order, with the schema's dtypes.

    Raises ``ValueError`` naming every missing, unexpected or mistyped column, or the expected
    order when the columns are right but out of order.
    """
    schema = SCHEMAS[(experiment, table)]
    problems = []
    missing = [c for c in schema if c not in df.columns]
    unexpected = [c for c in df.columns if c not in schema]
    if missing:
        problems.append(f"missing {missing}")
    if unexpected:
        problems.append(f"unexpected {unexpected}")
    mistyped = [f"{c} ({df[c].dtype}, expected {t})" for c, t in schema.items()
                if c in df.columns and str(df[c].dtype) != t]
    if mistyped:
        problems.append(f"mistyped {mistyped}")
    if not problems and list(df.columns) != list(schema):
        problems.append(f"columns out of order (expected {list(schema)})")
    if problems:
        raise ValueError(f"{experiment} {table}: " + "; ".join(problems))
    return df
