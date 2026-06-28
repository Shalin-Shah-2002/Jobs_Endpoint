from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceError(BaseModel):
    source: str
    code: str
    message: str
    retryable: bool = False


class SourceResponse(BaseModel):
    name: str
    enabled: bool
    status: str
    reason: str | None = None
    docs_url: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    title: str
    company: str
    location: str | None = None
    remote_type: str | None = None
    salary: str | None = None
    equity: str | None = None
    posted_at: datetime | None = None
    source_url: str
    fetched_at: datetime
    summary: str | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    limit: int
    next_cursor: str | None = None


class SearchRunCreate(BaseModel):
    q: str = Field(..., min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    remote: bool | None = None
    sources: list[str] | None = None
    limit: int = Field(default=25, ge=1, le=100)

    @field_validator("q", "location", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("q")
    @classmethod
    def q_is_required_after_strip(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Search query is required")
        return value

    @field_validator("sources")
    @classmethod
    def normalize_sources(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for source in value:
            clean = source.strip().lower()
            if not clean:
                raise ValueError("Source names cannot be blank")
            if clean not in seen:
                normalized.append(clean)
                seen.add(clean)
        return normalized


class SearchRunResponse(BaseModel):
    id: str
    q: str
    location: str | None = None
    remote: bool | None = None
    sources: list[str]
    limit: int
    status: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_jobs: int
    error_count: int
    errors: list[SourceError]


class HealthResponse(BaseModel):
    status: str
    database: str
    enabled_sources: list[str]

