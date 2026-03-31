"""Demo reference IDs used by the chatbot intake flow."""

import re
from typing import Optional


# Generate reference IDs from REF-1000 to REF-9999 (8,999 total IDs)
DEMO_REFERENCE_IDS = [f"REF-{i:04d}" for i in range(1000, 10000)]

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
