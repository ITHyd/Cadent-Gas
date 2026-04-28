from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import List

from .config import settings
from .mistral_client import mistral_client


ALLOWED_COMMANDS = {
    "help",
    "incident",
    "company-stats",
    "pending-incidents",
    "agent-jobs",
    "my-incidents",
    "available-agents",
    "all-agents",
    "kb-stats",
    "kb-true",
    "kb-false",
    "kb-recent",
}


@dataclass
class ParsedIntent:
    matched: bool
    command: str | None
    args: List[str]
    confidence: float
    reason: str = ""


async def parse_natural_language(user_text: str) -> ParsedIntent | None:
    if not mistral_client.enabled:
        return None

    try:
        parsed = await asyncio.wait_for(
            mistral_client.parse_intent(user_text),
            timeout=settings.ai_parse_timeout_seconds,
        )
    except Exception:
        return None

    matched = bool(parsed.get("matched"))
    command = parsed.get("command")
    args = [str(arg) for arg in (parsed.get("args") or [])]
    confidence = float(parsed.get("confidence", 0.0) or 0.0)
    reason = str(parsed.get("reason", "") or "")

    if command and command not in ALLOWED_COMMANDS:
        return ParsedIntent(False, None, [], 0.0, "Unsupported command returned by parser")

    return ParsedIntent(matched, command, args, confidence, reason)


def _normalize_incident_id(text: str) -> str | None:
    digits_only = re.fullmatch(r"\s*(\d+)\s*", text or "")
    if digits_only:
        return f"INC-{digits_only.group(1)}"
    match = re.search(r"\bINC[-_\s]?(\d+)\b", text or "", re.IGNORECASE)
    if not match:
        return None
    return f"INC-{match.group(1)}"


def _normalize_agent_id(text: str) -> str | None:
    digits_only = re.fullmatch(r"\s*(\d+)\s*", text or "")
    if digits_only:
        return f"agent_{digits_only.group(1).zfill(3)}"
    match = re.search(r"\bagent[-_\s]?(\d+)\b", text or "", re.IGNORECASE)
    if not match:
        return None
    return f"agent_{match.group(1).zfill(3)}"


def _normalize_user_id(text: str) -> str | None:
    digits_only = re.fullmatch(r"\s*(\d+)\s*", text or "")
    if digits_only:
        return f"user_{digits_only.group(1).zfill(3)}"
    match = re.search(r"\buser[-_\s]?(\d+)\b", text or "", re.IGNORECASE)
    if not match:
        return None
    return f"user_{match.group(1).zfill(3)}"


async def resolve_modal_argument(command: str, raw_text: str) -> str | None:
    text = (raw_text or "").strip()
    if not text:
        return None

    direct_resolvers = {
        "incident": _normalize_incident_id,
        "agent-jobs": _normalize_agent_id,
        "my-incidents": _normalize_user_id,
    }

    resolver = direct_resolvers.get(command)
    if resolver:
        direct_match = resolver(text)
        if direct_match:
            return direct_match

    parsed = await parse_natural_language(text)
    if not parsed or not parsed.matched or parsed.command != command or not parsed.args:
        return None

    candidate = str(parsed.args[0]).strip()
    if not candidate:
        return None

    if command == "incident":
        return _normalize_incident_id(candidate) or candidate
    if command == "agent-jobs":
        return _normalize_agent_id(candidate) or candidate
    if command == "my-incidents":
        return _normalize_user_id(candidate) or candidate

    return candidate
