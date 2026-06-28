"""Business logic for job alerts: CRUD and periodic execution."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.models.job import Job
from app.models.job_alert import JobAlert
from app.repositories.job_alert_repository import JobAlertRepository
from app.repositories.job_repository import JobRepository
from app.repositories.search_run_repository import SearchRunRepository
from app.repositories.source_status_repository import SourceStatusRepository
from app.schemas.dto import (
    JobAlertDTO,
    JobAlertExecutionListDTO,
    JobAlertInput,
    JobAlertPatch,
    JobDTO,
    SearchRunInput,
)
from app.services.clock import utc_now
from app.services.notification_service import NotificationResult, NotificationService
from app.services.search_executor import SearchExecutor
from app.services.search_run_service import SearchRunService
from app.services.source_service import SourceService
from app.views.job_alert_view import JobAlertExecutionView, JobAlertView


class JobAlertService:
    def __init__(
        self,
        *,
        alerts: JobAlertRepository,
        runs: SearchRunRepository,
        run_service: SearchRunService,
        source_service: SourceService,
        session_factory: sessionmaker[Session],
        settings_factory: Callable[[], Settings] = get_settings,
        notification_service: NotificationService,
    ) -> None:
        self._alerts = alerts
        self._runs = runs
        self._run_service = run_service
        self._source_service = source_service
        self._session_factory = session_factory
        self._settings_factory = settings_factory
        self._notification_service = notification_service

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_alert(self, payload: JobAlertInput, *, now: datetime) -> JobAlertDTO:
        settings = self._settings_factory()
        self._resolve_sources(payload, settings)
        alert = self._alerts.create(payload, now=now)
        return JobAlertView.to_dto(alert)

    def list_alerts(self) -> list[JobAlertDTO]:
        return [JobAlertView.to_dto(a) for a in self._alerts.list_all()]

    def get_alert(self, alert_id: str) -> JobAlertDTO:
        alert = self._get_alert_or_raise(alert_id)
        return JobAlertView.to_dto(alert)

    def update_alert(
        self, alert_id: str, patch: JobAlertPatch, *, now: datetime
    ) -> JobAlertDTO:
        alert = self._get_alert_or_raise(alert_id)
        self._apply_patch_validations(alert, patch)
        alert = self._alerts.update(alert, patch, now=now)
        return JobAlertView.to_dto(alert)

    def delete_alert(self, alert_id: str) -> None:
        alert = self._get_alert_or_raise(alert_id)
        self._alerts.delete(alert)

    def list_executions(
        self, alert_id: str, *, limit: int, cursor: str
    ) -> JobAlertExecutionListDTO:
        self._get_alert_or_raise(alert_id)
        from app.core.pagination import decode_cursor, encode_cursor

        rows = self._alerts.list_executions(
            alert_id, limit=limit, offset=decode_cursor(cursor)
        )
        items, next_offset = self._split_page(rows, limit)
        return JobAlertExecutionListDTO(
            items=[JobAlertExecutionView.to_dto(e) for e in items],
            limit=limit,
            next_cursor=encode_cursor(next_offset) if next_offset is not None else None,
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute_alert(self, alert_id: str, *, now: datetime | None = None) -> str:
        """Run a single alert synchronously and return the execution id.

        This method opens its own database session so it can safely be called
        from a background thread (APScheduler or FastAPI BackgroundTasks).
        """
        now = now or utc_now()
        session = self._session_factory()
        try:
            alerts_repo = JobAlertRepository(session)
            alert = alerts_repo.get(alert_id)
            if alert is None:
                return ""

            execution = alerts_repo.create_execution(alert_id, now=now, run_id=None)

            settings = self._settings_factory()
            runs_repo = SearchRunRepository(session)
            jobs_repo = JobRepository(session)
            statuses_repo = SourceStatusRepository(session)
            run_service = SearchRunService(
                runs=runs_repo,
                jobs=jobs_repo,
                statuses=statuses_repo,
                registry_factory=self._run_service._registry_factory,
                session_factory=self._session_factory,
                settings_factory=self._settings_factory,
            )
            source_service = SourceService(
                statuses_repo,
                registry_factory=self._source_service._registry_factory,
            )

            available = source_service.known_source_names(settings)
            payload = self._alert_to_search_input(alert)
            selected = run_service.resolve_sources(payload, available=available)

            status = "running"
            jobs: list[Job] = []
            new_jobs: list[Job] = []
            discord_status: str | None = None
            slack_status: str | None = None
            notified = False
            error: str | None = None

            try:
                run = runs_repo.create(payload, selected, now=now)
                execution.run_id = run.id
                session.commit()

                executor = SearchExecutor(
                    session_factory=self._session_factory,
                    registry_factory=self._run_service._registry_factory,
                    settings_factory=self._settings_factory,
                )
                executor.execute(run.id, payload, selected)

                jobs = executor.get_jobs_for_run(run.id)
                job_ids = [j.id for j in jobs]
                seen_ids = alerts_repo.filter_seen_job_ids(alert_id, job_ids)
                new_jobs = [j for j in jobs if j.id not in seen_ids]

                if new_jobs:
                    result = self._notification_service.send(
                        alert.name,
                        [JobDTO.model_validate(j) for j in new_jobs],
                        discord_webhook_url=alert.discord_webhook_url,
                        slack_webhook_url=alert.slack_webhook_url,
                    )
                    discord_status = result.discord_status
                    slack_status = result.slack_status
                    notified = True

                new_job_ids = [j.id for j in new_jobs]
                alerts_repo.mark_jobs_seen(alert_id, new_job_ids, now=now)

                status = "completed"
                alerts_repo.update_run_metadata(
                    alert,
                    last_run_at=now,
                    last_new_jobs_count=len(new_jobs),
                    last_error=None,
                )
            except Exception as exc:
                session.rollback()
                status = "failed"
                error = str(exc)
                alerts_repo.update_run_metadata(
                    alert,
                    last_run_at=now,
                    last_new_jobs_count=0,
                    last_error=error,
                )
                raise
            finally:
                alerts_repo.complete_execution(
                    execution,
                    now=utc_now(),
                    status=status,
                    total_jobs_found=len(jobs),
                    new_jobs_count=len(new_jobs),
                    notified=notified,
                    discord_status=discord_status,
                    slack_status=slack_status,
                    error=error,
                )

            return execution.id
        finally:
            session.close()

    def test_notification(
        self, alert_id: str, *, now: datetime | None = None
    ) -> NotificationResult:
        """Send a test notification using the alert's configured webhooks."""
        alert = self._get_alert_or_raise(alert_id)
        test_job = JobDTO(
            id="test-job-id",
            source="test",
            title="Test Job Alert",
            company="Acme Corp",
            location="Remote",
            remote_type="remote",
            salary="$100k-$150k",
            equity=None,
            posted_at=now or utc_now(),
            source_url="https://example.com/jobs/test",
            fetched_at=now or utc_now(),
            summary="This is a test notification from your job alert.",
        )
        return self._notification_service.send(
            alert.name,
            [test_job],
            discord_webhook_url=alert.discord_webhook_url,
            slack_webhook_url=alert.slack_webhook_url,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_alert_or_raise(self, alert_id: str) -> JobAlert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise NotFoundError(f"Job alert {alert_id} not found", code="alert_not_found")
        return alert

    def _resolve_sources(self, payload: JobAlertInput, settings: Settings) -> list[str]:
        available = self._source_service.known_source_names(settings)
        search_input = self._alert_input_to_search_input(payload)
        return self._run_service.resolve_sources(search_input, available=available)

    def _apply_patch_validations(
        self, alert: JobAlert, patch: JobAlertPatch
    ) -> None:
        sources = (
            patch.sources
            if patch.sources is not None
            else json.loads(alert.sources_json)
        )
        search_input = SearchRunInput(
            q=patch.q if patch.q is not None else alert.q,
            location=patch.location if patch.location is not None else alert.location,
            remote=patch.remote if patch.remote is not None else alert.remote,
            sources=sources,
            limit=patch.limit if patch.limit is not None else alert.limit,
        )
        self._run_service.resolve_sources(
            search_input,
            available=self._source_service.known_source_names(self._settings_factory()),
        )

    @staticmethod
    def _alert_to_search_input(alert: JobAlert) -> SearchRunInput:
        return SearchRunInput(
            q=alert.q,
            location=alert.location,
            remote=alert.remote,
            sources=json.loads(alert.sources_json) or None,
            limit=alert.limit,
        )

    @staticmethod
    def _alert_input_to_search_input(payload: JobAlertInput) -> SearchRunInput:
        return SearchRunInput(
            q=payload.q,
            location=payload.location,
            remote=payload.remote,
            sources=payload.sources,
            limit=payload.limit,
        )

    @staticmethod
    def _split_page(rows: list, limit: int) -> tuple[list, int | None]:
        if len(rows) > limit:
            return list(rows[:limit]), limit
        return list(rows), None
