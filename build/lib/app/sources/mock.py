from datetime import UTC, datetime, timedelta

from app.sources.base import JobCandidate, SourceInfo, SourceSearchResult


class MockSource:
    name = "mock"
    enabled = True
    info = SourceInfo(
        name="mock",
        enabled=True,
        status="ready",
        reason="Local development source with deterministic sample jobs.",
    )

    def __init__(self) -> None:
        now = datetime.now(UTC)
        self._jobs = [
            JobCandidate(
                source=self.name,
                source_job_id="mock-python-backend-1",
                title="Python Backend Engineer",
                company="SignalWorks",
                location="Bengaluru, India",
                remote_type="remote",
                salary="INR 24L - 38L",
                equity="0.05% - 0.15%",
                posted_at=now - timedelta(days=1),
                source_url="mock://jobs/python-backend-engineer",
                summary="Build FastAPI services for a hiring intelligence platform.",
                raw={"team": "platform"},
            ),
            JobCandidate(
                source=self.name,
                source_job_id="mock-fullstack-2",
                title="Full Stack Developer",
                company="LaunchNest",
                location="Mumbai, India",
                remote_type="hybrid",
                salary="INR 18L - 30L",
                equity=None,
                posted_at=now - timedelta(days=3),
                source_url="mock://jobs/full-stack-developer",
                summary="Work across React, Python APIs, and job matching workflows.",
                raw={"team": "product"},
            ),
            JobCandidate(
                source=self.name,
                source_job_id="mock-data-3",
                title="Data Engineer",
                company="HiringCloud",
                location="Remote, India",
                remote_type="remote",
                salary="INR 28L - 44L",
                equity="0.02% - 0.08%",
                posted_at=now - timedelta(days=5),
                source_url="mock://jobs/data-engineer",
                summary="Create pipelines that normalize job and company datasets.",
                raw={"team": "data"},
            ),
            JobCandidate(
                source=self.name,
                source_job_id="mock-devops-4",
                title="DevOps Engineer",
                company="OpsForge",
                location="Pune, India",
                remote_type="onsite",
                salary="INR 20L - 32L",
                equity=None,
                posted_at=now - timedelta(days=7),
                source_url="mock://jobs/devops-engineer",
                summary="Own deployments, observability, and API reliability.",
                raw={"team": "infrastructure"},
            ),
        ]

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

