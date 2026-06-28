from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.sources.base import JobCandidate


class JobRepository:
    """Data access for jobs. Knows SQL, not business rules."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, job_id: str) -> Job | None:
        return self._session.get(Job, job_id)

    def find_by_source_url(self, source: str, source_url: str) -> Job | None:
        return self._session.execute(
            select(Job).where(Job.source == source, Job.source_url == source_url)
        ).scalar_one_or_none()

    def upsert_from_candidate(self, candidate: JobCandidate, *, now: datetime) -> Job:
        existing = self.find_by_source_url(candidate.source, candidate.source_url)
        if existing is not None:
            self._update(existing, candidate, now)
            return existing
        job = self._build(candidate, now)
        self._session.add(job)
        return job

    def search(
        self,
        *,
        q: str | None,
        location: str | None,
        remote: bool | None,
        source: str | None,
        posted_after: datetime | None,
    ) -> Select[tuple[Job]]:
        stmt = select(Job)
        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Job.title).like(pattern),
                    func.lower(Job.company).like(pattern),
                    func.lower(Job.summary).like(pattern),
                )
            )
        if location:
            stmt = stmt.where(func.lower(Job.location).like(f"%{location.lower()}%"))
        if remote is True:
            stmt = stmt.where(Job.remote_type == "remote")
        elif remote is False:
            stmt = stmt.where(and_(Job.remote_type.is_not(None), Job.remote_type != "remote"))
        if source:
            stmt = stmt.where(Job.source == source.lower())
        if posted_after:
            stmt = stmt.where(Job.posted_at.is_not(None), Job.posted_at >= posted_after)
        return stmt

    def paginate(self, stmt: Select[tuple[Job]], *, limit: int, offset: int) -> Sequence[Job]:
        return (
            self._session.execute(
                stmt.order_by(Job.fetched_at.desc(), Job.posted_at.desc())
                .offset(offset)
                .limit(limit + 1)
            )
            .scalars()
            .all()
        )

    def list_for_run(
        self, run_id: str, *, limit: int, offset: int
    ) -> Sequence[Job]:
        from app.models.search_run import SearchRunJob

        stmt = (
            select(Job)
            .join(SearchRunJob, SearchRunJob.job_id == Job.id)
            .where(SearchRunJob.run_id == run_id)
        )
        return self.paginate(stmt, limit=limit, offset=offset)

    def _update(self, job: Job, candidate: JobCandidate, now: datetime) -> None:
        import json

        job.source_job_id = candidate.source_job_id
        job.title = candidate.title
        job.company = candidate.company
        job.location = candidate.location
        job.remote_type = candidate.remote_type
        job.salary = candidate.salary
        job.equity = candidate.equity
        job.posted_at = candidate.posted_at
        job.fetched_at = now
        job.summary = candidate.summary
        job.raw_json = json.dumps(candidate.raw, default=str, separators=(",", ":"))

    def _build(self, candidate: JobCandidate, now: datetime) -> Job:
        import json
        from uuid import uuid4

        return Job(
            id=str(uuid4()),
            source=candidate.source,
            source_job_id=candidate.source_job_id,
            title=candidate.title,
            company=candidate.company,
            location=candidate.location,
            remote_type=candidate.remote_type,
            salary=candidate.salary,
            equity=candidate.equity,
            posted_at=candidate.posted_at,
            source_url=candidate.source_url,
            fetched_at=now,
            summary=candidate.summary,
            raw_json=json.dumps(candidate.raw, default=str, separators=(",", ":")),
        )
