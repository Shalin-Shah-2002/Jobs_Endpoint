from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.schemas.dto import SourceErrorDTO


@dataclass
class JobCandidate:
    source: str
    source_job_id: str | None
    title: str
    company: str
    location: str | None
    remote_type: str | None
    salary: str | None
    equity: str | None
    posted_at: datetime | None
    source_url: str
    summary: str | None
    raw: dict[str, object] = field(default_factory=dict)


@dataclass
class SourceSearchResult:
    jobs: list[JobCandidate] = field(default_factory=list)
    errors: list[SourceErrorDTO] = field(default_factory=list)


@dataclass(frozen=True)
class SourceInfo:
    name: str
    enabled: bool
    status: str
    reason: str | None = None
    docs_url: str | None = None


class SourceAdapter(Protocol):
    name: str
    enabled: bool
    info: SourceInfo

    def search(
        self,
        *,
        q: str,
        location: str | None,
        remote: bool | None,
        limit: int,
    ) -> SourceSearchResult:
        """Return normalized job candidates or structured source errors."""
