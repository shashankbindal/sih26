"""Engine tests are pure Python: neutralise the DB fixtures from tests/conftest.py."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:  # overrides the DB-migrating fixture of the parent conftest
    return None


@pytest.fixture(autouse=True)
def _clean() -> None:  # overrides the DB-truncating fixture of the parent conftest
    return None
