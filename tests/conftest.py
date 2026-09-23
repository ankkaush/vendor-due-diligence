"""Shared pytest fixtures for database tests.

Standard SQLAlchemy test-isolation pattern: each test runs inside its own
transaction on a dedicated connection, which is rolled back afterward —
so tests never see each other's data and never need manual cleanup, and
the schema only needs to be migrated once per test session (assumes
`alembic upgrade head` has already been run against DATABASE_URL — tests
don't run migrations themselves, to keep "did the migration apply
correctly" and "does the schema behave correctly" as separate concerns).

join_transaction_mode="create_savepoint" (SQLAlchemy 2.0) is required, not
just a plain Session(bind=connection): several tests here deliberately
trigger a failed flush() (constraint violations, append-only trigger
rejections) inside `pytest.raises(...)`. Without savepoint mode, a failed
flush deassociates the ORM session from the outer connection-level
transaction, and the fixture's own teardown rollback then only warns
("transaction already deassociated") instead of cleanly reverting —
confirmed by actually hitting that warning before adding this setting, not
assumed in advance.
"""

import pytest
from sqlalchemy.orm import Session

from app.db.base import engine


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
