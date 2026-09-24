"""Versioned schema migrations.

Strategy: SQLite-bound ordinal migrations tracked in `schema_versions`.
`migrate()` applies every patch with version > current, then records it.
Baseline (v1) creates the full Phase-4 schema via Base.metadata.create_all.

Future phases append new `Migration` entries — never edit applied ones.
"""

from __future__ import annotations

from collections.abc import Callable

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
V4_ACTION_EXECUTIONS = Migration(
    4,
    "action_executions table for removal executor (Phase 16)",
    ddl=(
        "CREATE TABLE IF NOT EXISTS action_executions ("
        "id INTEGER PRIMARY KEY, "
        "action_id INTEGER NOT NULL, "
        "attempt INTEGER NOT NULL DEFAULT 1, "
        "status TEXT NOT NULL DEFAULT 'pending', "
        "channel TEXT NOT NULL DEFAULT 'manual', "
        "target_url TEXT, "
        "submitted_at TEXT, "
        "verified_at TEXT, "
        "verification_detail TEXT, "
        "note TEXT, "
        "created_at TEXT DEFAULT (datetime('now')), "
        "FOREIGN KEY(action_id) REFERENCES actions(id))"
    ),
)
def _apply_v5_agent_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS agent_conversations ("
            "id INTEGER PRIMARY KEY, "
            "title TEXT NOT NULL DEFAULT 'Agent chat', "
            "scan_id INTEGER, "
            "status TEXT NOT NULL DEFAULT 'active', "
            "hybrid_approved INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT DEFAULT (datetime('now')), "
            "updated_at TEXT DEFAULT (datetime('now')), "
            "FOREIGN KEY(scan_id) REFERENCES scans(id))"
        )
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS agent_messages ("
            "id INTEGER PRIMARY KEY, "
            "conversation_id INTEGER NOT NULL, "
            "role TEXT NOT NULL, "
            "content TEXT, "
            "blocked INTEGER NOT NULL DEFAULT 0, "
            "steps TEXT, "
            "answer TEXT, "
            "created_at TEXT DEFAULT (datetime('now')), "
            "FOREIGN KEY(conversation_id) REFERENCES agent_conversations(id))"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_agent_messages_conversation "
            "ON agent_messages(conversation_id)"
        )


V5_AGENT_CONVERSATIONS = Migration(
    5,
    "agent_conversations + agent_messages (SPEC-agent-api)",
    fn=_apply_v5_agent_schema,
)
MIGRATIONS: list[Migration] = [
    BASELINE,
    V2_IDEMPOTENCY,
    V3_JOB_SCAN_FK,
    V4_ACTION_EXECUTIONS,
    V5_AGENT_CONVERSATIONS,
]


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