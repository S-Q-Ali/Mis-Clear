"""Database engine and declarative base. Schema models arrive in Phase 4."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.backend.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


_ensure_parent(settings.database_path)

engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    # Import models here so they register on Base.metadata.
    import app.backend.models  # noqa: F401

    if not Path(settings.database_path).exists() or Path(settings.database_path).stat().st_size == 0:
        Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()