"""Demo reference IDs used by the chatbot intake flow."""

import re
from typing import Optional


DEMO_REFERENCE_IDS = [
    "REF-1001",
    "REF-1002",
    "REF-1003",
    "REF-1004",
    "REF-1005",
    "REF-1006",
    "REF-1007",
    "REF-1008",
    "REF-1009",
    "REF-1010",
    "REF-1011",
    "REF-1012",
    "REF-1013",
    "REF-1014",
    "REF-1015",
    "REF-1016",
    "REF-1017",
    "REF-1018",
    "REF-1019",
    "REF-1020",
]

_DEMO_REFERENCE_SET = set(DEMO_REFERENCE_IDS)


def normalize_demo_reference_id(value: Optional[str]) -> Optional[str]:
    """Normalize demo reference IDs to the canonical REF-#### format."""
    if value is None:
        return None

    cleaned = str(value).strip().upper()
    if not cleaned:
        return None

    match = re.fullmatch(r"(?:CRM|REF)[-_\s]?(\d{4})", cleaned)
    if not match:
        return None

    normalized = f"REF-{match.group(1)}"
    if normalized not in _DEMO_REFERENCE_SET:
        return None

    return normalized
