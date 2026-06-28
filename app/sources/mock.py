from datetime import UTC, datetime, timedelta

from app.sources.base import JobCandidate, SourceInfo, SourceSearchResult


def _default_sample_jobs() -> list[JobCandidate]:
    now = datetime.now(UTC)
    return [
        JobCandidate(
            source="mock",
            source_job_id="mock-py-1",
            title="Python Backend Engineer",
            company="TestLabs",
            location="Bengaluru, India",
            remote_type="remote",
            salary="INR 24L - 38L",
            equity=None,
            posted_at=now - timedelta(days=1),
            source_url="mock://jobs/py-backend-1",
            summary="Build FastAPI services.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-data-2",
            title="Data Engineer",
            company="DataCloud",
            location="Remote, India",
            remote_type="remote",
            salary="INR 28L - 44L",
            equity=None,
            posted_at=now - timedelta(days=2),
            source_url="mock://jobs/data-engineer-2",
            summary="Build data pipelines.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-full-3",
            title="Full Stack Developer",
            company="WebCo",
            location="Mumbai, India",
            remote_type="hybrid",
            salary="INR 18L - 30L",
            equity=None,
            posted_at=now - timedelta(days=3),
            source_url="mock://jobs/full-stack-3",
            summary="React and Python.",
        ),
    ]


class MockSource:
    name = "mock"
    enabled = True
    info = SourceInfo(
        name="mock",
        enabled=True,
        status="ready",
        reason="Development source with optional sample jobs for testing.",
    )

    def __init__(
        self, jobs: list[JobCandidate] | None = None, *, use_samples: bool = False
    ) -> None:
        self._jobs = jobs or (_default_sample_jobs() if use_samples else [])

    def search(
        self,
        *,
        q: str,
        location: str | None,
        remote: bool | None,
        limit: int,
    ) -> SourceSearchResult:
        query = q.lower()
        location_query = location.lower() if location else None

        matches: list[JobCandidate] = []
        for job in self._jobs:
            haystack = " ".join(
                value
                for value in [job.title, job.company, job.location or "", job.summary or ""]
                if value
            ).lower()
            if query not in haystack:
                continue
            if location_query and location_query not in (job.location or "").lower():
                continue
            if remote is True and job.remote_type != "remote":
                continue
            if remote is False and job.remote_type == "remote":
                continue
            matches.append(job)

        return SourceSearchResult(jobs=matches[:limit])
