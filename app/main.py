"""App factory + DI wiring."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import health_router, register_exception_handlers, router as v1_router
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.database import init_database
from app.core.rate_limit import FixedWindowRateLimiter
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
    print("=" * 60, flush=True)

    scheduler = AlertScheduler(
        engine=app.state.engine,
        session_factory=app.state.session_factory,
        container=app.state.container,
        settings=settings,
    )
    scheduler.start()
    app.state.alert_scheduler = scheduler
    try:
        yield
    finally:
        scheduler.stop()


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

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(v1_router)
    return app


app = create_app()
