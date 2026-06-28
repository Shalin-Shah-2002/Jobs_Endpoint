"""Unit tests for SourceService and SearchRunService — no HTTP."""

from datetime import UTC, datetime
from typing import Callable

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.repositories.search_run_repository import SearchRunRepository
from app.repositories.source_status_repository import SourceStatusRepository
from app.schemas.dto import SearchRunInput
from app.services.search_run_service import SearchRunService
from app.services.source_service import SourceService
from app.sources.base import SourceInfo, SourceSearchResult
from app.sources.registry import build_source_registry


class FakeAdapter:
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.info = SourceInfo(
            name=name,
            enabled=enabled,
            status="ready" if enabled else "disabled",
            reason="ok" if enabled else "disabled reason",
        )

    def search(self, **kwargs) -> SourceSearchResult:
        return SourceSearchResult()


def make_registry(include_disabled: bool = True) -> Callable[..., dict]:
    def factory(settings) -> dict:
        reg = {"mock": FakeAdapter("mock", enabled=True)}
        if include_disabled:
            reg["disabled1"] = FakeAdapter("disabled1", enabled=False)
        return reg
    return factory


def test_source_service_lists_all_known_sources(session: Session) -> None:
    service = SourceService(SourceStatusRepository(session), registry_factory=make_registry())
    settings = type("S", (), {})()
    dtos = service.list_sources(settings)
    assert {d.name for d in dtos} == {"mock", "disabled1"}
    assert {d.enabled for d in dtos} == {True, False}


def test_source_service_returns_only_enabled_names(session: Session) -> None:
    service = SourceService(SourceStatusRepository(session), registry_factory=make_registry())
    settings = type("S", (), {})()
    assert service.enabled_source_names(settings) == ["mock"]
    assert service.known_source_names(settings) == ["mock", "disabled1"]


def test_search_run_resolve_rejects_unknown_sources(session: Session) -> None:
    service = SearchRunService(
        runs=SearchRunRepository(session),
        jobs=__import__("app.repositories.job_repository", fromlist=["JobRepository"]).JobRepository(session),
        statuses=SourceStatusRepository(session),
        registry_factory=make_registry(),
        session_factory=lambda: session,
    )
    source_service = SourceService(SourceStatusRepository(session), registry_factory=make_registry())
    available = source_service.known_source_names(None)
    payload = SearchRunInput(q="python", sources=["made-up"], limit=10)
    with pytest.raises(ValidationError) as exc:
        service.resolve_sources(payload, available=available)
    assert exc.value.code == "unknown_sources"


def test_search_run_resolve_defaults_to_all_known(session: Session) -> None:
    service = SearchRunService(
        runs=SearchRunRepository(session),
        jobs=__import__("app.repositories.job_repository", fromlist=["JobRepository"]).JobRepository(session),
        statuses=SourceStatusRepository(session),
        registry_factory=make_registry(),
        session_factory=lambda: session,
    )
    source_service = SourceService(SourceStatusRepository(session), registry_factory=make_registry())
    available = source_service.known_source_names(None)
    payload = SearchRunInput(q="python", sources=None, limit=10)
    selected = service.resolve_sources(payload, available=available)
    assert set(selected) == {"mock", "disabled1"}


def test_search_run_resolve_rejects_empty(session: Session) -> None:
    service = SearchRunService(
        runs=SearchRunRepository(session),
        jobs=__import__("app.repositories.job_repository", fromlist=["JobRepository"]).JobRepository(session),
        statuses=SourceStatusRepository(session),
        registry_factory=lambda s: {},
        session_factory=lambda: session,
    )
    payload = SearchRunInput(q="python", sources=None, limit=10)
    with pytest.raises(ValidationError) as exc:
        service.resolve_sources(payload, available=[])
    assert exc.value.code == "no_sources"


def test_search_run_get_raises_not_found(session: Session) -> None:
    service = SearchRunService(
        runs=SearchRunRepository(session),
        jobs=__import__("app.repositories.job_repository", fromlist=["JobRepository"]).JobRepository(session),
        statuses=SourceStatusRepository(session),
        registry_factory=make_registry(),
        session_factory=lambda: session,
    )
    with pytest.raises(NotFoundError):
        service.get("missing-run-id")
