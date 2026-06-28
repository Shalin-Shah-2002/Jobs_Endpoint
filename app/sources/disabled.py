from app.schemas.dto import SourceErrorDTO
from app.sources.base import SourceInfo, SourceSearchResult


class DisabledSource:
    def __init__(self, *, name: str, reason: str, docs_url: str | None = None) -> None:
        self.name = name
        self.enabled = False
        self.info = SourceInfo(
            name=name,
            enabled=False,
            status="disabled",
            reason=reason,
            docs_url=docs_url,
        )

    def search(
        self,
        *,
        q: str,
        location: str | None,
        remote: bool | None,
        limit: int,
    ) -> SourceSearchResult:
        return SourceSearchResult(
            errors=[
                SourceErrorDTO(
                    source=self.name,
                    code="source_disabled",
                    message=self.info.reason or f"{self.name} is disabled",
                    retryable=False,
                )
            ]
        )

