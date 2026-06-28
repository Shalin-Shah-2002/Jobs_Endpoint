from __future__ import annotations

from fastapi import BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.controllers.base import BaseController
from app.core.pagination import decode_cursor
from app.schemas.dto import JobListDTO, SearchRunInput, SearchRunOutput
from app.services.clock import utc_now
from app.services.search_run_service import SearchRunService
from app.views.search_run_view import SearchRunView


class SearchRunController(BaseController):
    def get_run(self, run_id: str, *, session: Session) -> SearchRunOutput:
        service: SearchRunService = self.container.search_run_service(session)
        return SearchRunView.to_dto(service.get(run_id))

    def list_jobs(
        self, run_id: str, *, limit: int, cursor: str, session: Session
    ) -> JobListDTO:
        service = self.container.job_service(session)
        return service.list_for_run(
            run_id, limit=limit, offset=decode_cursor(cursor)
        )

    def create_run(
        self,
        payload: SearchRunInput,
        background_tasks: BackgroundTasks,
        request: Request,
        *,
        session: Session,
    ) -> SearchRunOutput:
        settings = request.app.state.settings
        source_service = self.container.source_service(session)
        run_service = self.container.search_run_service(session)
        run_repo = self.container.search_run_repository(session)

        available = source_service.known_source_names(settings)
        selected = run_service.resolve_sources(payload, available=available)
        run = run_repo.create(payload, selected, now=utc_now())

        background_tasks.add_task(
            run_service.execute_in_background, run.id, payload, selected
        )
        return SearchRunView.to_dto(run)
