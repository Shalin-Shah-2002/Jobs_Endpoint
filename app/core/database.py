from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import Settings


Base = declarative_base()


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def db_session(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def init_database(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    return engine, session_factory
