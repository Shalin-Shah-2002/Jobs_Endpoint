"""View layer mapping job-alert ORM models to Pydantic DTOs."""

import json

from app.models.job_alert import JobAlert, JobAlertExecution
from app.schemas.dto import JobAlertDTO, JobAlertExecutionDTO


class JobAlertView:
    @staticmethod
    def to_dto(alert: JobAlert) -> JobAlertDTO:
        return JobAlertDTO(
            id=alert.id,
            name=alert.name,
            q=alert.q,
            location=alert.location,
            remote=alert.remote,
            sources=json.loads(alert.sources_json),
            limit=alert.limit,
            check_interval_minutes=alert.check_interval_minutes,
            discord_webhook_url=alert.discord_webhook_url,
            slack_webhook_url=alert.slack_webhook_url,
            enabled=alert.enabled,
            last_run_at=alert.last_run_at,
            last_new_jobs_count=alert.last_new_jobs_count,
            last_error=alert.last_error,
            created_at=alert.created_at,
            updated_at=alert.updated_at,
        )


class JobAlertExecutionView:
    @staticmethod
    def to_dto(execution: JobAlertExecution) -> JobAlertExecutionDTO:
        return JobAlertExecutionDTO(
            id=execution.id,
            alert_id=execution.alert_id,
            run_id=execution.run_id,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            status=execution.status,
            total_jobs_found=execution.total_jobs_found,
            new_jobs_count=execution.new_jobs_count,
            notified=execution.notified,
            discord_status=execution.discord_status,
            slack_status=execution.slack_status,
            error=execution.error,
        )
