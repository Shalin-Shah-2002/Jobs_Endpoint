"""Unit tests for JobRepository — pure data access, no HTTP."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.repositories.job_repository import JobRepository
from app.sources.base import JobCandidate


def _candidate(**overrides) -> JobCandidate:
    base = dict(
        source="mock",
        source_job_id="m-1",
        title="Flutter Developer",
        company="OrbitLabs",
        location="Bengaluru, India",
        remote_type="remote",
        salary="INR 30L",
        equity=None,
        posted_at=datetime.now(UTC) - timedelta(days=1),
        source_url="mock://flutter-1",
        summary="Flutter mobile role",
        raw={"team": "mobile"},
    )
    base.update(overrides)
    return JobCandidate(**base)


def test_upsert_inserts_new_job(session: Session) -> None:
    repo = JobRepository(session)
    now = datetime.now(UTC)

    job = repo.upsert_from_candidate(_candidate(), now=now)

    assert job.id is not None
    assert job.title == "Flutter Developer"
    assert job.company == "OrbitLabs"
    assert job.source == "mock"
    assert job.fetched_at == now


def test_upsert_updates_existing_job_by_source_url(session: Session) -> None:
    repo = JobRepository(session)
    now = datetime.now(UTC)
    repo.upsert_from_candidate(_candidate(source_job_id="m-1", title="Junior"), now=now)
    session.commit()

    updated = repo.upsert_from_candidate(
        _candidate(source_job_id="m-1-updated", title="Senior"),
        now=now,
    )
    session.commit()

    all_jobs = repo.search(q=None, location=None, remote=None, source=None, posted_after=None)
    rows = repo.paginate(all_jobs, limit=10, offset=0)

    assert len(rows) == 1
    assert updated.title == "Senior"
    assert updated.source_job_id == "m-1-updated"


def test_search_filters_by_query_text(session: Session) -> None:
    repo = JobRepository(session)
    now = datetime.now(UTC)
    repo.upsert_from_candidate(
        _candidate(title="Flutter Developer", source_url="mock://a", summary="Flutter mobile"),
        now=now,
    )
    repo.upsert_from_candidate(
        _candidate(title="Python Engineer", company="Other", source_url="mock://b", summary="Backend work"),
        now=now,
    )
    session.commit()

    stmt = repo.search(q="flutter", location=None, remote=None, source=None, posted_after=None)
    rows = repo.paginate(stmt, limit=10, offset=0)

    assert len(rows) == 1
    assert rows[0].title == "Flutter Developer"


def test_search_filters_by_remote_true(session: Session) -> None:
    repo = JobRepository(session)
    now = datetime.now(UTC)
    repo.upsert_from_candidate(_candidate(remote_type="remote", source_url="mock://a"), now=now)
    repo.upsert_from_candidate(
        _candidate(remote_type="onsite", source_url="mock://b", title="Onsite"),
        now=now,
    )
    session.commit()

    stmt = repo.search(q=None, location=None, remote=True, source=None, posted_after=None)
    rows = repo.paginate(stmt, limit=10, offset=0)

    assert len(rows) == 1
    assert rows[0].remote_type == "remote"


def test_paginate_returns_next_offset(session: Session) -> None:
    repo = JobRepository(session)
    now = datetime.now(UTC)
    for i in range(3):
        repo.upsert_from_candidate(_candidate(source_url=f"mock://{i}"), now=now)
    session.commit()

    stmt = repo.search(q=None, location=None, remote=None, source=None, posted_after=None)
    rows = repo.paginate(stmt, limit=2, offset=0)
    assert len(rows) == 3  # limit+1 to detect more
    page, next_offset = rows[:2], 2
    assert next_offset == 2
    assert len(page) == 2
