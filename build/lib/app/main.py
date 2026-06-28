from fastapi import FastAPI, Request
from sqlalchemy import text

from app.api.v1.routes import router as v1_router
from app.config import Settings, get_settings
from app.database import Base, build_engine, build_session_factory
from app.models import Job, SearchRun, SearchRunJob, SourceStatus
from app.rate_limit import FixedWindowRateLimiter
from app.schemas import HealthResponse
from app.sources import build_source_registry

_ = (Job, SearchRun, SearchRunJob, SourceStatus)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    engine = build_engine(active_settings.database_url)
    session_factory = build_session_factory(engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        description="Compliance-first cached job search API.",
    )
    app.state.settings = active_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.rate_limiter = FixedWindowRateLimiter()

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        registry = build_source_registry(request.app.state.settings)
        return HealthResponse(
            status="ok",
            database="ok",
            enabled_sources=[name for name, adapter in registry.items() if adapter.enabled],
        )

    app.include_router(v1_router)
    return app


app = create_app()

