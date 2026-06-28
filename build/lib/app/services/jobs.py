from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Job, SearchRun, SearchRunJob, SourceStatus
from app.schemas import SearchRunCreate, SearchRunResponse, SourceError
from app.sources import build_source_registry
from app.sources.base import JobCandidate, SourceAdapter


def utc_now() -> datetime:
    return datetime.now(UTC)


def json_dumps(value: object) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def parse_errors(errors_json: str | None) -> list[SourceError]:
    if not errors_json:
        return []
    return [SourceError(**item) for item in json.loads(errors_json)]


def create_search_run(db: Session, payload: SearchRunCreate, selected_sources: list[str]) -> SearchRun:
    run = SearchRun(
        id=str(uuid4()),
        q=payload.q,
        location=payload.location,
        remote=payload.remote,
        sources_json=json_dumps(selected_sources),
        limit=payload.limit,
        status="pending",
        requested_at=utc_now(),
        total_jobs=0,
        error_count=0,
        errors_json="[]",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def search_run_to_response(run: SearchRun) -> SearchRunResponse:
    return SearchRunResponse(
        id=run.id,
        q=run.q,
        location=run.location,
        remote=run.remote,
        sources=json.loads(run.sources_json),
        limit=run.limit,
        status=run.status,
        requested_at=run.requested_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        total_jobs=run.total_jobs,
        error_count=run.error_count,
        errors=parse_errors(run.errors_json),
    )


def upsert_job(db: Session, candidate: JobCandidate) -> Job:
    now = utc_now()
    existing = db.execute(
        select(Job).where(
            Job.source == candidate.source,
            Job.source_url == candidate.source_url,
        )
    ).scalar_one_or_none()

    raw_json = json_dumps(candidate.raw)
    if existing:
        existing.source_job_id = candidate.source_job_id
        existing.title = candidate.title
        existing.company = candidate.company
        existing.location = candidate.location
        existing.remote_type = candidate.remote_type
        existing.salary = candidate.salary
        existing.equity = candidate.equity
        existing.posted_at = candidate.posted_at
        existing.fetched_at = now
        existing.summary = candidate.summary
        existing.raw_json = raw_json
        return existing

    job = Job(
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
        raw_json=raw_json,
    )
    db.add(job)
    return job


def attach_job_to_run(db: Session, run_id: str, job: Job) -> None:
    existing = db.get(SearchRunJob, {"run_id": run_id, "job_id": job.id})
    if existing:
        return
    db.add(
        SearchRunJob(
            run_id=run_id,
            job_id=job.id,
            source=job.source,
            attached_at=utc_now(),
        )
    )


def record_source_status(
    db: Session,
    adapter: SourceAdapter,
    *,
    status: str,
    error: SourceError | None = None,
) -> None:
    source_status = db.get(SourceStatus, adapter.name)
    if source_status is None:
        source_status = SourceStatus(source=adapter.name)
        db.add(source_status)

    source_status.enabled = adapter.enabled
    source_status.status = status
    source_status.reason = adapter.info.reason
    source_status.docs_url = adapter.info.docs_url
    source_status.last_checked_at = utc_now()

    if error:
        source_status.last_error_at = utc_now()
        source_status.last_error_code = error.code
        source_status.last_error_message = error.message
    elif status == "ready":
        source_status.last_success_at = utc_now()
        source_status.last_error_code = None
        source_status.last_error_message = None


def execute_search_run(
    run_id: str,
    payload: SearchRunCreate,
    selected_sources: list[str],
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    db = session_factory()
    registry = build_source_registry(settings)
    all_errors: list[SourceError] = []
    total_jobs = 0

    try:
        run = db.get(SearchRun, run_id)
        if run is None:
            return

        run.status = "running"
        run.started_at = utc_now()
        db.commit()

        for source_name in selected_sources:
            adapter = registry[source_name]
            result = adapter.search(
                q=payload.q,
                location=payload.location,
                remote=payload.remote,
                limit=payload.limit,
            )

            source_error = result.errors[0] if result.errors else None
            record_source_status(
                db,
                adapter,
                status="error" if source_error else adapter.info.status,
                error=source_error,
            )

            for error in result.errors:
                all_errors.append(error)

            for candidate in result.jobs:
                job = upsert_job(db, candidate)
                db.flush()
                attach_job_to_run(db, run_id, job)
                total_jobs += 1

        run.status = "completed"
        run.completed_at = utc_now()
        run.total_jobs = total_jobs
        run.error_count = len(all_errors)
        run.errors_json = json_dumps([error.model_dump() for error in all_errors])
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(SearchRun, run_id)
        if run:
            error = SourceError(
                source="service",
                code="search_run_failed",
                message="Search run failed before completion",
                retryable=True,
            )
            run.status = "failed"
            run.completed_at = utc_now()
            run.error_count = 1
            run.errors_json = json_dumps([error.model_dump()])
            db.commit()
        raise exc
    finally:
        db.close()


def apply_job_filters(
    stmt: Select[tuple[Job]],
    *,
    q: str | None,
    location: str | None,
    remote: bool | None,
    source: str | None,
    posted_after: datetime | None,
) -> Select[tuple[Job]]:
    if q:
        query = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Job.title).like(query),
                func.lower(Job.company).like(query),
                func.lower(Job.summary).like(query),
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


def paginate_jobs(
    db: Session,
    stmt: Select[tuple[Job]],
    *,
    limit: int,
    cursor: int,
) -> tuple[list[Job], str | None]:
    rows = db.execute(
        stmt.order_by(Job.fetched_at.desc(), Job.posted_at.desc()).offset(cursor).limit(limit + 1)
    ).scalars().all()
    next_cursor = str(cursor + limit) if len(rows) > limit else None
    return rows[:limit], next_cursor


def known_source_names(settings: Settings) -> set[str]:
    return set(build_source_registry(settings).keys())


def default_enabled_sources(settings: Settings) -> list[str]:
    return [
        name
        for name, adapter in build_source_registry(settings).items()
        if adapter.enabled
    ]


def validate_sources_or_raise(settings: Settings, sources: Iterable[str]) -> None:
    known = known_source_names(settings)
    unknown = sorted(set(sources) - known)
    if unknown:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source(s): {', '.join(unknown)}",
        )

