"""v1 API routes — thin glue between URL and controllers."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.controllers.health_controller import HealthController
from app.controllers.job_alert_controller import JobAlertController
from app.controllers.job_controller import JobController
from app.controllers.search_run_controller import SearchRunController
from app.controllers.source_controller import SourceController
from app.core.database import db_session
from app.core.exceptions import register_exception_handlers
from app.core.rate_limit import read_rate_limit, write_rate_limit
from app.core.security import require_api_key
from app.schemas.dto import (
    HealthDTO,
    JobAlertDTO,
    JobAlertExecutionListDTO,
    JobAlertInput,
    JobAlertPatch,
    JobAlertTestResultDTO,
    JobDTO,
    JobListDTO,
    SearchRunInput,
    SearchRunOutput,
    SourceDTO,
)


router = APIRouter(prefix="/api/v1")


def _make_job_controller(request: Request, session: Session = Depends(db_session)) -> JobController:
    return JobController(request)


def _make_search_run_controller(
    request: Request, session: Session = Depends(db_session)
) -> SearchRunController:
    return SearchRunController(request)


def _make_source_controller(
    request: Request, session: Session = Depends(db_session)
) -> SourceController:
    return SourceController(request)


def _make_job_alert_controller(
    request: Request, session: Session = Depends(db_session)
) -> JobAlertController:
    return JobAlertController(request)


@router.get("/sources", response_model=list[SourceDTO], dependencies=[Depends(read_rate_limit)])
def list_sources(
    controller: SourceController = Depends(_make_source_controller),
    session: Session = Depends(db_session),
) -> list[SourceDTO]:
    return controller.list_sources(session=session)


@router.get("/jobs", response_model=JobListDTO, dependencies=[Depends(read_rate_limit)])
def list_jobs(
    q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    location: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    remote: bool | None = None,
    source: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    posted_after: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str = Query(default=""),
    controller: JobController = Depends(_make_job_controller),
    session: Session = Depends(db_session),
) -> JobListDTO:
    return controller.list_jobs(
        q=q,
        location=location,
        remote=remote,
        source=source,
        posted_after=posted_after,
        limit=limit,
        cursor=cursor,
        session=session,
    )


@router.get("/jobs/{job_id}", response_model=JobDTO, dependencies=[Depends(read_rate_limit)])
def get_job(
    job_id: str,
    controller: JobController = Depends(_make_job_controller),
    session: Session = Depends(db_session),
) -> JobDTO:
    return controller.get_job(job_id, session=session)


@router.post(
    "/search-runs",
    response_model=SearchRunOutput,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(write_rate_limit), Depends(require_api_key)],
)
def create_search_run(
    payload: SearchRunInput,
    background_tasks: BackgroundTasks,
    request: Request,
    controller: SearchRunController = Depends(_make_search_run_controller),
    session: Session = Depends(db_session),
) -> SearchRunOutput:
    return controller.create_run(payload, background_tasks, request, session=session)


@router.get("/search-runs/{run_id}", response_model=SearchRunOutput, dependencies=[Depends(read_rate_limit)])
def get_search_run(
    run_id: str,
    controller: SearchRunController = Depends(_make_search_run_controller),
    session: Session = Depends(db_session),
) -> SearchRunOutput:
    return controller.get_run(run_id, session=session)


@router.get("/search-runs/{run_id}/jobs", response_model=JobListDTO, dependencies=[Depends(read_rate_limit)])
def get_search_run_jobs(
    run_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str = Query(default=""),
    controller: SearchRunController = Depends(_make_search_run_controller),
    session: Session = Depends(db_session),
) -> JobListDTO:
    return controller.list_jobs(run_id, limit=limit, cursor=cursor, session=session)


@router.post(
    "/alerts",
    response_model=JobAlertDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit), Depends(require_api_key)],
)
def create_alert(
    payload: JobAlertInput,
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> JobAlertDTO:
    return controller.create_alert(payload, session=session)


@router.get("/alerts", response_model=list[JobAlertDTO], dependencies=[Depends(read_rate_limit)])
def list_alerts(
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> list[JobAlertDTO]:
    return controller.list_alerts(session=session)


@router.get("/alerts/{alert_id}", response_model=JobAlertDTO, dependencies=[Depends(read_rate_limit)])
def get_alert(
    alert_id: str,
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> JobAlertDTO:
    return controller.get_alert(alert_id, session=session)


@router.patch(
    "/alerts/{alert_id}",
    response_model=JobAlertDTO,
    dependencies=[Depends(write_rate_limit), Depends(require_api_key)],
)
def update_alert(
    alert_id: str,
    patch: JobAlertPatch,
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> JobAlertDTO:
    return controller.update_alert(alert_id, patch, session=session)


@router.delete(
    "/alerts/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_rate_limit), Depends(require_api_key)],
)
def delete_alert(
    alert_id: str,
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> None:
    return controller.delete_alert(alert_id, session=session)


@router.get(
    "/alerts/{alert_id}/executions",
    response_model=JobAlertExecutionListDTO,
    dependencies=[Depends(read_rate_limit)],
)
def list_alert_executions(
    alert_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str = Query(default=""),
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> JobAlertExecutionListDTO:
    return controller.list_executions(alert_id, limit=limit, cursor=cursor, session=session)


@router.post(
    "/alerts/{alert_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(write_rate_limit), Depends(require_api_key)],
)
def run_alert(
    alert_id: str,
    background_tasks: BackgroundTasks,
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> dict:
    return controller.run_alert(alert_id, background_tasks, session=session)


@router.post(
    "/alerts/{alert_id}/test",
    response_model=JobAlertTestResultDTO,
    dependencies=[Depends(write_rate_limit), Depends(require_api_key)],
)
def test_alert(
    alert_id: str,
    controller: JobAlertController = Depends(_make_job_alert_controller),
    session: Session = Depends(db_session),
) -> JobAlertTestResultDTO:
    return controller.test_alert(alert_id, session=session)


health_router = APIRouter()


@health_router.get("/health", response_model=HealthDTO)
def health(
    request: Request,
    session: Session = Depends(db_session),
) -> HealthDTO:
    return HealthController(request).health(request, session=session)


__all__ = ["router", "health_router", "register_exception_handlers"]
