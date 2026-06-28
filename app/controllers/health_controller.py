from __future__ import annotations

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.controllers.base import BaseController
from app.schemas.dto import HealthDTO
from app.services.source_service import SourceService


class HealthController(BaseController):
    def health(self, request: Request, *, session: Session) -> HealthDTO:
        engine = request.app.state.engine
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        service: SourceService = self.container.source_service(session)
        enabled = service.enabled_source_names(request.app.state.settings)
        return HealthDTO(status="ok", database="ok", enabled_sources=enabled)
