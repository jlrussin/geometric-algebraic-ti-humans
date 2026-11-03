"""Shared fixtures for the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from geo_alg_ti_humans import tables


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def synthetic_root(repo_root) -> Path:
    """The directory of the synthetic tables (``tests/synthetic/make_tables.py``)."""
    return repo_root / "tests" / "synthetic"


@pytest.fixture(scope="session")
def data_root() -> Path:
    """The directory of the data tables; a test that needs them is skipped when they are absent."""
    root = tables.data_root()
    if not any(root.glob("experiment*/*.parquet")):
        pytest.skip(f"no data tables under {root}; set {tables.DATA_ENV} to their directory")
    return root
