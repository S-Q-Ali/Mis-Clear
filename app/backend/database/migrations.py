"""Versioned schema migrations.

Strategy: SQLite-bound ordinal migrations tracked in `schema_versions`.
`migrate()` applies every patch with version > current, then records it.
Baseline (v1) creates the full Phase-4 schema via Base.metadata.create_all.

Future phases append new `Migration` entries — never edit applied ones.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.backend.database.engine import Base


class Migration:
    def __init__(self, version: int, description: str, ddl: str | None = None) -> None:
        self.version = version
        self.description = description
        self.ddl = ddl

    def apply(self, engine: Engine) -> None:
        if self.ddl:
            with engine.begin() as conn:
                conn.exec_driver_sql(self.ddl)


BASELINE = Migration(1, "phase-4 baseline schema (all tables)")
MIGRATIONS: list[Migration] = [BASELINE]


def current_version(engine: Engine) -> int:
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT MAX(version) FROM schema_versions")).scalar()
    return rows if rows else 0


def migrate(engine: Engine) -> int:
    """Apply pending migrations; return the new version reached."""
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE IF NOT EXISTS schema_versions "
                "(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))"
            )
        )
    current = current_version(engine)

    # Baseline: create the full ORM schema before recording v1.
    if current < 1:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO schema_versions (version) VALUES (1)"))
        current = 1

    for migration in sorted(MIGRATIONS, key=lambda m: m.version):
        if migration.version <= current:
            continue
        migration.apply(engine)
        with engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO schema_versions (version) VALUES (:v)"),
                {"v": migration.version},
            )
        current = migration.version
    return current