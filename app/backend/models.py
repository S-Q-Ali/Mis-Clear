"""SQLAlchemy ORM models — Privacy Guardian schema (Phase 4).

Tables: scans, identities, relationships, findings, images, actions, jobs,
tool_runs, audit_logs. All timestamps are UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.database.engine import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20))  # email|username|image|custom
    target_value: Mapped[str] = mapped_column(String(255))
    scan_mode: Mapped[str] = mapped_column(String(20), default="local")  # local|hybrid
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending|running|completed|failed|interrupted
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    coverage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    findings: Mapped[list["Finding"]] = relationship(back_populates="scan")
    identities: Mapped[list["Identity"]] = relationship(back_populates="scan")
    images: Mapped[list["Image"]] = relationship(back_populates="scan")
    tool_runs: Mapped[list["ToolRun"]] = relationship(back_populates="scan")


class Identity(Base):
    __tablename__ = "identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # email|username|profile|website|custom
    value: Mapped[str] = mapped_column(String(255))
    canonical: Mapped[str] = mapped_column(String(255), default="")

    scan: Mapped[Scan | None] = relationship(back_populates="identities")
    outgoing: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.source_id", back_populates="source"
    )
    incoming: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.target_id", back_populates="target"
    )


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("identities.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("identities.id"))
    type: Mapped[str] = mapped_column(String(40))  # username->profile, profile->website, ...
    evidence_finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id"), nullable=True)

    source: Mapped[Identity] = relationship(foreign_keys=[source_id], back_populates="outgoing")
    target: Mapped[Identity] = relationship(foreign_keys=[target_id], back_populates="incoming")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"))
    type: Mapped[str] = mapped_column(String(40))  # email_exposure|username_profile|photo_metadata|...
    title: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), default="possible")
    # confirmed|probable|possible|weak|false_positive
    severity: Mapped[str] = mapped_column(String(20), default="low")
    # critical|high|medium|low|informational
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|reviewed|resolved

    scan: Mapped[Scan] = relationship(back_populates="findings")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    local_path: Mapped[str] = mapped_column(String(255))
    md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exif: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    scan: Mapped[Scan | None] = relationship(back_populates="images")


class PrivacyAction(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id"), nullable=True)
    recommended_action: Mapped[str] = mapped_column(String(255))
    deletion_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending|approved|completed|declined|expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    job_type: Mapped[str] = mapped_column(String(40))
    protocol_version: Mapped[str] = mapped_column(String(8), default="1")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # queued|running|completed|interrupted|failed
    privacy_mode: Mapped[str] = mapped_column(String(20), default="hybrid_approved")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    errors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    data_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_capabilities: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    worker: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ToolRun(Base):
    __tablename__ = "tool_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    tool: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="running")
    # running|completed|failed|blocked
    duration_ms: Mapped[int] = mapped_column(default=0)
    coverage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    findings_count: Mapped[int] = mapped_column(default=0)
    errors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    raw_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    scan: Mapped[Scan | None] = relationship(back_populates="tool_runs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    actor: Mapped[str] = mapped_column(String(80), default="user")
    action: Mapped[str] = mapped_column(String(40))  # create|approve|run|update|delete
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)