from __future__ import annotations

from datetime import datetime
from typing import Sequence

from app.core.errors import NotFoundError
from app.core.pagination import encode_cursor
from app.models.job import Job
from app.models.search_run import SearchRun
from app.repositories.job_repository import JobRepository
from app.schemas.dto import JobDTO, JobListDTO


class JobService:
    def __init__(self, jobs: JobRepository) -> None:
        self._jobs = jobs

    def get_by_id(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found", code="job_not_found")
        return job

    def list_jobs(
        self,
        *,
        q: str | None,
        location: str | None,
        remote: bool | None,
        source: str | None,
        posted_after: datetime | None,
        limit: int,
        offset: int,
    ) -> JobListDTO:
        stmt = self._jobs.search(
            q=q,
            location=location,
            remote=remote,
            source=source,
            posted_after=posted_after,
        )
        rows = self._jobs.paginate(stmt, limit=limit, offset=offset)
        items, next_offset = self._split_page(rows, limit)
        return JobListDTO(
            items=[JobDTO.model_validate(j) for j in items],
            limit=limit,
            next_cursor=encode_cursor(next_offset) if next_offset is not None else None,
        )

    def list_for_run(self, run_id: str, *, limit: int, offset: int) -> JobListDTO:
        if self._jobs.session.get(SearchRun, run_id) is None:
            raise NotFoundError(f"Search run {run_id} not found", code="run_not_found")
        rows = self._jobs.list_for_run(run_id, limit=limit, offset=offset)
        items, next_offset = self._split_page(rows, limit)
        return JobListDTO(
            items=[JobDTO.model_validate(j) for j in items],
            limit=limit,
            next_cursor=encode_cursor(next_offset) if next_offset is not None else None,
        )

    @staticmethod
    def _split_page(rows: Sequence[Job], limit: int) -> tuple[list[Job], int | None]:
        if len(rows) > limit:
            return list(rows[:limit]), limit
        return list(rows), None
