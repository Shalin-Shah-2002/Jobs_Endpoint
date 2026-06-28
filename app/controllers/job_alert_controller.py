"""HTTP controller for job alert CRUD, execution, and testing."""

from __future__ import annotations

from fastapi import BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.controllers.base import BaseController
from app.schemas.dto import (
    JobAlertDTO,
    JobAlertExecutionListDTO,
    JobAlertInput,
    JobAlertPatch,
    JobAlertTestResultDTO,
)
from app.services.clock import utc_now
from app.services.job_alert_service import JobAlertService


class JobAlertController(BaseController):
    def create_alert(
        self,
        payload: JobAlertInput,
        *,
        session: Session,
    ) -> JobAlertDTO:
        service: JobAlertService = self.container.job_alert_service(session)
        return service.create_alert(payload, now=utc_now())

    def list_alerts(
        self,
        *,
        session: Session,
    ) -> list[JobAlertDTO]:
        service: JobAlertService = self.container.job_alert_service(session)
        return service.list_alerts()

    def get_alert(
        self,
        alert_id: str,
        *,
        session: Session,
    ) -> JobAlertDTO:
        service: JobAlertService = self.container.job_alert_service(session)
        return service.get_alert(alert_id)

    def update_alert(
        self,
        alert_id: str,
        patch: JobAlertPatch,
        *,
        session: Session,
    ) -> JobAlertDTO:
        service: JobAlertService = self.container.job_alert_service(session)
        return service.update_alert(alert_id, patch, now=utc_now())

    def delete_alert(
        self,
        alert_id: str,
        *,
        session: Session,
    ) -> None:
        service: JobAlertService = self.container.job_alert_service(session)
        service.delete_alert(alert_id)

    def list_executions(
        self,
        alert_id: str,
        *,
        limit: int,
        cursor: str,
        session: Session,
    ) -> JobAlertExecutionListDTO:
        service: JobAlertService = self.container.job_alert_service(session)
        return service.list_executions(alert_id, limit=limit, cursor=cursor)

    def run_alert(
        self,
        alert_id: str,
        background_tasks: BackgroundTasks,
        *,
        session: Session,
    ) -> dict:
        service: JobAlertService = self.container.job_alert_service(session)
        background_tasks.add_task(service.execute_alert, alert_id)
        return {"message": "Alert execution started", "alert_id": alert_id}

    def test_alert(
        self,
        alert_id: str,
        *,
        session: Session,
    ) -> JobAlertTestResultDTO:
        service: JobAlertService = self.container.job_alert_service(session)
        result = service.test_notification(alert_id, now=utc_now())
        return JobAlertTestResultDTO(
            message="Test notification sent",
            discord_status=result.discord_status,
            slack_status=result.slack_status,
        )
