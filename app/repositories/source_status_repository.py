from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source_status import SourceStatus
from app.schemas.dto import SourceErrorDTO
from app.sources.base import SourceAdapter


class SourceStatusRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def list_all(self) -> dict[str, SourceStatus]:
        rows = self._session.execute(select(SourceStatus)).scalars().all()
        return {row.source: row for row in rows}

    def get(self, name: str) -> SourceStatus | None:
        return self._session.get(SourceStatus, name)

    def record(
        self,
        adapter: SourceAdapter,
        *,
        now: datetime,
        status: str,
        error: SourceErrorDTO | None = None,
    ) -> None:
        record = self.get(adapter.name)
        if record is None:
            record = SourceStatus(source=adapter.name)
            self._session.add(record)

        record.enabled = adapter.enabled
        record.status = status
        record.reason = adapter.info.reason
        record.docs_url = adapter.info.docs_url
        record.last_checked_at = now

        if error is not None:
            record.last_error_at = now
            record.last_error_code = error.code
            record.last_error_message = error.message
        elif status == "ready":
            record.last_success_at = now
            record.last_error_code = None
            record.last_error_message = None

        self._session.commit()
