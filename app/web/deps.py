"""FastAPI dependencies shared across routes: one DB session per request,
committed on success and rolled back on any exception — the request
boundary is the transaction boundary, same principle app.intake and
app.persist already use for a single call, just scoped to a whole request
here since a review submission touches several tables atomically.
"""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.base import SessionLocal


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
