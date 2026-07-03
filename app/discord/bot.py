"""Discord bot lifecycle — optional factory and event-loop integration.

The bot is opt-in: if ``discord_bot_token`` is empty in settings, the factory
returns ``None`` and the rest of the app runs without Discord.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from app.core.config import Settings
    from app.core.container import Container

logger = logging.getLogger(__name__)


def _build_bot() -> commands.Bot:
    """Construct a minimal discord.Bot instance.

    Intents are kept at the default (no privileged intents) because the bot
    only receives interactions over HTTP — no presence, members, or message
    content is needed.
    """
    intents = discord.Intents.none()
    return commands.Bot(intents=intents)


def create_bot(
    settings: Settings,
    container: Container,
    session_factory: sessionmaker,
) -> commands.Bot | None:
    """Build and configure the Discord bot, or return ``None`` if disabled."""
    if not settings.discord_bot_token:
        return None
    bot = _build_bot()
    bot._jobs_container = container  # type: ignore[attr-defined]
    bot._jobs_session_factory = session_factory  # type: ignore[attr-defined]
    bot._jobs_settings = settings  # type: ignore[attr-defined]
    return bot


async def start_bot(bot: commands.Bot, token: str) -> None:
    """Connect the bot to Discord's gateway.

    Safe to call from the FastAPI lifespan — runs on uvicorn's event loop.
    """
    logger.info("Starting Discord bot…")
    try:
        await bot.start(token)
    except Exception:
        logger.exception("Discord bot crashed")
        raise


def stop_bot(bot: commands.Bot) -> None:
    """Schedule bot shutdown on the running event loop."""
    if bot.is_closed():
        return
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(bot.close())
    else:
        # Fallback for tests/sync contexts
        loop.run_until_complete(bot.close())
