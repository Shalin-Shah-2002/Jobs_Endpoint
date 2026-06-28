from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.helpers import make_test_registry


def create_mock_search(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "q": "engineer",
        "location": "India",
        "remote": None,
        "sources": ["mock"],
        "limit": 10,
    }
    payload.update(overrides)
    response = client.post("/api/v1/search-runs", json=payload, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def test_health_and_sources(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert "mock" in health.json()["enabled_sources"]

    sources = client.get("/api/v1/sources")
    assert sources.status_code == 200
    body = {source["name"]: source for source in sources.json()}
    assert body["mock"]["enabled"] is True
    assert body["wellfound"]["enabled"] is True


def test_search_run_requires_api_key(client: TestClient) -> None:
    payload = {"q": "python", "sources": ["mock"]}
    missing = client.post("/api/v1/search-runs", json=payload)
    assert missing.status_code == 401

    invalid = client.post("/api/v1/search-runs", json=payload, headers={"X-API-Key": "wrong-key"})
    assert invalid.status_code == 403


def test_mock_search_run_creates_queryable_jobs(client: TestClient, auth_headers: dict[str, str]) -> None:
    run = create_mock_search(client, auth_headers, q="python", location="India", remote=True)

    fetched_run = client.get(f"/api/v1/search-runs/{run['id']}")
    assert fetched_run.status_code == 200
    assert fetched_run.json()["status"] == "completed"
    assert fetched_run.json()["total_jobs"] == 1

    run_jobs = client.get(f"/api/v1/search-runs/{run['id']}/jobs")
    assert run_jobs.status_code == 200
    assert len(run_jobs.json()["items"]) == 1
    assert run_jobs.json()["items"][0]["source"] == "mock"

    cached = client.get("/api/v1/jobs", params={"q": "python", "remote": True})
    assert cached.status_code == 200
    assert cached.json()["items"][0]["title"] == "Python Backend Engineer"


def test_get_job_and_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    run = create_mock_search(client, auth_headers, q="data")
    jobs = client.get(f"/api/v1/search-runs/{run['id']}/jobs").json()["items"]

    found = client.get(f"/api/v1/jobs/{jobs[0]['id']}")
    assert found.status_code == 200
    assert found.json()["title"] == "Data Engineer"

    missing = client.get("/api/v1/jobs/not-a-real-id")
    assert missing.status_code == 404


def test_mock_search_when_no_sources_configured(tmp_path, api_key: str) -> None:
    from app.core.config import Settings
    from app.main import create_app
    from app.sources.mock import MockSource
    from app.sources.wellfound import WellfoundSource
    from app.core.container import Container

    settings = Settings(
        api_key=api_key,
        database_url=f"sqlite:///{tmp_path / 'no-mock.db'}",
        read_rate_limit=1000,
        write_rate_limit=1000,
        rate_limit_window_seconds=60,
        enable_mock_source=False,
    )
    app = create_app(settings)

    app.state.container = Container(
        session_factory=app.state.session_factory,
        registry_factory=lambda s: {"mock": MockSource(), "wellfound": WellfoundSource()},
    )
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        headers = {"X-API-Key": api_key}
        payload = {"q": "python", "sources": ["mock"], "limit": 5}
        resp = c.post("/api/v1/search-runs", json=payload, headers=headers)
        assert resp.status_code == 202
        run_id = resp.json()["id"]
        fetched = c.get(f"/api/v1/search-runs/{run_id}")
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["status"] == "completed"
        assert body["total_jobs"] == 0


def test_unknown_source_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/search-runs",
        json={"q": "python", "sources": ["made-up-source"]},
        headers=auth_headers,
    )
    assert response.status_code == 400
    body = response.json()
    assert "Unknown source" in body["error"]["message"]
    assert body["error"]["code"] == "unknown_sources"


def test_pagination_and_deduping(client: TestClient, auth_headers: dict[str, str]) -> None:
    from base64 import b64decode

    create_mock_search(client, auth_headers, q="engineer", limit=10)
    create_mock_search(client, auth_headers, q="engineer", limit=10)

    first_page = client.get("/api/v1/jobs", params={"limit": 1})
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 1
    assert int(b64decode(first_page.json()["next_cursor"]).decode("utf-8")) == 1

    second_page = client.get("/api/v1/jobs", params={"limit": 1, "cursor": first_page.json()["next_cursor"]})
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1

    all_jobs = client.get("/api/v1/jobs", params={"limit": 100})
    source_urls = [job["source_url"] for job in all_jobs.json()["items"]]
    assert len(source_urls) == len(set(source_urls))


def test_invalid_inputs_are_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    too_large = client.get("/api/v1/jobs", params={"limit": 500})
    assert too_large.status_code == 422

    blank_query = client.post("/api/v1/search-runs", json={"q": "   "}, headers=auth_headers)
    assert blank_query.status_code == 422


def test_write_rate_limit(tmp_path, api_key: str) -> None:
    settings = Settings(
        api_key=api_key,
        database_url=f"sqlite:///{tmp_path / 'limited.db'}",
        read_rate_limit=1000,
        write_rate_limit=2,
        rate_limit_window_seconds=60,
        enable_mock_source=True,
    )
    app = create_app(settings)
    from app.core.container import Container

    app.state.container = Container(
        session_factory=app.state.session_factory,
        registry_factory=make_test_registry,
    )
    with TestClient(app) as limited_client:
        headers = {"X-API-Key": api_key}
        payload = {"q": "python", "sources": ["mock"]}
        assert limited_client.post("/api/v1/search-runs", json=payload, headers=headers).status_code == 202
        assert limited_client.post("/api/v1/search-runs", json=payload, headers=headers).status_code == 202
        response = limited_client.post("/api/v1/search-runs", json=payload, headers=headers)
        assert response.status_code == 429

