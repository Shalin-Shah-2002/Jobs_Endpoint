"""APScheduler-based periodic alert runner with SQLite job-store persistence."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.repositories.job_alert_repository import JobAlertRepository
from app.services.clock import utc_now
from app.services.job_alert_service import JobAlertService


# Module-level reference to the currently active scheduler instance. APScheduler
# persists only the function reference for interval jobs, so this lets the
# scheduled job reach the live scheduler without pickling the app object.
_current_scheduler: "AlertScheduler | None" = None


def _tick_job() -> None:
    """APScheduler entry point — delegates to the active scheduler instance."""
    if _current_scheduler is not None:
        _current_scheduler.tick()


class AlertScheduler:
    """Periodically checks enabled job alerts and executes the ones that are due."""

    def __init__(
        self,
        *,
        engine: Engine,
        session_factory: sessionmaker[Session],
        container: Container,
        settings: Settings,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._container = container
        self._settings = settings
        self._scheduler = BackgroundScheduler(
            jobstores={
                "default": SQLAlchemyJobStore(engine=engine),
            },
        )

    def start(self) -> None:
        global _current_scheduler
        _current_scheduler = self
        self._scheduler.add_job(
            _tick_job,
            "interval",
            seconds=self._settings.alert_check_interval_seconds,
            id="job_alert_tick",
            replace_existing=True,
            max_instances=1,
        )
        self._scheduler.start()

    def stop(self) -> None:
        global _current_scheduler
        try:
            self._scheduler.shutdown(wait=False)
        finally:
            _current_scheduler = None

    def tick(self) -> None:
        """Run every enabled alert whose interval has elapsed."""
        session = self._session_factory()
        try:
            alerts_repo = JobAlertRepository(session)
            job_alert_service = self._container.job_alert_service(session)
            now = utc_now()
            for alert in alerts_repo.list_all(enabled_only=True):
                if self._is_due(alert, now):
                    try:
                        job_alert_service.execute_alert(alert.id, now=now)
                    except Exception:
                        # Log and continue so one failing alert does not block others.
                        # The exception is already recorded on the execution row.
                        continue
        finally:
            session.close()

    @staticmethod
    def _is_due(alert: Any, now: datetime) -> bool:
        if alert.last_run_at is None:
            return True
        interval = timedelta(minutes=alert.check_interval_minutes)
        last_run = alert.last_run_at
        # SQLite stores datetimes without timezone info; assume UTC when naive.
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=now.tzinfo)
        return last_run + interval <= now
