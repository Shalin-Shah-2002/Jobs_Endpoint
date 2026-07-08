"""Data access for job alerts, their executions, and seen-job tracking."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Sequence
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.job_alert import JobAlert, JobAlertExecution, JobAlertSeenJob
from app.models.search_run import SearchRunJob
from app.schemas.dto import JobAlertInput, JobAlertPatch


class JobAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, alert_id: str) -> JobAlert | None:
        return self._session.get(JobAlert, alert_id)

    def list_all(self, *, enabled_only: bool = False) -> list[JobAlert]:
        stmt = select(JobAlert)
        if enabled_only:
            stmt = stmt.where(JobAlert.enabled.is_(True))
        stmt = stmt.order_by(JobAlert.created_at.desc())
        return list(self._session.execute(stmt).scalars().all())

    def create(self, payload: JobAlertInput, *, now: datetime) -> JobAlert:
        alert = JobAlert(
            id=str(uuid4()),
            name=payload.name,
            q=payload.q,
            location=payload.location,
            remote=payload.remote,
            sources_json=json.dumps(payload.sources or [], separators=(",", ":")),
            limit=payload.limit,
            check_interval_minutes=payload.check_interval_minutes,
            discord_webhook_url=payload.discord_webhook_url,
            slack_webhook_url=payload.slack_webhook_url,
            enabled=payload.enabled,
            created_at=now,
            updated_at=now,
        )
        self._session.add(alert)
        self._session.commit()
        self._session.refresh(alert)
        return alert

    def update(self, alert: JobAlert, patch: JobAlertPatch, *, now: datetime) -> JobAlert:
        if patch.name is not None:
            alert.name = patch.name
        if patch.q is not None:
            alert.q = patch.q
        if patch.location is not None:
            alert.location = patch.location
        if patch.remote is not None:
            alert.remote = patch.remote
        if patch.sources is not None:
            alert.sources_json = json.dumps(patch.sources, separators=(",", ":"))
        if patch.limit is not None:
            alert.limit = patch.limit
        if patch.check_interval_minutes is not None:
            alert.check_interval_minutes = patch.check_interval_minutes
        if patch.discord_webhook_url is not None:
            alert.discord_webhook_url = patch.discord_webhook_url
        if patch.slack_webhook_url is not None:
            alert.slack_webhook_url = patch.slack_webhook_url
        if patch.enabled is not None:
            alert.enabled = patch.enabled
        alert.updated_at = now
        self._session.commit()
        self._session.refresh(alert)
        return alert

    def delete(self, alert: JobAlert) -> None:
        self._session.delete(alert)
        self._session.commit()

    def update_run_metadata(
        self,
        alert: JobAlert,
        *,
        last_run_at: datetime,
        last_new_jobs_count: int,
        last_error: str | None,
    ) -> None:
        alert.last_run_at = last_run_at
        alert.last_new_jobs_count = last_new_jobs_count
        alert.last_error = last_error
        self._session.commit()

    def create_execution(
        self,
        alert_id: str,
        *,
        now: datetime,
        run_id: str | None = None,
    ) -> JobAlertExecution:
        execution = JobAlertExecution(
            id=str(uuid4()),
            alert_id=alert_id,
            run_id=run_id,
            started_at=now,
            status="running",
        )
        self._session.add(execution)
        self._session.commit()
        self._session.refresh(execution)
        return execution

    def complete_execution(
        self,
        execution: JobAlertExecution,
        *,
        now: datetime,
        status: str,
        total_jobs_found: int,
        new_jobs_count: int,
        notified: bool,
        discord_status: str | None,
        slack_status: str | None,
        error: str | None,
    ) -> None:
        execution.completed_at = now
        execution.status = status
        execution.total_jobs_found = total_jobs_found
        execution.new_jobs_count = new_jobs_count
        execution.notified = notified
        execution.discord_status = discord_status
        execution.slack_status = slack_status
        execution.error = error
        self._session.commit()

    def get_execution(self, execution_id: str) -> JobAlertExecution | None:
        return self._session.get(JobAlertExecution, execution_id)

    def list_executions(
        self,
        alert_id: str,
        *,
        limit: int,
        offset: int,
    ) -> Sequence[JobAlertExecution]:
        stmt = (
            select(JobAlertExecution)
            .where(JobAlertExecution.alert_id == alert_id)
            .order_by(JobAlertExecution.started_at.desc())
            .limit(limit + 1)
            .offset(offset)
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_jobs_for_run(self, run_id: str, *, limit: int, offset: int) -> Sequence[Job]:
        stmt = (
            select(Job)
            .join(SearchRunJob, Job.id == SearchRunJob.job_id)
            .where(SearchRunJob.run_id == run_id)
            .order_by(Job.fetched_at.desc(), Job.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
        return list(self._session.execute(stmt).scalars().all())

    def mark_jobs_seen(
        self,
        alert_id: str,
        job_ids: Sequence[str],
        *,
        now: datetime,
    ) -> int:
        if not job_ids:
            return 0
        seen = [
            JobAlertSeenJob(alert_id=alert_id, job_id=job_id, seen_at=now)
            for job_id in job_ids
        ]
        self._session.bulk_save_objects(seen)
        self._session.commit()
        return len(seen)

    def filter_seen_job_ids(self, alert_id: str, job_ids: Sequence[str]) -> set[str]:
        if not job_ids:
            return set()
        stmt = select(JobAlertSeenJob.job_id).where(
            JobAlertSeenJob.alert_id == alert_id,
            JobAlertSeenJob.job_id.in_(job_ids),
        )
        return set(self._session.execute(stmt).scalars().all())

    def count(self) -> int:
        return self._session.execute(select(func.count()).select_from(JobAlert)).scalar() or 0

    _WEBHOOK_URL_COLUMNS = {"discord_webhook_url", "slack_webhook_url"}

    def list_distinct_webhook_urls(self, column: str) -> list[str]:
        """Return distinct non-empty webhook URL values for *column*.

        *column* must be one of ``{"discord_webhook_url", "slack_webhook_url"}``.
        """
        if column not in self._WEBHOOK_URL_COLUMNS:
            raise ValueError(f"Unknown webhook column: {column!r}")
        col = getattr(JobAlert, column)
        rows = (
            self._session.query(col)
            .filter(col.isnot(None), col != "")
            .distinct()
            .all()
        )
        return [r[0] for r in rows]
