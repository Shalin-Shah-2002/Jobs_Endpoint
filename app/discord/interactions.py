"""FastAPI route that handles incoming Discord interactions.

This module is the boundary between Discord's HTTP and the rest of the app.
It is responsible for:

1. Verifying the ed25519 signature (with the configured public key).
2. Responding to PING (type 1) with PONG (type 1).
3. Parsing slash-command payloads and dispatching to :mod:`commands`.
4. For long-running commands (``/alert run``), scheduling the work as a
   background task and using a follow-up webhook to send the final result.

The route is mounted on the FastAPI app *only* if a Discord bot is
configured (see :mod:`app.discord.bot`). Otherwise it is absent.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter, Request, Response, status
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from app.discord.commands import autocomplete_alert_id, autocomplete_webhook_url, dispatch, execute_and_build_result, get_subcommand, parse_options

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter()


PONG_RESPONSE = {"type": 1}
DISCORD_API_BASE = "https://discord.com/api/v10"


def _verify_signature(public_key_hex: str, signature_hex: str, timestamp: str, body: bytes) -> bool:
    """Verify the ed25519 signature Discord sends with every interaction.

    Reference: https://discord.com/developers/docs/interactions/receiving-and-responding#security-and-authorization
    """
    if not public_key_hex:
        return False
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
    except (ValueError, TypeError):
        logger.exception("Invalid JOBS_DISCORD_PUBLIC_KEY (not valid hex)")
        return False
    message = timestamp.encode("ascii") + body
    try:
        verify_key.verify(message, bytes.fromhex(signature_hex))
    except BadSignatureError:
        return False
    except (ValueError, TypeError):
        return False
    return True


async def _send_followup(
    application_id: str,
    interaction_token: str,
    bot_token: str,
    body: dict[str, Any],
) -> None:
    """POST a follow-up message to Discord."""
    url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}"
    headers = {"Authorization": f"Bot {bot_token}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "Discord follow-up failed: %s %s", resp.status_code, resp.text[:200]
                )
    except Exception:
        logger.exception("Failed to send Discord follow-up message")


async def _run_alert_background(
    alert_id: str,
    application_id: str,
    interaction_token: str,
    bot_token: str,
    container: Any,
    session_factory: Any,
) -> None:
    """Background coroutine: run the alert, then send the result as a follow-up."""
    try:
        result = await execute_and_build_result(alert_id, container, session_factory)
        await _send_followup(application_id, interaction_token, bot_token, result)
    except Exception:
        logger.exception("Background alert run failed")
        await _send_followup(
            application_id,
            interaction_token,
            bot_token,
            {"content": "Internal error during alert execution."},
        )


@router.post("/interactions")
async def interactions(request: Request) -> Response:
    bot = getattr(request.app.state, "discord_bot", None)
    settings = request.app.state.settings
    if bot is None:
        return Response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content="Discord bot is not configured",
        )

    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    body = await request.body()

    if not _verify_signature(settings.discord_public_key, signature, timestamp, body):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, content="Invalid signature")

    try:
        payload: dict[str, Any] = json.loads(body)
    except ValueError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid JSON")

    interaction_type = payload.get("type")
    # PING — respond with PONG (type 1).
    if interaction_type == 1:
        return Response(
            status_code=status.HTTP_200_OK,
            content=json.dumps(PONG_RESPONSE),
            media_type="application/json",
        )

    # APPLICATION_COMMAND_AUTOCOMPLETE (type 4) — suggest alert IDs / webhook URLs.
    if interaction_type == 4:
        data = payload.get("data") or {}
        options = data.get("options", [])
        sub, sub_opts = get_subcommand(options)

        # Extract the focused option (name + typed value).
        focused_name: str | None = None
        focused_value: str | None = None
        for opt in (sub_opts or []):
            if opt.get("focused"):
                focused_name = str(opt.get("name", ""))
                focused_value = str(opt.get("value", ""))
                break

        if focused_value is not None:
            # Autocomplete alert_id in run/test subcommands.
            if sub in ("run", "test") and focused_name == "alert_id":
                choices = await autocomplete_alert_id(
                    focused_value,
                    request.app.state.container,
                    request.app.state.session_factory,
                )
                return Response(
                    status_code=status.HTTP_200_OK,
                    content=json.dumps({"type": 8, "data": {"choices": choices}}),
                    media_type="application/json",
                )
            # Autocomplete webhook URLs in create subcommand.
            if sub == "create" and focused_name in ("discord_webhook_url", "slack_webhook_url"):
                choices = await autocomplete_webhook_url(
                    focused_value,
                    request.app.state.container,
                    request.app.state.session_factory,
                    field=focused_name,
                )
                return Response(
                    status_code=status.HTTP_200_OK,
                    content=json.dumps({"type": 8, "data": {"choices": choices}}),
                    media_type="application/json",
                )
        return Response(
            status_code=status.HTTP_200_OK,
            content=json.dumps({"type": 8, "data": {"choices": []}}),
            media_type="application/json",
        )

    # APPLICATION_COMMAND (type 2) — dispatch.
    if interaction_type != 2:
        return Response(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=f"Unsupported interaction type: {interaction_type}",
        )

    data = payload.get("data") or {}
    sub, sub_opts = get_subcommand(data.get("options"))
    options = parse_options(sub_opts)
    container = request.app.state.container
    session_factory = request.app.state.session_factory

    response_payload = await dispatch(sub, options, container, session_factory)

    # Special handling for /alert run — defer the work so we hit the 3s window.
    if sub == "run" and response_payload.get("type") == 5:
        application_id = payload.get("application_id", "")
        interaction_token = payload.get("token", "")
        alert_id = options.get("alert_id", "")
        if application_id and interaction_token and alert_id:
            asyncio.create_task(
                _run_alert_background(
                    alert_id,
                    application_id,
                    interaction_token,
                    settings.discord_bot_token,
                    container,
                    session_factory,
                )
            )

    return Response(
        status_code=status.HTTP_200_OK,
        content=json.dumps(response_payload),
        media_type="application/json",
    )
