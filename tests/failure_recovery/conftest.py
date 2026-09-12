"""Phase 14 failure/recovery shared fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture()
def db_session(tmp_path):
    from sqlalchemy.orm import Session

    from app.backend.database.engine import init_db_at

    engine = init_db_at(str(tmp_path / "rec.db"))
    session = Session(engine)
    yield session
    session.close()