"""Unit tests for the Discord /interactions FastAPI route."""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from app.core.config import Settings, get_settings
from app.main import create_app
from tests.helpers import make_test_registry


@pytest.fixture
def public_key_hex() -> str:
    sk = SigningKey.generate()
    return sk.verify_key.encode().hex()


@pytest.fixture
def private_key_hex() -> str:
    sk = SigningKey.generate()
    return sk.encode().hex()


@pytest.fixture
def signing_key() -> SigningKey:
    return SigningKey.generate()


@pytest.fixture
def discord_enabled_client(
    tmp_path, signing_key: SigningKey
) -> TestClient:
    settings = Settings(
        api_key="test-api-key",
        database_url=f"sqlite:///{tmp_path / 'jobs-test.db'}",
        read_rate_limit=1000,
        write_rate_limit=1000,
        rate_limit_window_seconds=60,
        enable_mock_source=True,
        discord_bot_token="test-bot-token",
        discord_public_key=signing_key.verify_key.encode().hex(),
        discord_guild_id=1234567890,
    )
    app = create_app(settings)
    from app.core.container import Container

    app.state.container = Container(
        session_factory=app.state.session_factory,
        registry_factory=make_test_registry,
    )
    return TestClient(app)


@pytest.fixture
def discord_disabled_client(tmp_path) -> TestClient:
    settings = Settings(
        api_key="test-api-key",
        database_url=f"sqlite:///{tmp_path / 'jobs-test.db'}",
        read_rate_limit=1000,
        write_rate_limit=1000,
        rate_limit_window_seconds=60,
        enable_mock_source=True,
        discord_bot_token="",
    )
    app = create_app(settings)
    from app.core.container import Container

    app.state.container = Container(
        session_factory=app.state.session_factory,
        registry_factory=make_test_registry,
    )
    return TestClient(app)


def _sign_body(signing_key: SigningKey, body: bytes, timestamp: str = "1234567890") -> str:
    return signing_key.sign(timestamp.encode("ascii") + body).signature.hex()


class TestRouteMounting:
    def test_route_404_when_bot_disabled(self, discord_disabled_client: TestClient):
        r = discord_disabled_client.post("/interactions", json={"type": 1})
        assert r.status_code == 404

    def test_route_exists_when_bot_enabled(self, discord_enabled_client: TestClient):
        # An invalid signature still gets a 401 (proves the route is mounted).
        r = discord_enabled_client.post("/interactions", json={"type": 1})
        assert r.status_code == 401


class TestSignatureVerification:
    def test_passes_with_valid_signature(
        self, discord_enabled_client: TestClient, signing_key: SigningKey
    ):
        body = json.dumps({"type": 1}).encode("utf-8")
        sig = _sign_body(signing_key, body)
        r = discord_enabled_client.post(
            "/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": sig,
                "X-Signature-Timestamp": "1234567890",
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 200
        assert r.json() == {"type": 1}

    def test_rejects_invalid_signature(self, discord_enabled_client: TestClient):
        r = discord_enabled_client.post(
            "/interactions",
            json={"type": 1},
            headers={
                "X-Signature-Ed25519": "0" * 128,
                "X-Signature-Timestamp": "1234567890",
            },
        )
        assert r.status_code == 401

    def test_rejects_missing_headers(self, discord_enabled_client: TestClient):
        r = discord_enabled_client.post("/interactions", json={"type": 1})
        assert r.status_code == 401


class TestPingPong:
    def test_ping_returns_pong(
        self, discord_enabled_client: TestClient, signing_key: SigningKey
    ):
        body = json.dumps({"type": 1}).encode("utf-8")
        sig = _sign_body(signing_key, body)
        r = discord_enabled_client.post(
            "/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": sig,
                "X-Signature-Timestamp": "1234567890",
            },
        )
        assert r.status_code == 200
        assert r.json() == {"type": 1}


class TestDispatch:
    def test_alert_list_with_no_alerts(
        self, discord_enabled_client: TestClient, signing_key: SigningKey
    ):
        payload = {
            "type": 2,
            "application_id": "app-id",
            "token": "tok",
            "data": {"name": "alert", "options": [{"name": "list", "type": 1}]},
        }
        body = json.dumps(payload).encode("utf-8")
        sig = _sign_body(signing_key, body)
        r = discord_enabled_client.post(
            "/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": sig,
                "X-Signature-Timestamp": "1234567890",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == 4  # channel_message
        assert "embeds" in data["data"]
        assert "No alerts" in data["data"]["embeds"][0]["description"]

    def test_alert_run_returns_deferred_response(
        self, discord_enabled_client: TestClient, signing_key: SigningKey
    ):
        payload = {
            "type": 2,
            "application_id": "app-id",
            "token": "tok",
            "data": {
                "name": "alert",
                "options": [
                    {
                        "name": "run",
                        "type": 1,
                        "options": [{"name": "alert_id", "value": "nonexistent", "type": 3}],
                    }
                ],
            },
        }
        body = json.dumps(payload).encode("utf-8")
        sig = _sign_body(signing_key, body)
        r = discord_enabled_client.post(
            "/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": sig,
                "X-Signature-Timestamp": "1234567890",
            },
        )
        assert r.status_code == 200
        data = r.json()
        # Alert doesn't exist -> error response (type 4, ephemeral)
        assert data["type"] == 4
        assert data["data"].get("flags") == 64  # ephemeral
        assert "not found" in data["data"]["embeds"][0]["description"].lower()

    def test_unknown_subcommand_returns_error(
        self, discord_enabled_client: TestClient, signing_key: SigningKey
    ):
        payload = {
            "type": 2,
            "application_id": "app-id",
            "token": "tok",
            "data": {"name": "alert", "options": [{"name": "bogus", "type": 1}]},
        }
        body = json.dumps(payload).encode("utf-8")
        sig = _sign_body(signing_key, body)
        r = discord_enabled_client.post(
            "/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": sig,
                "X-Signature-Timestamp": "1234567890",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "Unknown subcommand" in data["data"]["embeds"][0]["description"]

    def test_unsupported_interaction_type(
        self, discord_enabled_client: TestClient, signing_key: SigningKey
    ):
        payload = {"type": 99}  # not 1 (ping) or 2 (application_command)
        body = json.dumps(payload).encode("utf-8")
        sig = _sign_body(signing_key, body)
        r = discord_enabled_client.post(
            "/interactions",
            content=body,
            headers={
                "X-Signature-Ed25519": sig,
                "X-Signature-Timestamp": "1234567890",
            },
        )
        assert r.status_code == 400
