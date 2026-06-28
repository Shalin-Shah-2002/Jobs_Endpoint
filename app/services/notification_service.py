"""Send job alert notifications to Discord and Slack incoming webhooks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.schemas.dto import JobDTO


_DISCORD_EMBED_LIMIT = 10
_SLACK_BLOCK_LIMIT = 10


@dataclass(frozen=True)
class NotificationResult:
    discord_status: str | None = None
    slack_status: str | None = None
    discord_error: str | None = None
    slack_error: str | None = None


class NotificationService:
    """Synchronous notification sender. Intended to be used from background threads."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds

    def send(
        self,
        alert_name: str,
        jobs: list[JobDTO],
        *,
        discord_webhook_url: str | None = None,
        slack_webhook_url: str | None = None,
    ) -> NotificationResult:
        if not jobs:
            return NotificationResult(discord_status="skipped", slack_status="skipped")

        discord_status: str | None = None
        discord_error: str | None = None
        slack_status: str | None = None
        slack_error: str | None = None

        if discord_webhook_url:
            discord_status, discord_error = self._send_discord(
                discord_webhook_url, alert_name, jobs
            )
        else:
            discord_status = "skipped"

        if slack_webhook_url:
            slack_status, slack_error = self._send_slack(
                slack_webhook_url, alert_name, jobs
            )
        else:
            slack_status = "skipped"

        return NotificationResult(
            discord_status=discord_status,
            slack_status=slack_status,
            discord_error=discord_error,
            slack_error=slack_error,
        )

    def _send_discord(
        self, webhook_url: str, alert_name: str, jobs: list[JobDTO]
    ) -> tuple[str, str | None]:
        payload = self._build_discord_payload(alert_name, jobs)
        try:
            response = httpx.post(webhook_url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            return "ok", None
        except httpx.HTTPStatusError as exc:
            return "failed", f"HTTP {exc.response.status_code}"
        except httpx.RequestError as exc:
            return "failed", str(exc)

    def _send_slack(
        self, webhook_url: str, alert_name: str, jobs: list[JobDTO]
    ) -> tuple[str, str | None]:
        payload = self._build_slack_payload(alert_name, jobs)
        try:
            response = httpx.post(webhook_url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            return "ok", None
        except httpx.HTTPStatusError as exc:
            return "failed", f"HTTP {exc.response.status_code}"
        except httpx.RequestError as exc:
            return "failed", str(exc)

    @staticmethod
    def _build_discord_payload(alert_name: str, jobs: list[JobDTO]) -> dict:
        embeds: list[dict] = []
        remaining = max(0, len(jobs) - _DISCORD_EMBED_LIMIT)

        for job in jobs[:_DISCORD_EMBED_LIMIT]:
            fields = [
                {"name": "Company", "value": job.company or "N/A", "inline": True},
                {"name": "Source", "value": job.source, "inline": True},
            ]
            if job.location:
                fields.append({"name": "Location", "value": job.location, "inline": True})
            if job.remote_type is not None:
                fields.append(
                    {"name": "Remote", "value": job.remote_type, "inline": True}
                )
            if job.salary:
                fields.append({"name": "Salary", "value": job.salary, "inline": True})

            embed = {
                "title": job.title,
                "url": job.source_url,
                "description": (job.summary or "")[:300],
                "fields": fields,
                "timestamp": _iso_or_now(job.posted_at),
            }
            embeds.append(embed)

        content = f"🔔 **{alert_name}** — {len(jobs)} new job(s) found!"
        if remaining:
            content += f" ({remaining} more not shown)"

        return {
            "content": content,
            "embeds": embeds,
        }

    @staticmethod
    def _build_slack_payload(alert_name: str, jobs: list[JobDTO]) -> dict:
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔔 {alert_name} — {len(jobs)} new job(s)!",
                    "emoji": True,
                },
            },
            {"type": "divider"},
        ]

        remaining = max(0, len(jobs) - _SLACK_BLOCK_LIMIT)

        for job in jobs[:_SLACK_BLOCK_LIMIT]:
            details = []
            if job.company:
                details.append(f"*{job.company}*")
            if job.location:
                details.append(f"📍 {job.location}")
            if job.remote_type is not None:
                details.append(f"🏠 {job.remote_type}")
            if job.salary:
                details.append(f"💰 {job.salary}")

            text = f"*<{job.source_url}|{job.title}*>\n" + " | ".join(details)
            if job.summary:
                text += f"\n{job.summary[:200]}"

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},
                }
            )

        if remaining:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"_...and {remaining} more job(s)._",
                    },
                }
            )

        return {"blocks": blocks}


def _iso_or_now(dt: datetime | None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
