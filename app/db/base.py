"""SQLAlchemy declarative base, engine, and session helpers.

Phase 4 scope only: the schema and the ability to open a session against
it. No repository/query layer yet — that arrives with the orchestrator in
Phase 5, once there's actual application logic to use it.
"""

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Explicit naming convention so Alembic autogenerate produces stable,
# predictable constraint/index names instead of database-assigned ones —
# required for migrations to diff cleanly across environments.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
