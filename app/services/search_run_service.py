from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationError
from app.models.search_run import SearchRun
from app.repositories.job_repository import JobRepository
from app.repositories.search_run_repository import SearchRunRepository
from app.repositories.source_status_repository import SourceStatusRepository
from app.schemas.dto import SearchRunInput
from app.services.clock import utc_now
from app.services.search_executor import SearchExecutor
from app.sources.base import SourceAdapter
from app.sources.registry import build_source_registry


class SearchRunService:
    def __init__(
        self,
        runs: SearchRunRepository,
        jobs: JobRepository,
        statuses: SourceStatusRepository,
        registry_factory: Callable[..., dict[str, SourceAdapter]],
        session_factory: sessionmaker[Session],
        settings_factory: Callable[[], Settings] = get_settings,
    ) -> None:
        self._runs = runs
        self._jobs = jobs
        self._statuses = statuses
        self._registry_factory = registry_factory
        self._session_factory = session_factory
        self._settings_factory = settings_factory

    def get(self, run_id: str) -> SearchRun:
        run = self._runs.get(run_id)
        if run is None:
            raise NotFoundError(f"Search run {run_id} not found", code="run_not_found")
        return run

    def resolve_sources(self, payload: SearchRunInput, *, available: list[str]) -> list[str]:
        selected = payload.sources or available
        if not selected:
            raise ValidationError(
                "No sources are configured",
                code="no_sources",
            )
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise ValidationError(
                f"Unknown source(s): {', '.join(unknown)}",
                code="unknown_sources",
            )
        return selected

    def create(self, payload: SearchRunInput, available_sources: list[str]) -> SearchRun:
        selected = self.resolve_sources(payload, available=available_sources)
        return self._runs.create(payload, selected, now=utc_now())

    def execute_in_background(
        self,
        run_id: str,
        payload: SearchRunInput,
        selected_sources: list[str],
    ) -> None:
        """Hand off the long-running work to a worker. Pure orchestration.

        The worker opens its OWN session and constructs its OWN repositories,
        bound to that session. The request-scoped repos on this service are
        long gone by the time the background task runs.
        """
        executor = SearchExecutor(
            session_factory=self._session_factory,
            registry_factory=self._registry_factory,
            settings_factory=self._settings_factory,
        )
        executor.execute(run_id, payload, selected_sources)
