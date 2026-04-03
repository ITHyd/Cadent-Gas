from __future__ import annotations

import logging
from urllib.parse import parse_qs
import json

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .ai_parser import resolve_modal_argument
from .command_router import CommandError, parse_interaction_command, route_command, _execute_command
from .config import settings
from .slack_security import verify_slack_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cadent Slack Bot Service", version="0.1.0")


def _format_backend_error(status_code: int, detail: str) -> str:
    message = (detail or "").strip()
    if not message:
        message = "The request could not be completed."
    return "\n".join(
        [
            "*Request failed*",
            f"Status: `{status_code}`",
            f"Details: {message}",
        ]
    )


def _format_unexpected_error(exc: Exception) -> str:
    message = str(exc).strip() or "Unknown error"
    return "\n".join(
        [
            "*Unexpected error*",
            f"Details: {message}",
        ]
    )


def _interaction_payload(text: str, blocks: list[dict] | None = None) -> dict:
    return {
        "response_type": "ephemeral",
        "text": text,
        **({"blocks": blocks} if blocks else {}),
        "replace_original": False,
    }


async def _post_interaction_response(response_url: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(response_url, json=payload)
        response.raise_for_status()


async def _execute_and_post_command(response_url: str, command: str, args: list[str]) -> None:
    try:
        result = await _execute_command(command, args)
        await _post_interaction_response(response_url, _interaction_payload(result.text, result.blocks))
    except CommandError as exc:
        await _post_interaction_response(response_url, _interaction_payload(str(exc)))
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.warning("Backend HTTP error via async interaction task: %s", detail)
        await _post_interaction_response(
            response_url,
            _interaction_payload(_format_backend_error(exc.response.status_code, detail)),
        )
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("Unhandled async Slack interaction error")
        await _post_interaction_response(response_url, _interaction_payload(_format_unexpected_error(exc)))


def _incident_lookup_modal(response_url: str | None) -> dict:
    return {
        "type": "modal",
        "callback_id": "incident_lookup_submit",
        "private_metadata": response_url or "",
        "title": {"type": "plain_text", "text": "Incident Lookup"},
        "submit": {"type": "plain_text", "text": "Fetch"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "incident_input",
                "label": {"type": "plain_text", "text": "Incident ID"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "incident_id",
                    "placeholder": {"type": "plain_text", "text": "INC-1001"},
                },
            }
        ],
    }


def _agent_jobs_modal(response_url: str | None) -> dict:
    return {
        "type": "modal",
        "callback_id": "agent_jobs_submit",
        "private_metadata": response_url or "",
        "title": {"type": "plain_text", "text": "Agent Jobs"},
        "submit": {"type": "plain_text", "text": "Fetch"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "agent_input",
                "label": {"type": "plain_text", "text": "Agent ID"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "agent_id",
                    "placeholder": {"type": "plain_text", "text": "agent_001"},
                },
            }
        ],
    }


def _my_incidents_modal(response_url: str | None) -> dict:
    return {
        "type": "modal",
        "callback_id": "my_incidents_submit",
        "private_metadata": response_url or "",
        "title": {"type": "plain_text", "text": "My Incidents"},
        "submit": {"type": "plain_text", "text": "Fetch"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "user_input",
                "label": {"type": "plain_text", "text": "User ID"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "user_id",
                    "placeholder": {"type": "plain_text", "text": "user_001"},
                },
            }
        ],
    }


async def _open_slack_modal(trigger_id: str, view: dict) -> None:
    if not settings.slack_bot_token:
        raise RuntimeError("Slack modal support is not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://slack.com/api/views.open",
            headers={
                "Authorization": f"Bearer {settings.slack_bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"trigger_id": trigger_id, "view": view},
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack views.open failed: {data.get('error', 'unknown_error')}")


def _submitted_incident_input(payload: dict) -> str:
    values = payload.get("view", {}).get("state", {}).get("values", {})
    block = values.get("incident_input", {})
    value = str(block.get("incident_id", {}).get("value") or "").strip()
    if not value:
        raise CommandError("Please enter an incident ID.")
    return value


def _submitted_agent_input(payload: dict) -> str:
    values = payload.get("view", {}).get("state", {}).get("values", {})
    block = values.get("agent_input", {})
    value = str(block.get("agent_id", {}).get("value") or "").strip()
    if not value:
        raise CommandError("Please enter an agent ID.")
    return value


def _submitted_user_input(payload: dict) -> str:
    values = payload.get("view", {}).get("state", {}).get("values", {})
    block = values.get("user_input", {})
    value = str(block.get("user_id", {}).get("value") or "").strip()
    if not value:
        raise CommandError("Please enter a user ID.")
    return value


def _modal_response_url(payload: dict) -> str:
    return str(payload.get("view", {}).get("private_metadata") or "").strip()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/slack/commands")
async def slack_commands(request: Request) -> JSONResponse:
    raw_body = await request.body()
    if not verify_slack_signature(
        signing_secret=settings.slack_signing_secret,
        timestamp=request.headers.get("x-slack-request-timestamp"),
        signature=request.headers.get("x-slack-signature"),
        raw_body=raw_body,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = parse_qs(raw_body.decode("utf-8"))
    text = (form.get("text") or [""])[0]
    user_id = (form.get("user_id") or [""])[0]
    command = (form.get("command") or [""])[0]
    logger.info("Slack command received: command=%s user_id=%s text=%s", command, user_id, text)

    try:
        result = await route_command(text)
        return JSONResponse(
            {
                "response_type": result.response_type,
                "text": result.text,
                **({"blocks": result.blocks} if result.blocks else {}),
            }
        )
    except CommandError as exc:
        return JSONResponse(
            {
                "response_type": "ephemeral",
                "text": str(exc),
            },
            status_code=200,
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.warning("Backend HTTP error: %s", detail)
        return JSONResponse(
            {
                "response_type": "ephemeral",
                "text": _format_backend_error(exc.response.status_code, detail),
            },
            status_code=200,
        )
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("Unhandled Slack command error")
        return JSONResponse(
            {
                "response_type": "ephemeral",
                "text": _format_unexpected_error(exc),
            },
            status_code=200,
        )


@app.post("/slack/interactions")
async def slack_interactions(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    raw_body = await request.body()
    if not verify_slack_signature(
        signing_secret=settings.slack_signing_secret,
        timestamp=request.headers.get("x-slack-request-timestamp"),
        signature=request.headers.get("x-slack-signature"),
        raw_body=raw_body,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = parse_qs(raw_body.decode("utf-8"))
    payload_raw = (form.get("payload") or ["{}"])[0]
    payload = json.loads(payload_raw)
    logger.info("Slack interaction received: type=%s", payload.get("type"))
    response_url = payload.get("response_url")

    try:
        if payload.get("type") == "block_actions":
            actions = payload.get("actions") or []
            action_value = str(actions[0].get("value") or "").strip() if actions else ""
            if action_value == "__open_incident_modal__":
                await _open_slack_modal(payload.get("trigger_id", ""), _incident_lookup_modal(response_url))
                return JSONResponse({})
            if action_value == "__open_agent_jobs_modal__":
                await _open_slack_modal(payload.get("trigger_id", ""), _agent_jobs_modal(response_url))
                return JSONResponse({})
            if action_value == "__open_my_incidents_modal__":
                await _open_slack_modal(payload.get("trigger_id", ""), _my_incidents_modal(response_url))
                return JSONResponse({})

        if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "incident_lookup_submit":
            incident_input = _submitted_incident_input(payload)
            modal_response_url = _modal_response_url(payload)
            incident_id = await resolve_modal_argument("incident", incident_input)
            if not incident_id:
                raise CommandError("I couldn't recognize that incident ID. Try `INC-1001` or just `1001`.")
            if modal_response_url:
                background_tasks.add_task(_execute_and_post_command, modal_response_url, "incident", [incident_id])
            return JSONResponse({"response_action": "clear"})

        if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "agent_jobs_submit":
            agent_input = _submitted_agent_input(payload)
            modal_response_url = _modal_response_url(payload)
            agent_id = await resolve_modal_argument("agent-jobs", agent_input)
            if not agent_id:
                raise CommandError("I couldn't recognize that agent ID. Try `agent_001` or just `1`.")
            if modal_response_url:
                background_tasks.add_task(_execute_and_post_command, modal_response_url, "agent-jobs", [agent_id])
            return JSONResponse({"response_action": "clear"})

        if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "my_incidents_submit":
            user_input = _submitted_user_input(payload)
            modal_response_url = _modal_response_url(payload)
            user_id = await resolve_modal_argument("my-incidents", user_input)
            if not user_id:
                raise CommandError("I couldn't recognize that user ID. Try `user_001` or just `1`.")
            if modal_response_url:
                background_tasks.add_task(_execute_and_post_command, modal_response_url, "my-incidents", [user_id])
            return JSONResponse({"response_action": "clear"})

        command, args = parse_interaction_command(payload)
        result = await _execute_command(command, args)
        if response_url:
            background_tasks.add_task(
                _post_interaction_response,
                response_url,
                _interaction_payload(result.text, result.blocks),
            )
            return JSONResponse({})
        return JSONResponse(_interaction_payload(result.text, result.blocks))
    except CommandError as exc:
        payload = _interaction_payload(str(exc))
        if response_url:
            background_tasks.add_task(_post_interaction_response, response_url, payload)
            return JSONResponse({}, status_code=200)
        return JSONResponse(payload, status_code=200)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.warning("Backend HTTP error via interaction: %s", detail)
        payload = _interaction_payload(_format_backend_error(exc.response.status_code, detail))
        if response_url:
            background_tasks.add_task(_post_interaction_response, response_url, payload)
            return JSONResponse({}, status_code=200)
        return JSONResponse(payload, status_code=200)
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("Unhandled Slack interaction error")
        payload = _interaction_payload(_format_unexpected_error(exc))
        if response_url:
            background_tasks.add_task(_post_interaction_response, response_url, payload)
            return JSONResponse({}, status_code=200)
        return JSONResponse(payload, status_code=200)
