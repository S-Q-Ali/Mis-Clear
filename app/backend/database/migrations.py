"""Versioned schema migrations.

Strategy: SQLite-bound ordinal migrations tracked in `schema_versions`.
`migrate()` applies every patch with version > current, then records it.
Baseline (v1) creates the full Phase-4 schema via Base.metadata.create_all.

Future phases append new `Migration` entries — never edit applied ones.
"""

from __future__ import annotations

from typing import Callable

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.backend.database.engine import Base


class Migration:
    def __init__(
        self,
        version: int,
        description: str,
        ddl: str | None = None,
        fn: Callable[[Engine], None] | None = None,
    ) -> None:
        self.version = version
        self.description = description
        self.ddl = ddl
        self.fn = fn

    def apply(self, engine: Engine) -> None:
        if self.ddl:
            with engine.begin() as conn:
                conn.exec_driver_sql(self.ddl)
        if self.fn:
            self.fn(engine)


def _columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _rename_if_exists(engine: Engine, table: str, old: str, new: str, col_type: str) -> None:
    if old in _columns(engine, table) and new not in _columns(engine, table):
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")


BASELINE = Migration(1, "phase-4 baseline schema (all tables)")
V2_IDEMPOTENCY = Migration(
    2,
    "idempotency_keys for POST /api/scans",
    ddl=(
        "CREATE TABLE IF NOT EXISTS idempotency_keys ("
        "key TEXT PRIMARY KEY, "
        "request_hash TEXT NOT NULL, "
        "scan_id INTEGER, "
        "created_at TEXT DEFAULT (datetime('now')), "
        "FOREIGN KEY(scan_id) REFERENCES scans(id))"
    ),
)
V3_JOB_SCAN_FK = Migration(
    3,
    "jobs.scene_id -> scan_id (typo fix)",
    fn=lambda engine: _rename_if_exists(engine, "jobs", "scene_id", "scan_id", "INTEGER"),
)
MIGRATIONS: list[Migration] = [BASELINE, V2_IDEMPOTENCY, V3_JOB_SCAN_FK]


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