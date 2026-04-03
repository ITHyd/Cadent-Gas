from __future__ import annotations

import json
from dataclasses import dataclass
import httpx

from .ai_parser import ALLOWED_COMMANDS, parse_natural_language
from .backend_client import backend_client
from .config import settings
from .formatters import (
    format_agent_list,
    format_company_stats,
    format_detailed_incident_list,
    format_help,
    format_incident,
    format_incident_list,
    format_kb_entries,
    format_kb_stats,
    format_lookup_empty,
)


class CommandError(ValueError):
    """Raised when a command is invalid or incomplete."""


@dataclass
class SlackCommandResult:
    text: str
    response_type: str = "ephemeral"
    blocks: list[dict] | None = None


def _parts(text: str) -> list[str]:
    return [part for part in (text or "").strip().split() if part]


def _display_lookup_id(kind: str, raw_id: str) -> str:
    value = (raw_id or "").strip()
    lowered = value.lower()
    if kind == "incident" and lowered.startswith("inc-"):
        return value[4:]
    if kind == "agent" and lowered.startswith("agent_"):
        return value[6:]
    if kind == "user" and lowered.startswith("user_"):
        return value[5:]
    return value


def _help_blocks() -> list[dict]:
    quick_actions = [
        ("Incident Lookup", "__open_incident_modal__"),
        ("Agent Jobs Lookup", "__open_agent_jobs_modal__"),
        ("My Incidents Lookup", "__open_my_incidents_modal__"),
        ("Company Stats", "company-stats"),
        ("Pending Incidents", "pending-incidents"),
        ("Available Agents", "available-agents"),
        ("All Agents", "all-agents"),
        ("KB Stats", "kb-stats"),
        ("KB True", "kb-true"),
        ("KB False", "kb-false"),
        ("KB Recent", "kb-recent"),
    ]

    action_elements = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": label},
            "action_id": f"cmd_{value.replace('-', '_')}",
            "value": value,
        }
        for label, value in quick_actions
    ]

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Cadent Slack commands*\nUse the buttons below to continue.",
            },
        },
        {"type": "actions", "elements": action_elements[:5]},
        {"type": "actions", "elements": action_elements[5:]},
    ]


async def _execute_command(command: str, args: list[str]) -> SlackCommandResult:
    if command in {"help", "?"}:
        return SlackCommandResult(format_help(), blocks=_help_blocks())

    if command == "incident":
        if not args:
            raise CommandError("Please enter an incident ID, for example `INC-1001`.")
        try:
            data = await backend_client.get(f"/api/v1/incidents/{args[0]}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return SlackCommandResult(
                    format_lookup_empty("Incident ID", _display_lookup_id("incident", args[0]), "Incident not found.")
                )
            raise
        return SlackCommandResult(format_incident(data))

    if command == "company-stats":
        tenant_id = args[0] if args else settings.default_tenant_id
        data = await backend_client.get(f"/api/v1/incidents/company/{tenant_id}/stats")
        return SlackCommandResult(format_company_stats(tenant_id, data))

    if command == "pending-incidents":
        tenant_id = args[0] if args else settings.default_tenant_id
        data = await backend_client.get(f"/api/v1/incidents/company/{tenant_id}", params={"status": "pending_company_action"})
        incidents = data.get("incidents", []) if isinstance(data, dict) else data
        return SlackCommandResult(format_incident_list(f"Pending incidents: {tenant_id}", incidents))

    if command == "agent-jobs":
        if not args:
            raise CommandError("Please enter an agent ID, for example `agent_001`.")
        data = await backend_client.get(f"/api/v1/incidents/agent/{args[0]}/incidents")
        incidents = data.get("incidents", []) if isinstance(data, dict) else data
        if not incidents:
            return SlackCommandResult(
                format_lookup_empty("Agent ID", _display_lookup_id("agent", args[0]), "No records found.")
            )
        return SlackCommandResult(format_incident_list(f"Agent jobs: {args[0]}", incidents))

    if command == "my-incidents":
        if not args:
            raise CommandError("Please enter a user ID, for example `user_001`.")
        data = await backend_client.get(f"/api/v1/incidents/user/{args[0]}")
        incidents = data.get("incidents", []) if isinstance(data, dict) else data
        if not incidents:
            return SlackCommandResult(
                format_lookup_empty("User ID", _display_lookup_id("user", args[0]), "No records found.")
            )
        return SlackCommandResult(format_detailed_incident_list(f"My incidents: {args[0]}", incidents))

    if command == "available-agents":
        data = await backend_client.get("/api/v1/incidents/agents/available")
        agents = data.get("agents", []) if isinstance(data, dict) else data
        return SlackCommandResult(format_agent_list("Available agents", agents))

    if command == "all-agents":
        data = await backend_client.get("/api/v1/incidents/agents/all")
        agents = data.get("agents", []) if isinstance(data, dict) else data
        return SlackCommandResult(format_agent_list("All agents", agents))

    if command == "kb-stats":
        tenant_id = args[0] if args else settings.default_tenant_id
        data = await backend_client.get("/api/v1/kb/stats", params={"tenant_id": tenant_id})
        return SlackCommandResult(format_kb_stats(tenant_id, data))

    if command == "kb-true":
        tenant_id = args[0] if args else settings.default_tenant_id
        data = await backend_client.get("/api/v1/kb/true", params={"tenant_id": tenant_id, "limit": 10, "page": 1})
        entries = data.get("items", []) if isinstance(data, dict) else data
        return SlackCommandResult(format_kb_entries(f"KB true incidents: {tenant_id}", entries))

    if command == "kb-false":
        tenant_id = args[0] if args else settings.default_tenant_id
        data = await backend_client.get("/api/v1/kb/false", params={"tenant_id": tenant_id, "limit": 10, "page": 1})
        entries = data.get("items", []) if isinstance(data, dict) else data
        return SlackCommandResult(format_kb_entries(f"KB false incidents: {tenant_id}", entries))

    if command == "kb-recent":
        tenant_id = args[0] if args else settings.default_tenant_id
        data = await backend_client.get("/api/v1/kb/recent", params={"tenant_id": tenant_id, "limit": 10})
        entries = data.get("entries", []) if isinstance(data, dict) else data
        return SlackCommandResult(format_kb_entries(f"KB recent entries: {tenant_id}", entries))

    raise CommandError("I couldn't recognize that request. Try `help` to see what I can do.")


async def route_command(text: str) -> SlackCommandResult:
    parts = _parts(text)
    if not parts:
        return SlackCommandResult(format_help(), blocks=_help_blocks())

    command = parts[0].lower()
    args = parts[1:]

    if command in ALLOWED_COMMANDS or command == "?":
        return await _execute_command(command, args)

    parsed = await parse_natural_language(text)
    if parsed and parsed.matched and parsed.command:
        return await _execute_command(parsed.command, parsed.args)

    raise CommandError("I couldn't understand that request. Try `help` or enter something like `incident INC-1001`.")


def parse_interaction_command(payload: dict) -> tuple[str, list[str]]:
    actions = payload.get("actions") or []
    if not actions:
        raise CommandError("I couldn't process that click. Please try again.")

    value = str(actions[0].get("value") or "").strip()
    if not value:
        raise CommandError("That action was incomplete. Please try again.")

    parts = _parts(value)
    if not parts:
        raise CommandError("That action did not include a valid request. Please try again.")

    command = parts[0].lower()
    args = parts[1:]
    return command, args
