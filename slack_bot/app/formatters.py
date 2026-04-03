from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _truncate(value: str, limit: int = 120) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def format_help() -> str:
    return "\n".join(
        [
            "*Cadent Slack commands*",
            "`help`",
            "`incident <incident_id>`",
            "`company-stats`",
            "`pending-incidents`",
            "`agent-jobs <agent_id>`",
            "`my-incidents <user_id>`",
            "`available-agents`",
            "`kb-stats`",
            "`kb-true`",
            "`kb-false`",
            "`kb-recent`",
        ]
    )


def format_incident(data: Dict[str, Any]) -> str:
    timeline = data.get("timeline", []) or []
    latest_step = next(
        (
            item.get("label")
            for item in reversed(timeline)
            if item.get("completed") or item.get("in_progress")
        ),
        "Unknown",
    )
    return "\n".join(
        [
            f"*Incident {data.get('incident_id', '-') }*",
            f"Status: `{data.get('status', '-')}`",
            f"Outcome: `{data.get('outcome') or 'n/a'}`",
            f"Risk score: `{data.get('risk_score', 'n/a')}`",
            f"Type: `{data.get('incident_type') or data.get('classified_use_case') or 'n/a'}`",
            f"Location: {_truncate(data.get('location') or data.get('user_address') or 'n/a', 100)}",
            f"Latest step: {latest_step}",
            f"Description: {_truncate(data.get('description') or 'n/a', 180)}",
        ]
    )


def format_company_stats(tenant_id: str, data: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"*Company Stats: {tenant_id}*",
            f"Total: `{data.get('total', 0)}`",
            f"New: `{data.get('new', 0)}`",
            f"In progress: `{data.get('in_progress', 0)}`",
            f"Pending: `{data.get('pending', 0)}`",
            f"Dispatched: `{data.get('dispatched', 0)}`",
            f"Resolved: `{data.get('resolved', 0)}`",
            f"Completed: `{data.get('completed', 0)}`",
            f"False reports: `{data.get('false_reports', 0)}`",
            f"Avg risk: `{round(float(data.get('avg_risk_score', 0) or 0), 3)}`",
        ]
    )


def format_incident_list(title: str, incidents: Iterable[Dict[str, Any]], limit: int = 10) -> str:
    items = list(incidents)
    if not items:
        return f"*{title}*\nNo records found."

    lines: List[str] = [f"*{title}*"]
    for incident in items[:limit]:
        lines.append(
            "• "
            + f"{incident.get('incident_id', '-')}"
            + f" | `{incident.get('status', '-')}`"
            + f" | {_truncate(incident.get('incident_type') or incident.get('classified_use_case') or 'n/a', 30)}"
            + f" | {_truncate(incident.get('description') or '', 80)}"
        )

    remaining = len(items) - min(len(items), limit)
    if remaining > 0:
        lines.append(f"...and {remaining} more")

    return "\n".join(lines)


def format_lookup_empty(label: str, value: str, message: str = "No records found.") -> str:
    return "\n".join(
        [
            f"*{label}: {value}*",
            message,
        ]
    )


def format_detailed_incident_list(title: str, incidents: Iterable[Dict[str, Any]], limit: int = 10) -> str:
    items = list(incidents)
    if not items:
        return f"*{title}*\nNo records found."

    lines: List[str] = [f"*{title}*"]
    for incident in items[:limit]:
        lines.extend(
            [
                f"*{incident.get('incident_id', '-')}*",
                f"Status: `{incident.get('status', '-')}`",
                f"Outcome: `{incident.get('outcome') or 'n/a'}`",
                f"Risk score: `{incident.get('risk_score', 'n/a')}`",
                f"Type: `{incident.get('incident_type') or incident.get('classified_use_case') or 'n/a'}`",
                f"Location: {_truncate(incident.get('location') or incident.get('user_address') or 'n/a', 100)}",
                f"Description: {_truncate(incident.get('description') or 'n/a', 180)}",
                "",
            ]
        )

    if lines and lines[-1] == "":
        lines.pop()

    remaining = len(items) - min(len(items), limit)
    if remaining > 0:
        lines.append(f"...and {remaining} more")

    return "\n".join(lines)


def format_agent_list(title: str, agents: Iterable[Dict[str, Any]], limit: int = 10) -> str:
    items = list(agents)
    if not items:
        return f"*{title}*\nNo records found."

    lines: List[str] = [f"*{title}*"]
    for agent in items[:limit]:
        lines.append(
            "• "
            + f"{agent.get('agent_id', '-')}"
            + f" | {agent.get('full_name', 'Unknown')}"
            + f" | {_truncate(agent.get('specialization') or 'n/a', 40)}"
            + f" | {_truncate(agent.get('location') or 'n/a', 40)}"
        )

    remaining = len(items) - min(len(items), limit)
    if remaining > 0:
        lines.append(f"...and {remaining} more")

    return "\n".join(lines)


def format_kb_search(data: Dict[str, Any]) -> str:
    results = data.get("results", []) or []
    if not results:
        return f"*KB Search*\nNo results found for `{data.get('query', '')}`."

    lines = [f"*KB Search: {data.get('query', '')}*"]
    for item in results[:8]:
        label = item.get("use_case") or item.get("reported_as") or item.get("kb_id") or "match"
        description = item.get("description") or item.get("actual_issue") or ""
        lines.append(f"• `{label}` | {_truncate(description, 100)}")
    return "\n".join(lines)


def format_connector_status(tenant_id: str, data: Dict[str, Any]) -> str:
    connectors = data.get("connectors", []) or []
    if not connectors:
        return f"*Connector Status: {tenant_id}*\nNo connectors found."

    lines = [f"*Connector Status: {tenant_id}*"]
    for item in connectors:
        lines.append(
            "• "
            + f"{item.get('connector_type', 'unknown')}"
            + f" | active=`{item.get('is_active', False)}`"
            + f" | health=`{item.get('health_status', 'unknown')}`"
        )
    return "\n".join(lines)


def format_kb_stats(tenant_id: str | None, data: Dict[str, Any]) -> str:
    label = tenant_id or "all"
    return "\n".join(
        [
            f"*KB Stats: {label}*",
            f"True incidents: `{data.get('tenant_true', data.get('total_true', 0))}`",
            f"False incidents: `{data.get('tenant_false', data.get('total_false', 0))}`",
            f"Total entries: `{data.get('tenant_true', data.get('total_true', 0)) + data.get('tenant_false', data.get('total_false', 0))}`",
            f"Recent additions: `{data.get('recent_additions', 0)}`",
        ]
    )


def format_kb_entries(title: str, entries: Iterable[Dict[str, Any]], limit: int = 10) -> str:
    items = list(entries)
    if not items:
        return f"*{title}*\nNo records found."

    lines: List[str] = [f"*{title}*"]
    for entry in items[:limit]:
        label = entry.get("use_case") or entry.get("reported_as") or entry.get("kb_id") or "entry"
        description = entry.get("description") or entry.get("actual_issue") or entry.get("resolution_summary") or ""
        lines.append(f"• `{label}` | {_truncate(description, 100)}")

    shown = min(len(items), limit)
    lines.insert(1, f"Showing `{shown}` of `{len(items)}` entries")
    remaining = len(items) - shown
    if remaining > 0:
        lines.append(f"...and {remaining} more")

    return "\n".join(lines)
