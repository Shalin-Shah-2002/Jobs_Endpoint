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
from app.schemas.dto import JobAlertInput, JobAlertPatch
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


# ===========================================================================
# /jobs commands
# ===========================================================================

# ---------------------------------------------------------------------------
# /jobs search
# ---------------------------------------------------------------------------
async def jobs_search(ctx: CommandContext) -> dict[str, Any]:
    """Search cached jobs and return results as an embed."""
    opts = ctx.options
    q = opts.get("q")
    if not q:
        return _error_response("Search query is required.")

    session = ctx.open_session()
    try:
        from app.services.job_service import JobService

        service: JobService = ctx.container.job_service(session)
        result = service.list_jobs(
            q=q,
            location=opts.get("location"),
            remote=opts.get("remote"),
            source=opts.get("source"),
            posted_after=None,
            limit=min(opts.get("limit", 25), 25),
            offset=0,
        )
    except Exception as exc:
        logger.exception("jobs_search failed")
        return _error_response(f"Search failed: {exc}")
    finally:
        session.close()

    if not result.items:
        embed = _embed("Job Search", "No jobs match your search.", color=0x5865F2)
        return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()

    # Show up to 10 results in the embed description
    MAX_DISPLAY = 10
    lines: list[str] = []
    for job in result.items[:MAX_DISPLAY]:
        posted = f"<t:{int(job.posted_at.timestamp())}:R>" if job.posted_at else ""
        loc = f" 📍{job.location}" if job.location else ""
        remote_tag = f" 🏠{job.remote_type}" if job.remote_type else ""
        salary = f" 💰{job.salary}" if job.salary else ""
        lines.append(
            f"**[{job.title}]({job.source_url})** — {job.company}"
            f"{loc}{remote_tag}{salary} {posted}".strip()
        )

    description = "\n".join(lines)
    total_count = result.next_cursor is not None  # has more pages
    shown = min(len(result.items), MAX_DISPLAY)
    if total_count:
        footer = f"\n\n_Showing {shown} results. Use more specific filters for fewer results._"
        if len(description) + len(footer) <= 4000:
            description += footer

    embed = _embed(
        f"Job Search — {q}",
        description[:4000],
        color=0x5865F2,
    )
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ---------------------------------------------------------------------------
# /jobs get
# ---------------------------------------------------------------------------
async def jobs_get(ctx: CommandContext) -> dict[str, Any]:
    """Get full details on a single job."""
    job_id = ctx.options.get("job_id", "")
    if not job_id:
        return _error_response("Job ID is required.")

    session = ctx.open_session()
    try:
        from app.services.job_service import JobService

        service: JobService = ctx.container.job_service(session)
        job = service.get_by_id(job_id)
    except AppError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("jobs_get failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    fields: list[dict[str, Any]] = [
        {"name": "Company", "value": job.company, "inline": True},
        {"name": "Source", "value": job.source, "inline": True},
        {"name": "Location", "value": job.location or "—", "inline": True},
        {"name": "Remote", "value": job.remote_type or "—", "inline": True},
    ]
    if job.salary:
        fields.append({"name": "Salary", "value": job.salary, "inline": True})
    if job.equity:
        fields.append({"name": "Equity", "value": job.equity, "inline": True})

    description = (job.summary or "")[:300]
    if job.summary and len(job.summary) > 300:
        description += "…"

    embed: dict[str, Any] = {
        "title": job.title,
        "url": job.source_url,
        "description": description or None,
        "fields": fields,
        "color": 0x5865F2,
    }
    if job.posted_at:
        embed["timestamp"] = job.posted_at.isoformat()

    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ===========================================================================
# /search commands
# ===========================================================================

# ---------------------------------------------------------------------------
# /search create  (deferred — type 5)
# ---------------------------------------------------------------------------
async def search_create(ctx: CommandContext) -> dict[str, Any]:
    """Acknowledge the search command immediately (deferred response).

    Discord requires a response within 3s. The actual search takes 5-30s.
    The interactions route fires the actual execution in a background
    task and uses a follow-up webhook to send the final result.
    """
    opts = ctx.options
    q = opts.get("q")
    if not q:
        return _error_response("Search query is required.")

    sources_raw = opts.get("sources")
    if isinstance(sources_raw, str):
        sources_raw = [s.strip() for s in sources_raw.split(",") if s.strip()]

    embed = _embed(
        "Searching…",
        f"Query: **{q}**\n"
        f"Location: {opts.get('location', '—')}\n"
        f"Remote: {opts.get('remote', 'any')}\n"
        f"Sources: {', '.join(sources_raw) if sources_raw else 'all'}\n\n"
        "Searching in the background. Results will follow shortly.",
        color=0xFEE75C,
    )
    return InteractionResponse(
        type=5,  # deferred_channel_message
        data={"embeds": [embed]},
    ).to_dict()


async def execute_search_and_build_result(
    options: dict[str, Any],
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Run the search and return the result embed dict for the follow-up message."""
    from app.core.config import get_settings
    from app.services.search_executor import SearchExecutor
    from app.services.search_run_service import SearchRunService
    from app.services.source_service import SourceService
    from app.schemas.dto import SearchRunInput

    q = options.get("q", "")
    location = options.get("location")
    remote = options.get("remote")
    sources_raw = options.get("sources")
    if isinstance(sources_raw, str):
        sources_raw = [s.strip() for s in sources_raw.split(",") if s.strip()]
    limit = min(options.get("limit", 25), 100)

    if not q:
        return _error_response("Search query is required.")

    settings = get_settings()

    # Phase 1: create the search run (own session)
    session = session_factory()
    try:
        from app.repositories.job_repository import JobRepository
        from app.repositories.search_run_repository import SearchRunRepository
        from app.repositories.source_status_repository import SourceStatusRepository

        runs_repo = SearchRunRepository(session)
        jobs_repo = JobRepository(session)
        statuses_repo = SourceStatusRepository(session)

        source_service = SourceService(
            statuses_repo,
            registry_factory=container.registry_factory,
        )
        available = source_service.known_source_names(settings)
        selected = sources_raw or available

        # Validate sources
        unknown = sorted(set(selected) - set(available))
        if unknown:
            return _error_response(f"Unknown source(s): {', '.join(unknown)}")

        payload = SearchRunInput(
            q=q,
            location=location,
            remote=remote,
            sources=selected,
            limit=limit,
        )

        run_service = SearchRunService(
            runs=runs_repo,
            jobs=jobs_repo,
            statuses=statuses_repo,
            registry_factory=container.registry_factory,
            session_factory=session_factory,
        )
        run = run_service.create(payload, available)
        run_id = run.id
    except (AppError, ValueError) as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("search_create: failed to create run")
        return _error_response(f"Failed to create search run: {exc}")
    finally:
        session.close()

    # Phase 2: execute via SearchExecutor (opens its own session)
    try:
        executor = SearchExecutor(
            session_factory=session_factory,
            registry_factory=container.registry_factory,
            settings_factory=get_settings,
        )
        executor.execute(run_id, payload, selected)
    except Exception as exc:
        logger.exception(f"search_create: execution failed for run {run_id}")
        return _error_response(f"Search execution failed: {exc}")

    # Phase 3: fetch results in a fresh session
    session = session_factory()
    try:
        from app.repositories.job_repository import JobRepository
        from app.repositories.search_run_repository import SearchRunRepository

        runs_repo2 = SearchRunRepository(session)
        jobs_repo2 = JobRepository(session)

        completed_run = runs_repo2.get(run_id)
        if completed_run is None:
            return _error_response("Search run not found after execution.")

        jobs_result = jobs_repo2.list_for_run(run_id, limit=100, offset=0)
        items = list(jobs_result) if jobs_result else []

        # Build result embed
        title = f"Search Complete — {q}"
        desc_lines: list[str] = [
            f"**Run ID:** `{run_id[:8]}…`",
            f"**Status:** {completed_run.status}",
            f"**Total jobs:** {completed_run.total_jobs}",
        ]
        if completed_run.error_count:
            desc_lines.append(f"**Errors:** {completed_run.error_count}")

        if items:
            desc_lines.append("")
            for j in items[:5]:
                posted = f"<t:{int(j.posted_at.timestamp())}:R>" if j.posted_at else ""
                desc_lines.append(f"• **{j.title}** — {j.company} {posted}")

            remaining = max(0, len(items) - 5)
            if remaining:
                desc_lines.append(f"\n_...and {remaining} more job(s)._")
        else:
            desc_lines.append("\n_No jobs found for this search._")

        color = 0x57F287 if completed_run.status == "completed" else 0xED4245
        embed = _embed(title, "\n".join(desc_lines), color=color)
        return {"embeds": [embed]}
    except Exception as exc:
        logger.exception(f"search_create: failed to fetch results for run {run_id}")
        return _error_response(f"Failed to fetch results: {exc}")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# /search status
# ---------------------------------------------------------------------------
async def search_status(ctx: CommandContext) -> dict[str, Any]:
    """Check the status of a search run."""
    run_id = ctx.options.get("run_id", "")
    if not run_id:
        return _error_response("Run ID is required.")

    session = ctx.open_session()
    try:
        from app.services.search_run_service import SearchRunService

        service: SearchRunService = ctx.container.search_run_service(session)
        run = service.get(run_id)
    except AppError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("search_status failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    emoji = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}

    desc = (
        f"**Query:** {run.q}\n"
        f"**Location:** {run.location or '—'}\n"
        f"**Remote:** {run.remote}\n"
        f"**Status:** {emoji.get(run.status, '❓')} {run.status}\n"
        f"**Total jobs:** {run.total_jobs}\n"
        f"**Errors:** {run.error_count}\n"
        f"**Requested:** <t:{int(run.requested_at.timestamp())}:R>"
    )
    if run.started_at:
        desc += f"\n**Started:** <t:{int(run.started_at.timestamp())}:R>"
    if run.completed_at:
        desc += f"\n**Completed:** <t:{int(run.completed_at.timestamp())}:R>"

    color = (
        0x57F287
        if run.status == "completed"
        else (0xED4245 if run.status == "failed" else 0xFEE75C)
    )
    embed = _embed(f"Search Run `{run_id[:8]}…`", desc, color=color)
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ===========================================================================
# /sources command
# ===========================================================================

async def sources_list(ctx: CommandContext) -> dict[str, Any]:
    """List available job sources with their status."""
    session = ctx.open_session()
    try:
        from app.core.config import get_settings
        from app.services.source_service import SourceService

        service: SourceService = ctx.container.source_service(session)
        settings = get_settings()
        sources = service.list_sources(settings)
    except Exception as exc:
        logger.exception("sources_list failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    if not sources:
        embed = _embed("Sources", "No sources configured.", color=0x5865F2)
        return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()

    lines: list[str] = []
    for s in sources:
        icon = "✅" if s.status == "ok" else ("⚠️" if s.status == "error" else "❌")
        enabled = "enabled" if s.enabled else "disabled"
        status_line = f"{icon} **{s.name}** ({enabled}, {s.status})"
        if s.last_checked_at:
            ts = int(s.last_checked_at.timestamp())
            status_line += f" — last checked <t:{ts}:R>"
        if s.last_error_message:
            status_line += f"\n   └ Error: {s.last_error_message[:200]}"
        lines.append(status_line)

    embed = _embed("Job Sources", "\n".join(lines), color=0x5865F2)
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ===========================================================================
# /alert command additions
# ===========================================================================

# ---------------------------------------------------------------------------
# /alert info
# ---------------------------------------------------------------------------
async def alert_info(ctx: CommandContext) -> dict[str, Any]:
    """Show full details for a single alert."""
    alert_id = ctx.options.get("alert_id", "")
    if not alert_id:
        return _error_response("Alert ID is required.")

    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        alert = service.get_alert(alert_id)
    except AppError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("alert_info failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    desc = (
        f"**Name:** {alert.name}\n"
        f"**Query:** {alert.q}\n"
        f"**Location:** {alert.location or '—'}\n"
        f"**Remote:** {alert.remote}\n"
        f"**Sources:** {', '.join(alert.sources) or 'all'}\n"
        f"**Limit:** {alert.limit}\n"
        f"**Interval:** every {alert.check_interval_minutes}m\n"
        f"**Enabled:** {'✅ yes' if alert.enabled else '❌ no'}\n"
        f"**Discord webhook:** {'yes' if alert.discord_webhook_url else 'no'}\n"
        f"**Slack webhook:** {'yes' if alert.slack_webhook_url else 'no'}\n"
    )
    if alert.last_run_at:
        desc += f"**Last run:** <t:{int(alert.last_run_at.timestamp())}:R>\n"
    desc += f"**Last new jobs:** {alert.last_new_jobs_count}\n"
    if alert.last_error:
        desc += f"**Last error:** {alert.last_error[:200]}"

    embed = _embed(f"Alert: {alert.name}", desc, color=0x5865F2)
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ---------------------------------------------------------------------------
# /alert delete
# ---------------------------------------------------------------------------
async def alert_delete(ctx: CommandContext) -> dict[str, Any]:
    """Delete an alert."""
    alert_id = ctx.options.get("alert_id", "")
    if not alert_id:
        return _error_response("Alert ID is required.")

    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        alert = service.get_alert(alert_id)
        name = alert.name
        service.delete_alert(alert_id)
    except AppError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("alert_delete failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    embed = _embed(
        "Alert Deleted",
        f"Alert **{name}** (`{alert_id[:8]}…`) has been deleted.",
        color=0x57F287,
    )
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ---------------------------------------------------------------------------
# /alert toggle
# ---------------------------------------------------------------------------
async def alert_toggle(ctx: CommandContext) -> dict[str, Any]:
    """Toggle an alert between enabled and disabled."""
    alert_id = ctx.options.get("alert_id", "")
    if not alert_id:
        return _error_response("Alert ID is required.")

    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        alert = service.get_alert(alert_id)
        new_enabled = not alert.enabled
        patch = JobAlertPatch(enabled=new_enabled)
        updated = service.update_alert(alert_id, patch, now=utc_now())
    except AppError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("alert_toggle failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    state = "enabled" if updated.enabled else "disabled"
    embed = _embed(
        "Alert Updated",
        f"Alert **{updated.name}** (`{alert_id[:8]}…`) is now **{state}**.",
        color=0x57F287,
    )
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ---------------------------------------------------------------------------
# /alert executions
# ---------------------------------------------------------------------------
async def alert_executions(ctx: CommandContext) -> dict[str, Any]:
    """View execution history for an alert."""
    alert_id = ctx.options.get("alert_id", "")
    exec_limit = min(ctx.options.get("limit", 10), 25)

    if not alert_id:
        return _error_response("Alert ID is required.")

    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        alert = service.get_alert(alert_id)
        executions = service.list_executions(alert_id, limit=exec_limit, cursor="")
    except AppError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("alert_executions failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    if not executions.items:
        embed = _embed(
            f"Executions — {alert.name}",
            "_No executions recorded yet._",
            color=0x5865F2,
        )
        return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()

    lines: list[str] = []
    for e in executions.items:
        icon = "✅" if e.status == "completed" else "❌"
        started = f"<t:{int(e.started_at.timestamp())}:R>" if e.started_at else "—"
        lines.append(
            f"{icon} `{e.id[:8]}…` — {e.status} — {started}"
            f" — {e.new_jobs_count} new, {e.total_jobs_found} total"
            f" — notified: {'✅' if e.notified else '—'}"
        )
        if e.error:
            lines.append(f"   └ Error: {e.error[:200]}")

    embed = _embed(
        f"Executions — {alert.name}",
        "\n".join(lines),
        color=0x5865F2,
    )
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ---------------------------------------------------------------------------
# /alert edit
# ---------------------------------------------------------------------------
async def alert_edit(ctx: CommandContext) -> dict[str, Any]:
    """Edit properties of an existing alert."""
    opts = ctx.options
    alert_id = opts.get("alert_id", "")
    if not alert_id:
        return _error_response("Alert ID is required.")

    sources_raw = opts.get("sources")
    if isinstance(sources_raw, str):
        sources_raw = [s.strip() for s in sources_raw.split(",") if s.strip()]

    # Build the patch from what was provided
    patch_kwargs: dict[str, Any] = {}
    for field in ("name", "q", "location", "discord_webhook_url", "slack_webhook_url"):
        if field in opts and opts[field] is not None:
            patch_kwargs[field] = opts[field]
    for field in ("remote", "enabled"):
        if field in opts:
            patch_kwargs[field] = opts[field]
    for field in ("limit", "check_interval_minutes"):
        if field in opts and opts[field] is not None:
            patch_kwargs[field] = opts[field]
    if sources_raw:
        patch_kwargs["sources"] = sources_raw

    if not patch_kwargs:
        return _error_response("At least one field to update must be provided.")

    session = ctx.open_session()
    try:
        service: JobAlertService = ctx.container.job_alert_service(session)
        patch = JobAlertPatch(**patch_kwargs)
        updated = service.update_alert(alert_id, patch, now=utc_now())
    except (AppError, ValueError) as exc:
        return _error_response(str(exc))
    except Exception as exc:
        logger.exception("alert_edit failed")
        return _error_response(f"Error: {exc}")
    finally:
        session.close()

    embed = _embed(
        "Alert Updated",
        f"Alert **{updated.name}** (`{alert_id[:8]}…`) has been updated.\n\n"
        f"**Query:** {updated.q}\n"
        f"**Location:** {updated.location or '—'}\n"
        f"**Remote:** {updated.remote}\n"
        f"**Sources:** {', '.join(updated.sources) or 'all'}\n"
        f"**Interval:** every {updated.check_interval_minutes}m\n"
        f"**Enabled:** {'✅ yes' if updated.enabled else '❌ no'}\n"
        f"**Limit:** {updated.limit}",
        color=0x57F287,
    )
    return InteractionResponse(type=4, data={"embeds": [embed]}).to_dict()


# ===========================================================================
# Command registries
# ===========================================================================

ALERT_COMMAND_REGISTRY: dict[str, Any] = {
    "create": alert_create,
    "list": alert_list,
    "run": alert_run,
    "test": alert_test,
    "info": alert_info,
    "delete": alert_delete,
    "toggle": alert_toggle,
    "executions": alert_executions,
    "edit": alert_edit,
}

JOBS_COMMAND_REGISTRY: dict[str, Any] = {
    "search": jobs_search,
    "get": jobs_get,
}

SEARCH_COMMAND_REGISTRY: dict[str, Any] = {
    "create": search_create,
    "status": search_status,
}

SOURCES_COMMAND_REGISTRY: dict[str, Any] = {
    "list": sources_list,
}


# ===========================================================================
# Sub-dispatchers
# ===========================================================================

async def dispatch_alert(
    subcommand: str,
    options: dict[str, Any],
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Route a parsed /alert invocation to its handler."""
    handler = ALERT_COMMAND_REGISTRY.get(subcommand)
    if handler is None:
        return _error_response(f"Unknown alert subcommand: {subcommand!r}")
    ctx = CommandContext(
        subcommand=subcommand,
        options=options,
        container=container,
        session_factory=session_factory,
    )
    return await handler(ctx)


async def dispatch_jobs(
    subcommand: str,
    options: dict[str, Any],
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Route a parsed /jobs invocation to its handler."""
    handler = JOBS_COMMAND_REGISTRY.get(subcommand)
    if handler is None:
        return _error_response(f"Unknown jobs subcommand: {subcommand!r}")
    ctx = CommandContext(
        subcommand=subcommand,
        options=options,
        container=container,
        session_factory=session_factory,
    )
    return await handler(ctx)


async def dispatch_search(
    subcommand: str,
    options: dict[str, Any],
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Route a parsed /search invocation to its handler."""
    handler = SEARCH_COMMAND_REGISTRY.get(subcommand)
    if handler is None:
        return _error_response(f"Unknown search subcommand: {subcommand!r}")
    ctx = CommandContext(
        subcommand=subcommand,
        options=options,
        container=container,
        session_factory=session_factory,
    )
    return await handler(ctx)


async def dispatch_sources(
    subcommand: str,
    options: dict[str, Any],
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Route a parsed /sources invocation to its handler."""
    handler = SOURCES_COMMAND_REGISTRY.get(subcommand)
    if handler is None:
        return _error_response(f"Unknown sources subcommand: {subcommand!r}")
    ctx = CommandContext(
        subcommand=subcommand,
        options=options,
        container=container,
        session_factory=session_factory,
    )
    return await handler(ctx)


TOP_LEVEL_DISPATCH: dict[str, Any] = {
    "alert": dispatch_alert,
    "jobs": dispatch_jobs,
    "search": dispatch_search,
    "sources": dispatch_sources,
}


async def dispatch(
    command: str,
    subcommand: str,
    options: dict[str, Any],
    container: Container,
    session_factory: sessionmaker,
) -> dict[str, Any]:
    """Route to the correct command group dispatcher.

    *command* is the top-level slash command name (e.g. ``"alert"``,
    ``"jobs"``, ``"search"``, ``"sources"``). *subcommand* is the
    subcommand within that group (e.g. ``"create"``, ``"search"``).
    """
    dispatcher_fn = TOP_LEVEL_DISPATCH.get(command)
    if dispatcher_fn is None:
        return _error_response(f"Unknown command: {command!r}")
    return await dispatcher_fn(subcommand, options, container, session_factory)


# ===========================================================================
# Autocomplete — suggest alert IDs as the user types
# ===========================================================================
async def autocomplete_alert_id(
    focused_value: str,
    container: Container,
    session_factory: sessionmaker,
    max_choices: int = 25,
) -> list[dict[str, Any]]:
    """Return up to 25 alert choices matching the user's typed prefix."""
    session = session_factory()
    try:
        from app.repositories.job_alert_repository import JobAlertRepository

        repo = JobAlertRepository(session)
        all_alerts = repo.list_all(enabled_only=False)
    finally:
        session.close()

    query = focused_value.lower()
    matches = [
        a for a in all_alerts if query in a.id.lower() or query in a.name.lower()
    ]
    matches.sort(key=lambda a: (0 if a.id.lower().startswith(query) else 1, a.name))

    choices: list[dict[str, Any]] = []
    for a in matches[:max_choices]:
        label = (
            f"{a.name} ({a.id[:8]}…)" if len(a.id) > 8 else f"{a.name} ({a.id})"
        )
        choices.append({"name": label[:100], "value": a.id})
    return choices


# ===========================================================================
# Autocomplete — suggest previously-used webhook URLs as the user types
# ===========================================================================
async def autocomplete_webhook_url(
    focused_value: str,
    container: Container,
    session_factory: sessionmaker,
    field: str = "discord_webhook_url",
    max_choices: int = 25,
) -> list[dict[str, Any]]:
    """Return up to 25 webhook URL choices matching the user's typed prefix.

    *field* must be ``"discord_webhook_url"`` or ``"slack_webhook_url"``.

    URLs longer than 100 characters are excluded because Discord caps
    autocomplete choice value/name at 100 chars.
    """
    session = session_factory()
    try:
        from app.repositories.job_alert_repository import JobAlertRepository

        repo = JobAlertRepository(session)
        urls = repo.list_distinct_webhook_urls(field)
    finally:
        session.close()

    query = focused_value.lower()
    matches = [u for u in urls if query in u.lower()]
    matches.sort(key=lambda u: (0 if u.lower().startswith(query) else 1, u))

    choices: list[dict[str, Any]] = []
    for u in matches:
        if len(u) > 100:
            continue  # Discord rejects values > 100 chars
        choices.append({"name": u, "value": u})
        if len(choices) >= max_choices:
            break
    return choices


# ===========================================================================
# Autocomplete — suggest job IDs as the user types
# ===========================================================================
async def autocomplete_job_id(
    focused_value: str,
    container: Container,
    session_factory: sessionmaker,
    max_choices: int = 25,
) -> list[dict[str, Any]]:
    """Return up to 25 job IDs matching the user's typed prefix."""
    session = session_factory()
    try:
        from app.models.job import Job
        from sqlalchemy import select

        stmt = select(Job).order_by(Job.fetched_at.desc()).limit(25)
        recent = list(session.execute(stmt).scalars().all())
    finally:
        session.close()

    query = focused_value.lower()
    matches = [
        j for j in recent if query in j.id.lower() or query in j.title.lower()
    ]
    matches.sort(
        key=lambda j: (0 if j.id.lower().startswith(query) else 1, j.title)
    )

    choices: list[dict[str, Any]] = []
    for j in matches[:max_choices]:
        label = (
            f"{j.title[:80]} ({j.id[:8]}…)"
            if len(j.id) > 8
            else f"{j.title[:80]} ({j.id})"
        )
        choices.append({"name": label[:100], "value": j.id})
    return choices


# ===========================================================================
# Autocomplete — suggest search run IDs as the user types
# ===========================================================================
async def autocomplete_run_id(
    focused_value: str,
    container: Container,
    session_factory: sessionmaker,
    max_choices: int = 25,
) -> list[dict[str, Any]]:
    """Return up to 25 search run IDs matching the user's typed prefix."""
    session = session_factory()
    try:
        from app.models.search_run import SearchRun
        from sqlalchemy import select

        stmt = (
            select(SearchRun).order_by(SearchRun.requested_at.desc()).limit(25)
        )
        recent = list(session.execute(stmt).scalars().all())
    finally:
        session.close()

    query = focused_value.lower()
    matches = [r for r in recent if query in r.id.lower()]
    matches.sort(key=lambda r: (0 if r.id.lower().startswith(query) else 1, r.q))

    choices: list[dict[str, Any]] = []
    for r in matches[:max_choices]:
        label = (
            f"{r.q[:60]} ({r.id[:8]}…)"
            if len(r.id) > 8
            else f"{r.q[:60]} ({r.id})"
        )
        choices.append({"name": label[:100], "value": r.id})
    return choices


# ===========================================================================
# Option parsing helpers
# ===========================================================================

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
