"""Composition root — wires repositories and services per request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.repositories.job_alert_repository import JobAlertRepository
from app.repositories.job_repository import JobRepository
from app.repositories.search_run_repository import SearchRunRepository
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.job_alert_service import JobAlertService
from app.services.job_service import JobService
from app.services.notification_service import NotificationService
from app.services.search_run_service import SearchRunService
from app.services.source_service import SourceService
from app.sources.base import SourceAdapter
from app.sources.registry import build_source_registry


@dataclass
class Container:
    """Builds services scoped to a request session.

    Repositories are cheap to construct, so we rebuild them per request to
    keep session ownership simple and thread-safe.
    """

    session_factory: sessionmaker[Session]
    registry_factory: Callable[..., dict[str, SourceAdapter]] = build_source_registry

    def job_repository(self, session: Session) -> JobRepository:
        return JobRepository(session)

    def search_run_repository(self, session: Session) -> SearchRunRepository:
        return SearchRunRepository(session)

    def source_status_repository(self, session: Session) -> SourceStatusRepository:
        return SourceStatusRepository(session)

    def job_service(self, session: Session) -> JobService:
        return JobService(self.job_repository(session))

    def source_service(self, session: Session) -> SourceService:
        return SourceService(
            self.source_status_repository(session),
            registry_factory=self.registry_factory,
        )

    def search_run_service(self, session: Session) -> SearchRunService:
        return SearchRunService(
            runs=self.search_run_repository(session),
            jobs=self.job_repository(session),
            statuses=self.source_status_repository(session),
            registry_factory=self.registry_factory,
            session_factory=self.session_factory,
        )

    def job_alert_repository(self, session: Session) -> JobAlertRepository:
        return JobAlertRepository(session)

    def notification_service(self) -> NotificationService:
        return NotificationService(
            timeout_seconds=get_settings().notification_timeout_seconds
        )

    def job_alert_service(self, session: Session) -> JobAlertService:
        return JobAlertService(
            alerts=self.job_alert_repository(session),
            runs=self.search_run_repository(session),
            run_service=self.search_run_service(session),
            source_service=self.source_service(session),
            session_factory=self.session_factory,
            settings_factory=get_settings,
            notification_service=self.notification_service(),
        )
