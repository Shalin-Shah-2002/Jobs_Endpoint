"""Unit tests for JobService — business logic, no HTTP."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.repositories.job_repository import JobRepository
from app.services.job_service import JobService
from app.sources.base import JobCandidate


def _make_candidate(source_url: str, **kwargs) -> JobCandidate:
    base = dict(
        source="mock",
        source_job_id=source_url,
        title="Flutter Developer",
        company="OrbitLabs",
        location="Bengaluru, India",
        remote_type="remote",
        salary="INR 30L",
        equity=None,
        posted_at=datetime.now(UTC) - timedelta(days=1),
        source_url=source_url,
        summary="Flutter role",
        raw={},
    )
    base.update(kwargs)
    return JobCandidate(**base)


@pytest.fixture
def service(session: Session) -> JobService:
    repo = JobRepository(session)
    now = datetime.now(UTC)
    repo.upsert_from_candidate(
        _make_candidate("mock://a", title="Flutter Developer", summary="Flutter mobile role"),
        now=now,
    )
    repo.upsert_from_candidate(
        _make_candidate("mock://b", title="Python Engineer", summary="Backend services"),
        now=now,
    )
    repo.upsert_from_candidate(
        _make_candidate(
            "mock://c",
            title="Onsite Dev",
            summary="Onsite infra work",
            remote_type="onsite",
        ),
        now=now,
    )
    session.commit()
    return JobService(repo)


def test_list_jobs_filters_by_query(service: JobService) -> None:
    result = service.list_jobs(
        q="flutter", location=None, remote=None, source=None,
        posted_after=None, limit=10, offset=0,
    )
    assert len(result.items) == 1
    assert result.items[0].title == "Flutter Developer"


def test_list_jobs_filters_by_remote_true(service: JobService) -> None:
    result = service.list_jobs(
        q=None, location=None, remote=True, source=None,
        posted_after=None, limit=10, offset=0,
    )
    assert {item.remote_type for item in result.items} == {"remote"}


def test_list_jobs_returns_pagination_cursor(service: JobService) -> None:
    result = service.list_jobs(
        q=None, location=None, remote=None, source=None,
        posted_after=None, limit=1, offset=0,
    )
    assert len(result.items) == 1
    assert result.next_cursor is not None  # base64-encoded "1"

    next_page = service.list_jobs(
        q=None, location=None, remote=None, source=None,
        posted_after=None, limit=10, offset=1,
    )
    assert len(next_page.items) == 2


def test_get_by_id_raises_not_found(session: Session) -> None:
    service = JobService(JobRepository(session))
    with pytest.raises(NotFoundError) as exc_info:
        service.get_by_id("does-not-exist")
    assert exc_info.value.code == "job_not_found"
