from datetime import datetime, timezone

import pytest

from app.schemas.dto import JobDTO
from app.services.notification_service import NotificationService


@pytest.fixture
def sample_jobs() -> list[JobDTO]:
    return [
        JobDTO(
            id="job-1",
            source="mock",
            title="Senior Python Engineer",
            company="Acme",
            location="Remote",
            remote_type="remote",
            salary="$150k",
            equity=None,
            posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_url="https://example.com/1",
            fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            summary="Build Python services.",
        ),
        JobDTO(
            id="job-2",
            source="wellfound",
            title="Full Stack Developer",
            company="Beta",
            location="NYC",
            remote_type="hybrid",
            salary=None,
            equity="0.1%",
            posted_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
            source_url="https://example.com/2",
            fetched_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
            summary=None,
        ),
    ]


def test_send_skips_when_no_jobs() -> None:
    service = NotificationService()
    result = service.send("Alert", [], discord_webhook_url="https://discord.com/x")
    assert result.discord_status == "skipped"
    assert result.slack_status == "skipped"


def test_send_skips_when_no_webhooks(sample_jobs: list[JobDTO]) -> None:
    service = NotificationService()
    result = service.send("Alert", sample_jobs)
    assert result.discord_status == "skipped"
    assert result.slack_status == "skipped"


def test_discord_payload_structure(sample_jobs: list[JobDTO]) -> None:
    service = NotificationService()
    payload = service._build_discord_payload("My Alert", sample_jobs)
    assert payload["content"].startswith("🔔 **My Alert**")
    assert len(payload["embeds"]) == 2
    embed = payload["embeds"][0]
    assert embed["title"] == "Senior Python Engineer"
    assert embed["url"] == "https://example.com/1"
    assert any(f["name"] == "Company" and f["value"] == "Acme" for f in embed["fields"])


def test_slack_payload_structure(sample_jobs: list[JobDTO]) -> None:
    service = NotificationService()
    payload = service._build_slack_payload("My Alert", sample_jobs)
    assert payload["blocks"][0]["type"] == "header"
    assert any(b["type"] == "section" and "Senior Python Engineer" in b["text"]["text"] for b in payload["blocks"])
