"""Database engine, session, and schema management (SQLite/SQLAlchemy)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.backend.config import settings


class Base(DeclarativeBase):
    pass


def build_engine(db_path: str) -> Engine:
    """Create a SQLite engine for the given path (used by app and tests).

    Enables WAL mode + a generous busy timeout so concurrent writers (scan
    requests vs Colab worker protocol transitions) queue gracefully instead of
    raising ``database is locked`` on the first contention.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


engine = build_engine(settings.database_path)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Ensure persistence directory exists and schema is migrated (idempotent)."""
    from app.backend.database.migrations import migrate

    migrate(engine)


def init_db_at(db_path: str) -> Engine:
    """Migrate a schema at a specific path (test isolation) and return its engine."""
    import app.backend.models  # noqa: F401  # register models on Base.metadata
    from app.backend.database.migrations import migrate

    eng = build_engine(db_path)
    migrate(eng)
    return eng


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()