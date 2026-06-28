"""Shared synchronous search execution used by search runs and job alerts."""

from __future__ import annotations

from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.repositories.search_run_repository import SearchRunRepository
from app.repositories.source_status_repository import SourceStatusRepository
from app.schemas.dto import SearchRunInput, SourceErrorDTO
from app.services.clock import utc_now
from app.sources.base import SourceAdapter


class SearchExecutor:
    """Runs a search across selected sources and attaches results to a search run.

    This class is intentionally synchronous: it is meant to be called from
    background threads (FastAPI BackgroundTasks or APScheduler jobs). It opens
    and manages its own database session.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        registry_factory: Callable[..., dict[str, SourceAdapter]],
        settings_factory: Callable[[], Settings],
    ) -> None:
        self._session_factory = session_factory
        self._registry_factory = registry_factory
        self._settings_factory = settings_factory

    def execute(
        self,
        run_id: str,
        payload: SearchRunInput,
        selected_sources: list[str],
    ) -> int:
        """Execute the search and return the number of jobs attached.

        Raises:
            NotFoundError: If the search run does not exist.
        """
        session = self._session_factory()
        runs = SearchRunRepository(session)
        jobs = JobRepository(session)
        statuses = SourceStatusRepository(session)
        try:
            registry = self._registry_factory(self._settings_factory())
            run = runs.get(run_id)
            if run is None:
                raise NotFoundError(f"Search run {run_id} not found", code="run_not_found")

            runs.mark_running(run, now=utc_now())

            total_jobs = 0
            all_errors: list[dict] = []
            for source_name in selected_sources:
                adapter = registry[source_name]
                result = adapter.search(
                    q=payload.q,
                    location=payload.location,
                    remote=payload.remote,
                    limit=payload.limit,
                )
                primary_error = result.errors[0] if result.errors else None
                statuses.record(
                    adapter,
                    now=utc_now(),
                    status="error" if primary_error else adapter.info.status,
                    error=primary_error,
                )
                all_errors.extend([e.model_dump() for e in result.errors])

                for candidate in result.jobs:
                    job = jobs.upsert_from_candidate(candidate, now=utc_now())
                    session.flush()
                    runs.attach_job(run_id, job.id, job.source, now=utc_now())
                    total_jobs += 1

            runs.complete(
                run,
                now=utc_now(),
                status="completed",
                total_jobs=total_jobs,
                error_count=len(all_errors),
                errors=all_errors,
            )
            return total_jobs
        except Exception:
            session.rollback()
            run = runs.get(run_id)
            if run is not None:
                runs.complete(
                    run,
                    now=utc_now(),
                    status="failed",
                    total_jobs=0,
                    error_count=1,
                    errors=[
                        SourceErrorDTO(
                            source="service",
                            code="search_run_failed",
                            message="Search run failed before completion",
                            retryable=True,
                        ).model_dump()
                    ],
                )
            raise
        finally:
            session.close()

    def get_jobs_for_run(self, run_id: str) -> list[Job]:
        """Return the Job objects attached to a completed search run."""
        session = self._session_factory()
        try:
            from app.models.search_run import SearchRunJob

            stmt = (
                select(Job)
                .join(SearchRunJob, Job.id == SearchRunJob.job_id)
                .where(SearchRunJob.run_id == run_id)
                .order_by(Job.fetched_at.desc())
            )
            return list(session.execute(stmt).scalars().all())
        finally:
            session.close()
