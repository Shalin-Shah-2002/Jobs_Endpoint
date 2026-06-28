from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.controllers.base import BaseController
from app.schemas.dto import SourceDTO
from app.services.source_service import SourceService
from app.views.source_view import SourceView


class SourceController(BaseController):
    def list_sources(self, *, session: Session) -> list[SourceDTO]:
        settings: object = self.request.app.state.settings
        service: SourceService = self.container.source_service(session)
        return SourceView.to_dtos(service.list_sources(settings))
