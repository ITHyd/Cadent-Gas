"""Intent detection for mid-conversation topic changes, emergencies, and multi-incident input."""
import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Emergency keywords (case-insensitive fast scan) ──────────────────────────
EMERGENCY_KEYWORDS = [
    "explosion", "explode", "fire", "burning", "flames",
    "911", "999", "emergency", "unconscious", "fainted",
    "can't breathe", "cannot breathe", "choking", "suffocating",
    "evacuate", "evacuation", "collapse", "collapsed",
    "carbon monoxide", "co poisoning", "co leak",
    "someone is hurt", "someone hurt", "people injured",
    "building on fire", "house on fire",
]

# ── Cues that the user wants to report a different / new incident ────────────
NEW_INCIDENT_CUES = [
    "another issue", "another problem", "another incident",
    "new problem", "new issue", "new incident",
    "something else", "different problem", "different issue",
    "also have", "also want to report", "also need to report",
    "by the way", "one more thing", "on another note",
    "separate issue", "separate problem", "separate incident",
    "switch to", "change topic", "different topic",
    "i also noticed", "i also have", "there's also",
    "wait i also", "oh and also", "plus there's",
]

# ── Multi-incident split patterns ────────────────────────────────────────────
_MULTI_INCIDENT_PATTERNS = [
    # "I smell gas AND my meter is broken"
    re.compile(
        r"\b(?:i have|there(?:'s| is)|i notice[d]?|i see|i hear|i smell)\b.{5,80}"
        r"\b(?:and also|and|plus|but also|also)\b.{5,80}"
        r"\b(?:i have|there(?:'s| is)|i notice[d]?|i see|i hear|i smell)\b",
        re.IGNORECASE,
    ),
    # Numbered list: "1. gas smell 2. meter broken"
    re.compile(
        r"(?:^|\n)\s*[1-9][.)]\s*.{5,120}(?:\n\s*[2-9][.)]\s*.{5,120})+",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Bullet list: "- gas smell\n- meter issue"
    re.compile(
        r"(?:^|\n)\s*[-•*]\s*.{5,120}(?:\n\s*[-•*]\s*.{5,120})+",
        re.IGNORECASE | re.MULTILINE,
    ),
]


def detect_emergency(message: str) -> bool:
    """Fast keyword scan for emergency situations. O(n) on keyword list."""
    lower = message.lower()
    for kw in EMERGENCY_KEYWORDS:
        if kw in lower:
            logger.warning("Emergency keyword detected: '%s'", kw)
            return True
    return False


def detect_intent(
    message: str,
    classification: Dict[str, Any],
    current_use_case: Optional[str],
) -> Dict[str, Any]:
    """
    Determine what the user intends with this message.

    Returns
    -------
    {
        "intent": "same_topic" | "new_incident" | "multi_incident" | "small_talk" | "unclear",
        "confidence": float,
        "detail": str,               # human-readable explanation
        "new_use_case": str | None,   # only when intent == "new_incident"
        "incidents": list | None,     # only when intent == "multi_incident"
    }
    """
    classified_use_case = classification.get("use_case", "")
    classified_confidence = classification.get("confidence", 0.0)

    # ── 1. Multi-incident check ──────────────────────────────────────────
    incidents = detect_multi_incident(message)
    if len(incidents) >= 2:
        return {
            "intent": "multi_incident",
            "confidence": 0.90,
            "detail": f"Detected {len(incidents)} incidents in one message",
            "new_use_case": None,
            "incidents": incidents,
        }

    # ── 2. Explicit new-incident cue ─────────────────────────────────────
    lower = message.lower()
    for cue in NEW_INCIDENT_CUES:
        if cue in lower:
            return {
                "intent": "new_incident",
                "confidence": max(classified_confidence, 0.75),
                "detail": f"Explicit cue detected: '{cue}'",
                "new_use_case": classified_use_case if classified_use_case != current_use_case else None,
                "incidents": None,
            }

    # ── 3. Classification says different topic ───────────────────────────
    if current_use_case and classified_use_case and classified_use_case != current_use_case:
        if classified_confidence >= 0.50:
            return {
                "intent": "new_incident",
                "confidence": classified_confidence,
                "detail": (
                    f"Classifier mapped to '{classified_use_case}' "
                    f"(current: '{current_use_case}', conf={classified_confidence:.2f})"
                ),
                "new_use_case": classified_use_case,
                "incidents": None,
            }

    # ── 4. Small-talk / very low confidence (<0.30) ─────────────────────
    if classified_confidence < 0.30:
        return {
            "intent": "small_talk",
            "confidence": classified_confidence,
            "detail": "Very low classification confidence — likely off-topic",
            "new_use_case": None,
            "incidents": None,
        }

    # ── 5. Unclear / ambiguous (0.30–0.50) with different use case ────
    if (
        current_use_case
        and classified_use_case
        and classified_use_case != current_use_case
        and classified_confidence < 0.50
    ):
        return {
            "intent": "unclear",
            "confidence": classified_confidence,
            "detail": (
                f"Ambiguous: classified as '{classified_use_case}' "
                f"(current: '{current_use_case}', conf={classified_confidence:.2f}) — asking clarification"
            ),
            "new_use_case": classified_use_case,
            "incidents": None,
        }

    # ── 6. Same topic (default) ──────────────────────────────────────────
    return {
        "intent": "same_topic",
        "confidence": classified_confidence,
        "detail": "Message appears relevant to current workflow",
        "new_use_case": None,
        "incidents": None,
    }


def detect_multi_incident(message: str) -> List[str]:
    """
    Return a list of incident fragments if the message contains more than one
    distinct incident description. Returns an empty list otherwise.
    """
    for pattern in _MULTI_INCIDENT_PATTERNS:
        match = pattern.search(message)
        if match:
            # Split on the conjunction / bullet / number
            raw = match.group(0)
            parts = re.split(r"\b(?:and also|and|plus|but also|also)\b|[\n]", raw, flags=re.IGNORECASE)
            # Clean up
            cleaned = []
            for part in parts:
                part = re.sub(r"^\s*[-•*\d.)]+\s*", "", part).strip()
                if len(part) > 4:
                    cleaned.append(part)
            if len(cleaned) >= 2:
                return cleaned

    return []
