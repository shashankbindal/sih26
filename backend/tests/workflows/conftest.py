"""Workflow tests: reset the process-wide CaseLink runtime (fitted similarity, institution index)
before every test, because the DB is truncated between tests.

Run against a private database to avoid clashing with other test runs:
    TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/loksutra_test_wf pytest tests/workflows
"""

from __future__ import annotations

import pytest

from app.services.caselink_runtime import reset_runtime


@pytest.fixture(autouse=True)
def _fresh_runtime():
    reset_runtime()
    yield
    reset_runtime()
