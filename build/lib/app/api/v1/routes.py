from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, SearchRun, SearchRunJob, SourceStatus
from app.rate_limit import read_rate_limit, write_rate_limit
from app.schemas import JobListResponse, JobResponse, SearchRunCreate, SearchRunResponse, SourceResponse
from app.security import require_api_key
from app.services.jobs import (
    apply_job_filters,
    create_search_run,
    default_enabled_sources,
    execute_search_run,
    paginate_jobs,
    search_run_to_response,
    validate_sources_or_raise,
)
from app.sources import build_source_registry


router = APIRouter(prefix="/api/v1")


@router.get("/sources", response_model=list[SourceResponse], dependencies=[Depends(read_rate_limit)])
def list_sources(request: Request, db: Session = Depends(get_db)) -> list[SourceResponse]:
    registry = build_source_registry(request.app.state.settings)
    db_statuses = {status.source: status for status in db.execute(select(SourceStatus)).scalars()}

    responses: list[SourceResponse] = []
    for name in sorted(registry):
        adapter = registry[name]
        db_status = db_statuses.get(name)
        responses.append(
            SourceResponse(
                name=name,
                enabled=adapter.enabled,
                status=db_status.status if db_status else adapter.info.status,
                reason=db_status.reason if db_status else adapter.info.reason,
                docs_url=db_status.docs_url if db_status else adapter.info.docs_url,
                last_checked_at=db_status.last_checked_at if db_status else None,
                last_success_at=db_status.last_success_at if db_status else None,
                last_error_at=db_status.last_error_at if db_status else None,
                last_error_code=db_status.last_error_code if db_status else None,
                last_error_message=db_status.last_error_message if db_status else None,
            )
        )
    return responses


@router.get("/jobs", response_model=JobListResponse, dependencies=[Depends(read_rate_limit)])
def list_jobs(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    location: str | None = Query(default=None, min_length=1, max_length=120),
    remote: bool | None = None,
    source: str | None = Query(default=None, min_length=1, max_length=50),
    posted_after: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JobListResponse:
    stmt = apply_job_filters(
        select(Job),
        q=q.strip() if q else None,
        location=location.strip() if location else None,
        remote=remote,
        source=source.strip().lower() if source else None,
        posted_after=posted_after,
    )
    jobs, next_cursor = paginate_jobs(db, stmt, limit=limit, cursor=cursor)
    return JobListResponse(items=jobs, limit=limit, next_cursor=next_cursor)


@router.get("/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(read_rate_limit)])
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post(
    "/search-runs",
    response_model=SearchRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(write_rate_limit), Depends(require_api_key)],
)
def create_run(
    payload: SearchRunCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> SearchRunResponse:
    settings = request.app.state.settings
    selected_sources = payload.sources or default_enabled_sources(settings)
    validate_sources_or_raise(settings, selected_sources)

    if not selected_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No enabled sources are configured",
        )

    run = create_search_run(db, payload, selected_sources)
    background_tasks.add_task(
        execute_search_run,
        run.id,
        payload,
        selected_sources,
        request.app.state.session_factory,
        settings,
    )
    return search_run_to_response(run)


@router.get("/search-runs/{run_id}", response_model=SearchRunResponse, dependencies=[Depends(read_rate_limit)])
def get_search_run(run_id: str, db: Session = Depends(get_db)) -> SearchRunResponse:
    run = db.get(SearchRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search run not found")
    return search_run_to_response(run)


@router.get(
    "/search-runs/{run_id}/jobs",
    response_model=JobListResponse,
    dependencies=[Depends(read_rate_limit)],
)
def get_search_run_jobs(
    run_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JobListResponse:
    if db.get(SearchRun, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search run not found")

    stmt = select(Job).join(SearchRunJob, SearchRunJob.job_id == Job.id).where(SearchRunJob.run_id == run_id)
    jobs, next_cursor = paginate_jobs(db, stmt, limit=limit, cursor=cursor)
    return JobListResponse(items=jobs, limit=limit, next_cursor=next_cursor)

