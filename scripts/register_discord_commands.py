"""Register Discord slash commands for the Jobs Endpoint bot.

This script registers all slash commands with Discord's REST API for a
specific guild. Run it once after creating your bot, and re-run whenever
you change the command schemas.

Usage:
    uv run python scripts/register_discord_commands.py

Required env vars (in ``.env``):
    JOBS_DISCORD_BOT_TOKEN      — from Discord Developer Portal → Bot
    JOBS_DISCORD_APPLICATION_ID — from Discord Developer Portal → General Information
    JOBS_DISCORD_GUILD_ID       — your test server ID (right-click → Copy ID)
"""
from __future__ import annotations

import os
import sys
from typing import Any

import httpx


DISCORD_API_BASE = "https://discord.com/api/v10"


COMMANDS: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # /alert — Manage job alerts
    # ------------------------------------------------------------------
    {
        "name": "alert",
        "description": "Manage job alerts.",
        "options": [
            {
                "name": "create",
                "description": "Create a new job alert.",
                "type": 1,  # SUB_COMMAND
                "options": [
                    {"name": "name", "description": "Human label for the alert.", "type": 3, "required": True},
                    {"name": "q", "description": "Search query.", "type": 3, "required": True},
                    {"name": "location", "description": "Optional location filter.", "type": 3, "required": False},
                    {"name": "remote", "description": "Remote only (true/false/blank=any).", "type": 5, "required": False},
                    {"name": "sources", "description": "Comma-separated source names (e.g. mock,wellfound).", "type": 3, "required": False},
                    {"name": "limit", "description": "Max jobs per run (1-100).", "type": 4, "required": False, "min_value": 1, "max_value": 100},
                    {"name": "check_interval_minutes", "description": "Re-check interval in minutes (5-10080).", "type": 4, "required": False, "min_value": 5, "max_value": 10080},
                    {"name": "discord_webhook_url", "description": "Discord delivery webhook.", "type": 3, "required": False, "autocomplete": True},
                    {"name": "slack_webhook_url", "description": "Slack delivery webhook.", "type": 3, "required": False, "autocomplete": True},
                    {"name": "enabled", "description": "Whether the scheduler runs this alert.", "type": 5, "required": False},
                ],
            },
            {
                "name": "list",
                "description": "List all configured alerts.",
                "type": 1,
            },
            {
                "name": "run",
                "description": "Trigger an alert immediately.",
                "type": 1,
                "options": [
                    {"name": "alert_id", "description": "Alert ID (from /alert list).", "type": 3, "required": True, "autocomplete": True},
                ],
            },
            {
                "name": "test",
                "description": "Send a test notification through the alert's webhooks.",
                "type": 1,
                "options": [
                    {"name": "alert_id", "description": "Alert ID (from /alert list).", "type": 3, "required": True, "autocomplete": True},
                ],
            },
            {
                "name": "info",
                "description": "Show full details for a single alert.",
                "type": 1,
                "options": [
                    {"name": "alert_id", "description": "Alert ID (from /alert list).", "type": 3, "required": True, "autocomplete": True},
                ],
            },
            {
                "name": "delete",
                "description": "Delete an alert permanently.",
                "type": 1,
                "options": [
                    {"name": "alert_id", "description": "Alert ID (from /alert list).", "type": 3, "required": True, "autocomplete": True},
                ],
            },
            {
                "name": "toggle",
                "description": "Enable or disable an alert.",
                "type": 1,
                "options": [
                    {"name": "alert_id", "description": "Alert ID (from /alert list).", "type": 3, "required": True, "autocomplete": True},
                ],
            },
            {
                "name": "executions",
                "description": "View execution history for an alert.",
                "type": 1,
                "options": [
                    {"name": "alert_id", "description": "Alert ID (from /alert list).", "type": 3, "required": True, "autocomplete": True},
                    {"name": "limit", "description": "Max executions to show (1-25).", "type": 4, "required": False, "min_value": 1, "max_value": 25},
                ],
            },
            {
                "name": "edit",
                "description": "Update properties of an existing alert.",
                "type": 1,
                "options": [
                    {"name": "alert_id", "description": "Alert ID (from /alert list).", "type": 3, "required": True, "autocomplete": True},
                    {"name": "name", "description": "New human label for the alert.", "type": 3, "required": False},
                    {"name": "q", "description": "New search query.", "type": 3, "required": False},
                    {"name": "location", "description": "New location filter.", "type": 3, "required": False},
                    {"name": "remote", "description": "New remote filter.", "type": 5, "required": False},
                    {"name": "sources", "description": "Comma-separated source names.", "type": 3, "required": False},
                    {"name": "limit", "description": "Max jobs per run (1-100).", "type": 4, "required": False, "min_value": 1, "max_value": 100},
                    {"name": "check_interval_minutes", "description": "Re-check interval in minutes (5-10080).", "type": 4, "required": False, "min_value": 5, "max_value": 10080},
                    {"name": "discord_webhook_url", "description": "Discord delivery webhook.", "type": 3, "required": False},
                    {"name": "slack_webhook_url", "description": "Slack delivery webhook.", "type": 3, "required": False},
                    {"name": "enabled", "description": "Whether the scheduler runs this alert.", "type": 5, "required": False},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------
    # /jobs — Search and browse cached jobs
    # ------------------------------------------------------------------
    {
        "name": "jobs",
        "description": "Search and browse cached job listings.",
        "options": [
            {
                "name": "search",
                "description": "Search cached jobs by keyword, location, and filters.",
                "type": 1,
                "options": [
                    {"name": "q", "description": "Search query (job title, company, keyword).", "type": 3, "required": True},
                    {"name": "location", "description": "Location filter.", "type": 3, "required": False},
                    {"name": "remote", "description": "Remote only.", "type": 5, "required": False},
                    {"name": "source", "description": "Source name (e.g. wellfound, mock).", "type": 3, "required": False},
                    {"name": "limit", "description": "Max results (1-25).", "type": 4, "required": False, "min_value": 1, "max_value": 25},
                ],
            },
            {
                "name": "get",
                "description": "Get full details for a specific job by ID.",
                "type": 1,
                "options": [
                    {"name": "job_id", "description": "Job ID.", "type": 3, "required": True, "autocomplete": True},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------
    # /search — On-demand search runs
    # ------------------------------------------------------------------
    {
        "name": "search",
        "description": "Execute on-demand job searches and check their status.",
        "options": [
            {
                "name": "create",
                "description": "Run a new job search across enabled sources.",
                "type": 1,
                "options": [
                    {"name": "q", "description": "Search query.", "type": 3, "required": True},
                    {"name": "location", "description": "Location filter.", "type": 3, "required": False},
                    {"name": "remote", "description": "Remote only.", "type": 5, "required": False},
                    {"name": "sources", "description": "Comma-separated source names (e.g. mock,wellfound).", "type": 3, "required": False},
                    {"name": "limit", "description": "Max results per source (1-100).", "type": 4, "required": False, "min_value": 1, "max_value": 100},
                ],
            },
            {
                "name": "status",
                "description": "Check the status and results of a search run.",
                "type": 1,
                "options": [
                    {"name": "run_id", "description": "Search run ID.", "type": 3, "required": True, "autocomplete": True},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------
    # /sources — List job sources
    # ------------------------------------------------------------------
    {
        "name": "sources",
        "description": "List available job sources and their status.",
        "options": [
            {
                "name": "list",
                "description": "Show all configured job sources with their current status.",
                "type": 1,
            },
        ],
    },
]


def main() -> int:
    bot_token = os.environ.get("JOBS_DISCORD_BOT_TOKEN")
    application_id = os.environ.get("JOBS_DISCORD_APPLICATION_ID")
    guild_id = os.environ.get("JOBS_DISCORD_GUILD_ID")

    missing = [
        name
        for name, val in (
            ("JOBS_DISCORD_BOT_TOKEN", bot_token),
            ("JOBS_DISCORD_APPLICATION_ID", application_id),
            ("JOBS_DISCORD_GUILD_ID", guild_id),
        )
        if not val
    ]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        print(
            "Set them in .env or in the shell, then re-run.",
            file=sys.stderr,
        )
        return 1

    url = f"{DISCORD_API_BASE}/applications/{application_id}/guilds/{guild_id}/commands"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    print(f"Registering {len(COMMANDS)} command(s) with guild {guild_id}…")
    with httpx.Client(timeout=30.0) as client:
        resp = client.put(url, headers=headers, json=COMMANDS)
        if resp.status_code >= 400:
            print(
                f"  ✗ {resp.status_code} {resp.text[:500]}",
                file=sys.stderr,
            )
            return 1
        for cmd in resp.json():
            print(f"  ✓ {cmd.get('name')} (id: {cmd.get('id')})")

    print("Done. Commands are now available in the guild (instant sync).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
