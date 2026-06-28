from unittest.mock import MagicMock

from fastapi.testclient import TestClient


ALERT_PAYLOAD = {
    "name": "Python India Alerts",
    "q": "python",
    "location": "India",
    "remote": True,
    "sources": ["mock"],
    "limit": 10,
    "check_interval_minutes": 60,
    "discord_webhook_url": "https://discord.com/api/webhooks/123/token",
    "slack_webhook_url": "https://hooks.slack.com/services/T000/B000/XXXX",
}


def test_create_alert_requires_api_key(client: TestClient) -> None:
    response = client.post("/api/v1/alerts", json=ALERT_PAYLOAD)
    assert response.status_code == 401


def test_create_and_get_alert(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/alerts", json=ALERT_PAYLOAD, headers=auth_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == ALERT_PAYLOAD["name"]
    assert body["q"] == ALERT_PAYLOAD["q"]
    assert body["sources"] == ["mock"]

    fetched = client.get(f"/api/v1/alerts/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_list_alerts(client: TestClient, auth_headers: dict[str, str]) -> None:
    for i in range(2):
        payload = {**ALERT_PAYLOAD, "name": f"Alert {i}"}
        resp = client.post("/api/v1/alerts", json=payload, headers=auth_headers)
        assert resp.status_code == 201

    response = client.get("/api/v1/alerts")
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) >= 2


def test_update_alert(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/alerts", json=ALERT_PAYLOAD, headers=auth_headers)
    alert_id = created.json()["id"]

    patch = {"name": "Updated Name", "enabled": False}
    updated = client.patch(f"/api/v1/alerts/{alert_id}", json=patch, headers=auth_headers)
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Updated Name"
    assert body["enabled"] is False


def test_delete_alert(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/alerts", json=ALERT_PAYLOAD, headers=auth_headers)
    alert_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/alerts/{alert_id}")
    assert missing.status_code == 404


def test_unknown_source_rejected_on_create(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = {**ALERT_PAYLOAD, "sources": ["not-real"]}
    response = client.post("/api/v1/alerts", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_sources"


def test_run_alert_manually(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/alerts",
        json={**ALERT_PAYLOAD, "discord_webhook_url": None, "slack_webhook_url": None},
        headers=auth_headers,
    )
    alert_id = created.json()["id"]

    run = client.post(f"/api/v1/alerts/{alert_id}/run", headers=auth_headers)
    assert run.status_code == 202

    executions = client.get(f"/api/v1/alerts/{alert_id}/executions")
    assert executions.status_code == 200
    items = executions.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "completed"
    assert items[0]["total_jobs_found"] == 1
    assert items[0]["new_jobs_count"] == 1


def test_second_run_finds_no_new_jobs(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/alerts",
        json={**ALERT_PAYLOAD, "discord_webhook_url": None, "slack_webhook_url": None},
        headers=auth_headers,
    )
    alert_id = created.json()["id"]

    client.post(f"/api/v1/alerts/{alert_id}/run", headers=auth_headers)
    client.post(f"/api/v1/alerts/{alert_id}/run", headers=auth_headers)

    executions = client.get(f"/api/v1/alerts/{alert_id}/executions")
    items = executions.json()["items"]
    assert len(items) == 2
    # Most recent first
    assert items[0]["new_jobs_count"] == 0
    assert items[1]["new_jobs_count"] == 1


def test_test_alert_endpoint(client: TestClient, auth_headers: dict[str, str], monkeypatch) -> None:
    created = client.post("/api/v1/alerts", json=ALERT_PAYLOAD, headers=auth_headers)
    alert_id = created.json()["id"]

    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_response.raise_for_status = MagicMock()

    def mock_post(url, **kwargs):
        return mock_response

    monkeypatch.setattr("app.services.notification_service.httpx.post", mock_post)

    response = client.post(f"/api/v1/alerts/{alert_id}/test", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Test notification sent"
    assert body["discord_status"] == "ok"
    assert body["slack_status"] == "ok"


def test_alert_executions_paginate(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/alerts",
        json={**ALERT_PAYLOAD, "discord_webhook_url": None, "slack_webhook_url": None},
        headers=auth_headers,
    )
    alert_id = created.json()["id"]

    client.post(f"/api/v1/alerts/{alert_id}/run", headers=auth_headers)

    first = client.get(f"/api/v1/alerts/{alert_id}/executions", params={"limit": 1})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 1
