from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceErrorDTO(BaseModel):
    source: str
    code: str
    message: str
    retryable: bool = False


class SourceDTO(BaseModel):
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


class JobDTO(BaseModel):
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


class JobListDTO(BaseModel):
    items: list[JobDTO]
    limit: int
    next_cursor: str | None = None


class SearchRunInput(BaseModel):
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


class SearchRunOutput(BaseModel):
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
    errors: list[SourceErrorDTO]


class JobAlertInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    q: str = Field(..., min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    remote: bool | None = None
    sources: list[str] | None = None
    limit: int = Field(default=25, ge=1, le=100)
    check_interval_minutes: int = Field(default=60, ge=5, le=10080)
    discord_webhook_url: str | None = Field(default=None, max_length=1024)
    slack_webhook_url: str | None = Field(default=None, max_length=1024)
    enabled: bool = True

    @field_validator("q", "location", "name", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("q", "name")
    @classmethod
    def required_after_strip(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Field is required")
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

    @field_validator("discord_webhook_url", "slack_webhook_url", mode="before")
    @classmethod
    def strip_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("discord_webhook_url", "slack_webhook_url")
    @classmethod
    def url_must_be_http(cls, value: str | None) -> str | None:
        if value is not None and not (
            value.startswith("http://") or value.startswith("https://")
        ):
            raise ValueError("Webhook URL must start with http:// or https://")
        return value


class JobAlertPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    q: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    remote: bool | None = None
    sources: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=100)
    check_interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    discord_webhook_url: str | None = Field(default=None, max_length=1024)
    slack_webhook_url: str | None = Field(default=None, max_length=1024)
    enabled: bool | None = None

    @field_validator("q", "location", "name", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
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

    @field_validator("discord_webhook_url", "slack_webhook_url", mode="before")
    @classmethod
    def strip_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("discord_webhook_url", "slack_webhook_url")
    @classmethod
    def url_must_be_http(cls, value: str | None) -> str | None:
        if value is not None and not (
            value.startswith("http://") or value.startswith("https://")
        ):
            raise ValueError("Webhook URL must start with http:// or https://")
        return value


class JobAlertDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    q: str
    location: str | None = None
    remote: bool | None = None
    sources: list[str]
    limit: int
    check_interval_minutes: int
    discord_webhook_url: str | None = None
    slack_webhook_url: str | None = None
    enabled: bool
    last_run_at: datetime | None = None
    last_new_jobs_count: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class JobAlertExecutionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alert_id: str
    run_id: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    total_jobs_found: int
    new_jobs_count: int
    notified: bool
    discord_status: str | None = None
    slack_status: str | None = None
    error: str | None = None


class JobAlertExecutionListDTO(BaseModel):
    items: list[JobAlertExecutionDTO]
    limit: int
    next_cursor: str | None = None


class JobAlertTestResultDTO(BaseModel):
    message: str
    discord_status: str | None = None
    slack_status: str | None = None


class HealthDTO(BaseModel):
    status: str
    database: str
    enabled_sources: list[str]


class WebhookSubscriptionInput(BaseModel):
    url: str = Field(..., min_length=1, max_length=1024)
    secret: str = Field(..., min_length=8, max_length=255)
    source: str = Field(..., min_length=1, max_length=50)
    query: str = Field(..., min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    remote: bool | None = None
    poll_interval_seconds: int = Field(default=900, ge=60, le=86400)
    enabled: bool = True

    @field_validator("url", mode="before")
    @classmethod
    def strip_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str | None) -> str:
        if not value:
            raise ValueError("URL is required")
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value

    @field_validator("source", "query", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("query")
    @classmethod
    def query_is_required_after_strip(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Search query is required")
        return value

    @field_validator("source")
    @classmethod
    def source_lowercase(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Source is required")
        return value.lower()


class WebhookSubscriptionPatch(BaseModel):
    url: str | None = Field(default=None, min_length=1, max_length=1024)
    secret: str | None = Field(default=None, min_length=8, max_length=255)
    location: str | None = Field(default=None, max_length=120)
    remote: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=60, le=86400)
    enabled: bool | None = None

    @field_validator("url", mode="before")
    @classmethod
    def strip_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str | None) -> str | None:
        if value and not (
            value.startswith("http://") or value.startswith("https://")
        ):
            raise ValueError("URL must start with http:// or https://")
        return value


class WebhookSubscriptionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    source: str
    query: str
    location: str | None = None
    remote: bool | None = None
    poll_interval_seconds: int
    enabled: bool
    last_polled_at: datetime | None = None
    last_delivered_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreatedDTO(BaseModel):
    id: str
    secret: str
    url: str
    source: str
    query: str
    location: str | None = None
    poll_interval_seconds: int
    enabled: bool
    created_at: datetime


class WebhookDeliveryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    subscription_id: str
    job_id: str
    delivered_at: datetime
    status_code: int | None
    attempt_count: int
    response_excerpt: str | None = None


class WebhookDeliveryListDTO(BaseModel):
    items: list[WebhookDeliveryDTO]
    limit: int
    next_cursor: str | None = None
