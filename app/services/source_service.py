from __future__ import annotations

from typing import Callable

from app.repositories.source_status_repository import SourceStatusRepository
from app.schemas.dto import SourceDTO
from app.sources.base import SourceAdapter
from app.sources.registry import build_source_registry


class SourceService:
    def __init__(
        self,
        statuses: SourceStatusRepository,
        registry_factory: Callable[..., dict[str, SourceAdapter]] = build_source_registry,
    ) -> None:
        self._statuses = statuses
        self._registry_factory = registry_factory

    def list_sources(self, settings) -> list[SourceDTO]:
        registry = self._registry_factory(settings)
        stored = self._statuses.list_all()
        out: list[SourceDTO] = []
        for name in sorted(registry):
            adapter = registry[name]
            record = stored.get(name)
            out.append(
                SourceDTO(
                    name=name,
                    enabled=adapter.enabled,
                    status=record.status if record else adapter.info.status,
                    reason=record.reason if record else adapter.info.reason,
                    docs_url=record.docs_url if record else adapter.info.docs_url,
                    last_checked_at=record.last_checked_at if record else None,
                    last_success_at=record.last_success_at if record else None,
                    last_error_at=record.last_error_at if record else None,
                    last_error_code=record.last_error_code if record else None,
                    last_error_message=record.last_error_message if record else None,
                )
            )
        return out

    def enabled_source_names(self, settings) -> list[str]:
        return [
            name
            for name, adapter in self._registry_factory(settings).items()
            if adapter.enabled
        ]

    def known_source_names(self, settings) -> list[str]:
        return list(self._registry_factory(settings).keys())
