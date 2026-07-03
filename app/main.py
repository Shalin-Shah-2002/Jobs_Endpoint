"""App factory + DI wiring."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import health_router, register_exception_handlers, router as v1_router
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.database import init_database
from app.core.rate_limit import FixedWindowRateLimiter
from app.discord.bot import create_bot, start_bot, stop_bot
from app.models.registry import Job, SearchRun, SearchRunJob, SourceStatus  # noqa: F401  (registers models)
from app.services.alert_scheduler import AlertScheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = app.state.settings
    docs_url = app.docs_url or "/docs"
    openapi_url = app.openapi_url or "/openapi.json"
    print("=" * 60, flush=True)
    print(f"{settings.app_name} v{app.version}", flush=True)
    print("-" * 60, flush=True)
    print(f"  Swagger UI:  http://127.0.0.1:8000{docs_url}", flush=True)
    print(f"  OpenAPI:     http://127.0.0.1:8000{openapi_url}", flush=True)
    print(f"  ReDoc:       http://127.0.0.1:8000/redoc", flush=True)
    print(f"  Health:      http://127.0.0.1:8000/health", flush=True)
    print(f"  API base:    http://127.0.0.1:8000/api/v1", flush=True)
    if getattr(app.state, "discord_bot", None) is not None:
        print(f"  Discord:     bot enabled (guild {settings.discord_guild_id})", flush=True)
    else:
        print("  Discord:     disabled (no JOBS_DISCORD_BOT_TOKEN)", flush=True)
    print("=" * 60, flush=True)

    scheduler = AlertScheduler(
        engine=app.state.engine,
        session_factory=app.state.session_factory,
        container=app.state.container,
        settings=settings,
    )
    scheduler.start()
    app.state.alert_scheduler = scheduler

    bot_task: asyncio.Task[None] | None = None
    bot = getattr(app.state, "discord_bot", None)
    if bot is not None and settings.discord_bot_token:
        bot_task = asyncio.create_task(
            start_bot(bot, settings.discord_bot_token),
            name="discord-bot",
        )

    try:
        yield
    finally:
        scheduler.stop()
        if bot is not None and bot_task is not None:
            stop_bot(bot)
            bot_task.cancel()
            try:
                await bot_task
            except (asyncio.CancelledError, Exception):
                pass


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    engine, session_factory = init_database(active_settings)

    container = Container(session_factory=session_factory)

    app = FastAPI(
        title=active_settings.app_name,
        version="0.2.0",
        description="Compliance-first cached job search API.",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.rate_limiter = FixedWindowRateLimiter()
    app.state.container = container

    # Optional Discord bot — only wired if a token is configured.
    bot = create_bot(active_settings, container, session_factory)
    app.state.discord_bot = bot
    if bot is not None:
        from app.discord.interactions import router as discord_router
        app.include_router(discord_router)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(v1_router)
    return app


app = create_app()
