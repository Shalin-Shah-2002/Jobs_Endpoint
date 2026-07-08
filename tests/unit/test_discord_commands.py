"""Unit tests for Discord slash-command handlers (pure functions)."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.container import Container
from app.core.database import Base
from app.discord.commands import (
    ALERT_COMMAND_REGISTRY,
    _embed,
    _embed_error,
    _error_response,
    dispatch,
    get_subcommand,
    parse_options,
)
from app.models.registry import Job, SearchRun, SearchRunJob, SourceStatus  # noqa: F401
from tests.helpers import make_test_registry


@pytest.fixture
def container() -> Container:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    sf = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    return Container(session_factory=sf, registry_factory=make_test_registry)


class TestParseOptions:
    def test_empty(self):
        assert parse_options(None) == {}
        assert parse_options([]) == {}

    def test_flat_options(self):
        opts = [
            {"name": "name", "value": "foo"},
            {"name": "limit", "value": 25},
        ]
        assert parse_options(opts) == {"name": "foo", "limit": 25}


class TestGetSubcommand:
    def test_no_options(self):
        assert get_subcommand(None) == ("", None)
        assert get_subcommand([]) == ("", None)

    def test_finds_subcommand(self):
        opts = [
            {"name": "create", "type": 1, "options": [{"name": "name", "value": "x"}]}
        ]
        sub, sub_opts = get_subcommand(opts)
        assert sub == "create"
        assert sub_opts == [{"name": "name", "value": "x"}]

    def test_passthrough_when_no_subcommand(self):
        opts = [{"name": "name", "value": "x"}]
        sub, sub_opts = get_subcommand(opts)
        assert sub == ""
        assert sub_opts == opts


class TestRegistry:
    def test_all_commands_registered(self):
        assert set(ALERT_COMMAND_REGISTRY.keys()) == {
            "create", "list", "run", "test",
            "info", "delete", "toggle", "executions", "edit",
        }


class TestDispatch:
    def test_dispatches_create(self, container: Container):
        # Required: name, q
        options = {"name": "Test", "q": "flutter"}
        result = asyncio.run(
            dispatch("alert", "create", options, container, container.session_factory)
        )
        assert result["type"] == 4
        assert "embeds" in result["data"]

    def test_dispatches_list_empty(self, container: Container):
        result = asyncio.run(
            dispatch("alert", "list", {}, container, container.session_factory)
        )
        assert result["type"] == 4
        assert "No alerts" in result["data"]["embeds"][0]["description"]

    def test_unknown_subcommand(self, container: Container):
        result = asyncio.run(
            dispatch("alert", "bogus", {}, container, container.session_factory)
        )
        assert "Unknown" in result["data"]["embeds"][0]["description"]

    def test_unknown_command_group(self, container: Container):
        result = asyncio.run(
            dispatch("bogus", "x", {}, container, container.session_factory)
        )
        assert "Unknown command" in result["data"]["embeds"][0]["description"]


class TestEmbeds:
    def test_embed_has_required_fields(self):
        e = _embed("title", "desc", color=0x123456)
        assert e == {"title": "title", "description": "desc", "color": 0x123456}

    def test_embed_error_is_red(self):
        e = _embed_error("oops")
        assert e["title"] == "Error"
        assert e["color"] == 0xED4245

    def test_error_response_is_ephemeral(self):
        r = _error_response("bad")
        assert r["type"] == 4
        assert r["data"]["flags"] == 64
        assert r["data"]["embeds"][0]["title"] == "Error"
