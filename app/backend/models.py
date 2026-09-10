"""SQLAlchemy ORM models (populated in Phase 4)."""

from app.backend.database.engine import Base


class _Placeholder(Base):
    """Scaffold so Base.metadata is non-empty before Phase 4.

    Removed once real models (scans, findings, identities, ...) land.
    """

    __tablename__ = "_bootstrap_placeholder"
    id = None  # type: ignore[assignment]