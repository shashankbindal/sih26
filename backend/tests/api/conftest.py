r"""Black-box HTTP tests against a RUNNING server (default http://127.0.0.1:8000, demo DB, demo logins).

Run:  cd backend; .venv\Scripts\python.exe -m pytest tests/api -q        (server must be up and freshly seeded)
Env:  QA_API_URL (default http://127.0.0.1:8000), QA_DB_URL (optional, for audit_log row counts).

These tests MUTATE the demo database (new cases, clearances, one tamper demo on a throwaway case).
Reseed afterwards:  python -m app.seed.generate --reset
They are skipped automatically unless the server is reachable AND tests/api was selected explicitly
(or QA_LIVE=1), so a plain `pytest -q` of the in-process suite never touches the demo DB.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

from tests.api.helpers import API, BASE, USERS, Api, login

# The in-process suite's autouse fixtures drop/recreate the TEST database schema; irrelevant here.


@pytest.fixture(scope="session", autouse=True)
def _schema():  # noqa: D401 - override of tests/conftest.py fixture
    yield


@pytest.fixture(autouse=True)
def _clean(_schema):  # noqa: D401 - override of tests/conftest.py fixture
    yield


def _server_up() -> bool:
    try:
        return httpx.get(API + "/health", timeout=3).status_code == 200
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    api_items = [i for i in items if "tests" + os.sep + "api" in str(i.fspath) or "tests/api" in str(i.fspath)]
    if not api_items:
        return
    explicit = os.environ.get("QA_LIVE") == "1" or any("api" in a.replace("\\", "/").split("/") for a in sys.argv)
    if not explicit:
        reason = "live API tests: run `pytest tests/api` (or QA_LIVE=1) against a running, freshly seeded server"
    elif not _server_up():
        reason = f"server not reachable at {BASE}"
    else:
        return
    skip = pytest.mark.skip(reason=reason)
    for i in api_items:
        i.add_marker(skip)


@pytest.fixture(scope="session")
def anon() -> Api:
    return Api(None)


@pytest.fixture(scope="session")
def u() -> dict[str, Api]:
    """One logged-in client per demo user, keyed by the local part of the e-mail."""
    return {k: login(k) for k in USERS}
