"""Shared fixtures: in-memory SQLite engine + session factory."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.registry import Job, SearchRun, SearchRunJob, SourceStatus  # noqa: F401


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
