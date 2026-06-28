from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.helpers import make_test_registry


@pytest.fixture
def api_key() -> str:
    return "test-api-key"


@pytest.fixture
def client(tmp_path, api_key: str) -> Generator[TestClient, None, None]:
    settings = Settings(
        api_key=api_key,
        database_url=f"sqlite:///{tmp_path / 'jobs-test.db'}",
        read_rate_limit=1000,
        write_rate_limit=1000,
        rate_limit_window_seconds=60,
        enable_mock_source=True,
    )
    app = create_app(settings)
    from app.core.container import Container

    app.state.container = Container(
        session_factory=app.state.session_factory,
        registry_factory=make_test_registry,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}
