from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Query
from sqlalchemy.orm import Session

from app.controllers.base import BaseController
from app.core.pagination import decode_cursor
from app.schemas.dto import JobDTO, JobListDTO
from app.services.job_service import JobService


class JobController(BaseController):
    """Thin HTTP layer for /jobs endpoints. Pure delegation, no FastAPI deps."""

    def list_jobs(
        self,
        *,
        q: str | None,
        location: str | None,
        remote: bool | None,
        source: str | None,
        posted_after: datetime | None,
        limit: int,
        cursor: str,
        session: Session,
    ) -> JobListDTO:
        service: JobService = self.container.job_service(session)
        return service.list_jobs(
            q=q.strip() if q else None,
            location=location.strip() if location else None,
            remote=remote,
            source=source.strip().lower() if source else None,
            posted_after=posted_after,
            limit=limit,
            offset=decode_cursor(cursor),
        )

    def get_job(self, job_id: str, *, session: Session) -> JobDTO:
        service: JobService = self.container.job_service(session)
        return JobDTO.model_validate(service.get_by_id(job_id))
