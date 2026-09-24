"""Web route test fixtures.

The TestClient shares the SAME db_session (tests/conftest.py's
transaction-per-test fixture) across every request in a test, via a
dependency override that neither commits nor closes it — the outer
fixture owns that session's lifecycle and rolls it back at teardown, so
route handlers see the exact objects a test set up and nothing a test
writes ever reaches another test or the real dev database.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.web.deps import get_db
from app.web.main import app

REVIEWER_AUTH = (settings.reviewer_username, settings.reviewer_password)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
