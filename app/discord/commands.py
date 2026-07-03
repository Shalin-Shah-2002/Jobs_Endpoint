"""Slash command handlers for Discord — pure functions that build embeds.

Each handler takes a :class:`CommandContext` (parsed args + DI handles) and
returns an ``InteractionResponse`` dict ready to be serialized as JSON. The
interactions route in :mod:`app.discord.interactions` is responsible for
signature verification, PING handling, and HTTP wrapping.

This module is intentionally decoupled from py-cord's event loop so handlers
can be unit-tested with plain async test runners.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.errors import AppError
from app.schemas.dto import JobAlertInput
from app.services.clock import utc_now
from app.services.job_alert_service import JobAlertService

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from app.core.container import Container


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response builder helpers
# ---------------------------------------------------------------------------
@dataclass
class InteractionResponse:
    """Minimal Discord interaction response payload."""

    type: int  # 4 = channel_message, 5 = deferred_channel_message
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}


def _embed(title: str, description: str, *, color: int = 0x5865F2) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "color": color,
    }


def _embed_error(message: str) -> dict[str, Any]:
    return _embed("Error", message, color=0xED4245)


def _error_response(message: str) -> dict[str, Any]:
    return InteractionResponse(
        type=4,
        data={"embeds": [_embed_error(message)], "flags": 64},  # 64 = ephemeral
    ).to_dict()


# ---------------------------------------------------------------------------
# Command context (parsed slash-command invocation)
# ---------------------------------------------------------------------------
@dataclass
class CommandContext:
    """Parsed slash-command arguments + DI handles."""

    subcommand: str
    options: dict[str, Any]
    container: Container
    session_factory: sessionmaker

    def open_session(self):
        return self.session_factory()


# ---------------------------------------------------------------------------
# /alert create
# ---------------------------------------------------------------------------
async def alert_create(ctx: CommandContext) -> dict[str, Any]:
    opts = ctx.options
    sources = opts.get("sources")
    if isinstance(sources, str):
        sources = [s.strip() for s in sources.split(",") if s.strip()]

    try:
        payload = JobAlertInput(
            name=opts["name"],
            q=opts["q"],
            location=opts.get("location"),
            remote=opts.get("remote"),
            sources=sources,
            limit=opts.get("limit", 25),
            check_interval_minutes=opts.get("check_interval_minutes", 60),
            discord_webhook_url=opts.get("discord_webhook_url"),
            slack_webhook_url=opts.get("slack_webhook_url"),
            enabled=opts.get("enabled", True),
        )
    except Exception as exc:
        return _error_response(f"Invalid input: {exc}")

    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        alert = service.create_alert(payload, now=utc_now())
    except AppError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("alert_create failed")
        return _error_response(f"Internal error: {exc}")
    finally:
        session.close()

    embed = _embed(
        "Alert created",
        (
            f"**ID:** `{alert.id}`\n"
            f"**Name:** {alert.name}\n"
            f"**Query:** {alert.q}\n"
            f"**Location:** {alert.location or '—'}\n"
            f"**Remote:** {alert.remote}\n"
            f"**Sources:** {', '.join(alert.sources) or 'all'}\n"
            f"**Cadence:** every {alert.check_interval_minutes}m\n"
            f"**Discord webhook:** {'yes' if alert.discord_webhook_url else 'no'}\n"
            f"**Slack webhook:** {'yes' if alert.slack_webhook_url else 'no'}\n"
            f"**Enabled:** {alert.enabled}"
        ),
        color=0x57F287,
    )
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ---------------------------------------------------------------------------
# /alert list
# ---------------------------------------------------------------------------
async def alert_list(ctx: CommandContext) -> dict[str, Any]:
    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        alerts = service.list_alerts()
    finally:
        session.close()

    if not alerts:
        embed = _embed("Alerts", "_No alerts configured._", color=0x5865F2)
        return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()

    ephemeral = len(alerts) > 10
    lines = []
    for a in alerts[:10]:
        last_run = a.last_run_at.isoformat() if a.last_run_at else "never"
        lines.append(
            f"• `{a.id}` — **{a.name}** ({'on' if a.enabled else 'off'})"
            f" — last run: {last_run}, new jobs: {a.last_new_jobs_count}"
        )
    title = (
        f"Alerts ({len(alerts)} total)"
        if not ephemeral
        else f"Alerts (showing 10 of {len(alerts)})"
    )
    embed = _embed(title, "\n".join(lines), color=0x5865F2)
    flags = 64 if ephemeral else 0
    return InteractionResponse(type=4, data={"embeds": [embed], "flags": flags}).to_dict()


# ---------------------------------------------------------------------------
# /alert run
# ---------------------------------------------------------------------------
async def alert_run(ctx: CommandContext) -> dict[str, Any]:
    """Acknowledge the run command immediately (deferred response).

    Discord requires a response within 3s. Alert execution takes 5-30s.
    The interactions route fires the actual execution in a background
    task and uses a follow-up webhook to send the final result.

    Here we only validate that the alert exists and return the deferred ack.
    """
    alert_id = ctx.options["alert_id"]
    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        try:
            service.get_alert(alert_id)
        except AppError as exc:
            return _error_response(str(exc))
    finally:
        session.close()

    embed = _embed(
        "Running…",
        f"Executing alert `{alert_id}` in the background. Result will follow.",
        color=0xFEE75C,
    )
    return InteractionResponse(
        type=5,  # deferred_channel_message — acknowledges immediately
        data={"embeds": [embed]},
    ).to_dict()


async def execute_and_build_result(
    alert_id: str,
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Run the alert and return the result embed dict for the follow-up message.

    Designed to be called from ``asyncio.create_task`` so the original
    interaction response can be sent within Discord's 3-second window.
    """
    session = session_factory()
    try:
        service: JobAlertService = container.job_alert_service(session)
        try:
            service.execute_alert(alert_id, now=utc_now())
        except AppError as exc:
            return _error_response(str(exc))
        except Exception as exc:
            logger.exception("alert_run execution failed")
            return _error_response(f"Internal error: {exc}")
    finally:
        session.close()

    # Fetch the latest execution for the alert to report counts.
    from app.repositories.job_alert_repository import JobAlertRepository
    session = session_factory()
    try:
        repo = JobAlertRepository(session)
        rows = repo.list_executions(alert_id, limit=1, offset=0)
        latest = rows[0] if rows else None
    finally:
        session.close()

    if latest is None:
        return _error_response("Execution did not produce a record.")

    title = "Done" if latest.status == "completed" else f"Status: {latest.status}"
    color = 0x57F287 if latest.status == "completed" else 0xED4245
    desc = (
        f"**New jobs:** {latest.new_jobs_count}\n"
        f"**Total found:** {latest.total_jobs_found}\n"
        f"**Notified:** {latest.notified}\n"
        f"**Discord:** {latest.discord_status or '—'}\n"
        f"**Slack:** {latest.slack_status or '—'}\n"
    )
    if latest.error:
        desc += f"**Error:** {latest.error}"
    return {
        "embeds": [_embed(title, desc, color=color)],
    }


# ---------------------------------------------------------------------------
# /alert test
# ---------------------------------------------------------------------------
async def alert_test(ctx: CommandContext) -> dict[str, Any]:
    alert_id = ctx.options["alert_id"]
    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        try:
            result = service.test_notification(alert_id, now=utc_now())
        except AppError as exc:
            return _error_response(str(exc))
    finally:
        session.close()

    embed = _embed(
        "Test notification sent",
        (
            f"**Discord:** {result.discord_status or '—'}\n"
            f"**Slack:** {result.slack_status or '—'}"
        ),
        color=0x57F287,
    )
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
COMMAND_REGISTRY: dict[str, Any] = {
    "create": alert_create,
    "list": alert_list,
    "run": alert_run,
    "test": alert_test,
}


def parse_options(raw_options: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Flatten Discord option array into a dict by name."""
    if not raw_options:
        return {}
    return {opt["name"]: opt.get("value") for opt in raw_options}


def get_subcommand(options: list[dict[str, Any]] | None) -> tuple[str, list[dict[str, Any]] | None]:
    """Extract the first subcommand (e.g. 'create') and remaining options."""
    if not options:
        return "", None
    for opt in options:
        if opt.get("type") == 1:  # SUB_COMMAND
            return str(opt["name"]), opt.get("options") or []
    return "", options


async def dispatch(
    subcommand: str,
    options: dict[str, Any],
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Route a parsed /alert invocation to its handler."""
    handler = COMMAND_REGISTRY.get(subcommand)
    if handler is None:
        return _error_response(f"Unknown subcommand: {subcommand!r}")
    ctx = CommandContext(
        subcommand=subcommand,
        options=options,
        container=container,
        session_factory=session_factory,
    )
    return await handler(ctx)
