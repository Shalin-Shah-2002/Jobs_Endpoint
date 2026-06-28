from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.search_run import SearchRun, SearchRunJob
from app.schemas.dto import SearchRunInput


class SearchRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, run_id: str) -> SearchRun | None:
        return self._session.get(SearchRun, run_id)

    def create(self, payload: SearchRunInput, sources: list[str], *, now: datetime) -> SearchRun:
        import json

        run = SearchRun(
            id=str(uuid4()),
            q=payload.q,
            location=payload.location,
            remote=payload.remote,
            sources_json=json.dumps(sources, separators=(",", ":")),
            limit=payload.limit,
            status="pending",
            requested_at=now,
            total_jobs=0,
            error_count=0,
            errors_json="[]",
        )
        self._session.add(run)
        self._session.commit()
        self._session.refresh(run)
        return run

    def mark_running(self, run: SearchRun, *, now: datetime) -> None:
        run.status = "running"
        run.started_at = now
        self._session.commit()

    def attach_job(self, run_id: str, job_id: str, source: str, *, now: datetime) -> bool:
        existing = self._session.get(SearchRunJob, {"run_id": run_id, "job_id": job_id})
        if existing is not None:
            return False
        self._session.add(
            SearchRunJob(run_id=run_id, job_id=job_id, source=source, attached_at=now)
        )
        return True

    def complete(
        self,
        run: SearchRun,
        *,
        now: datetime,
        status: str,
        total_jobs: int,
        error_count: int,
        errors: list[dict],
    ) -> None:
        import json

        run.status = status
        run.completed_at = now
        run.total_jobs = total_jobs
        run.error_count = error_count
        run.errors_json = json.dumps(errors, separators=(",", ":"))
        self._session.commit()

    def list_statuses(self) -> dict[str, SearchRun]:
        rows = self._session.execute(select(SearchRun)).scalars().all()
        return {row.id: row for row in rows}
