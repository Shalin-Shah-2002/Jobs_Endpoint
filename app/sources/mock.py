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
            summary="Build FastAPI services. Python, PostgreSQL, Redis.",
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
            summary="Build data pipelines with Spark and Airflow.",
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
            summary="React and Python. Full stack web development.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-ai-4",
            title="AI/ML Engineer",
            company="NovaAI",
            location="Bengaluru, India",
            remote_type="remote",
            salary="INR 35L - 60L",
            equity="0.05% - 0.15%",
            posted_at=now - timedelta(hours=6),
            source_url="mock://jobs/ai-ml-4",
            summary="Build and deploy LLM-powered applications. RAG, fine-tuning, prompt engineering.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-ai-5",
            title="AI Developer",
            company="SmartSys",
            location="Remote, India",
            remote_type="remote",
            salary="INR 20L - 35L",
            equity=None,
            posted_at=now - timedelta(hours=12),
            source_url="mock://jobs/ai-dev-5",
            summary="Develop AI agents and automation tools using Python and LangChain.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-ai-6",
            title="Senior AI Engineer",
            company="DeepThink",
            location="Mumbai, India",
            remote_type="remote",
            salary="INR 40L - 70L",
            equity="0.1% - 0.3%",
            posted_at=now - timedelta(days=1),
            source_url="mock://jobs/senior-ai-6",
            summary="Lead AI research and development. NLP, computer vision, and generative AI.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-frontend-7",
            title="Frontend Developer",
            company="UIWorks",
            location="Pune, India",
            remote_type="remote",
            salary="INR 14L - 24L",
            equity=None,
            posted_at=now - timedelta(days=2),
            source_url="mock://jobs/frontend-7",
            summary="React, TypeScript, Tailwind CSS. Build beautiful UIs.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-devops-8",
            title="DevOps Engineer",
            company="CloudOps",
            location="Remote, India",
            remote_type="remote",
            salary="INR 22L - 38L",
            equity=None,
            posted_at=now - timedelta(days=4),
            source_url="mock://jobs/devops-8",
            summary="Kubernetes, Terraform, CI/CD pipelines. AWS infrastructure.",
        ),
        JobCandidate(
            source="mock",
            source_job_id="mock-ds-9",
            title="Data Scientist",
            company="Quantico",
            location="Bengaluru, India",
            remote_type="hybrid",
            salary="INR 25L - 42L",
            equity="0.02% - 0.08%",
            posted_at=now - timedelta(days=5),
            source_url="mock://jobs/data-scientist-9",
            summary="ML modeling, experimentation, A/B testing. Python, R, TensorFlow.",
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
