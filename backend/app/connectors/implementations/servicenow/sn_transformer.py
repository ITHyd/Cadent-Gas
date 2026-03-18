"""Bidirectional data transformer: Incident ↔ CanonicalTicket ↔ SN payload.

Uses the FieldMappingEngine for declarative field mapping, with SN-specific
post-processing for connector quirks (work_notes, use_case categories, etc.).

Data paths:
- Internal Incident model  →  CanonicalTicket          (incident_to_canonical — hardcoded, no engine)
- CanonicalTicket          →  ServiceNow API payload    (canonical_to_sn_payload — engine + post-processing)
- ServiceNow API response  →  CanonicalTicket           (sn_response_to_canonical — engine + fallbacks)
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.connector import (
    CanonicalPriority,
    CanonicalStatus,
    CanonicalTicket,
    ConnectorType,
    SyncEventType,
)
from app.models.incident import Incident, IncidentOutcome, IncidentStatus
from app.connectors.field_mapping_engine import mapping_engine
from app.connectors.sn_default_mapping import (
    CANONICAL_TO_SN_STATUS,
    OUTCOME_TO_SN_CLOSE_CODE,
    SN_PRIORITY_TO_CANONICAL,
    SN_STATUS_TO_CANONICAL,
    USE_CASE_TO_SN_CATEGORY,
    risk_score_to_sn_priority,
    sn_priority_to_risk_score,
)

logger = logging.getLogger(__name__)


# ── Incident Status → Canonical Status mapping ───────────────────────────
_INCIDENT_STATUS_TO_CANONICAL: Dict[str, CanonicalStatus] = {
    "new": CanonicalStatus.NEW,
    "submitted": CanonicalStatus.NEW,
    "classifying": CanonicalStatus.IN_PROGRESS,
    "in_progress": CanonicalStatus.IN_PROGRESS,
    "paused": CanonicalStatus.ON_HOLD,
    "waiting_input": CanonicalStatus.PENDING,
    "analyzing": CanonicalStatus.IN_PROGRESS,
    "pending_company_action": CanonicalStatus.PENDING,
    "dispatched": CanonicalStatus.IN_PROGRESS,
    "resolved": CanonicalStatus.RESOLVED,
    "completed": CanonicalStatus.CLOSED,
    "emergency": CanonicalStatus.IN_PROGRESS,
    "false_report": CanonicalStatus.CANCELLED,
    "closed": CanonicalStatus.CLOSED,
}


def incident_to_canonical(incident: Incident) -> CanonicalTicket:
    """Convert an internal Incident to a CanonicalTicket for outbound push."""
    # Map status
    status_str = incident.status.value if isinstance(incident.status, IncidentStatus) else str(incident.status)
    canonical_status = _INCIDENT_STATUS_TO_CANONICAL.get(status_str, CanonicalStatus.NEW)

    # Map priority from risk_score
    if incident.risk_score is not None:
        sn_pri = risk_score_to_sn_priority(incident.risk_score)
        canonical_priority = CanonicalPriority(SN_PRIORITY_TO_CANONICAL.get(sn_pri, "medium"))
    else:
        canonical_priority = CanonicalPriority.MEDIUM

    # Map category from classified_use_case
    category = None
    use_case = incident.classified_use_case or incident.incident_type
    if use_case:
        sn_cat = USE_CASE_TO_SN_CATEGORY.get(use_case)
        if sn_cat:
            category = f"{sn_cat['category']} - {sn_cat['subcategory']}"
        else:
            category = use_case

    # Map resolution code from outcome
    resolution_code = None
    if incident.outcome:
        outcome_val = incident.outcome.value if isinstance(incident.outcome, IncidentOutcome) else str(incident.outcome)
        resolution_code = OUTCOME_TO_SN_CLOSE_CODE.get(outcome_val)

    # Build title
    title = _build_title(incident)

    return CanonicalTicket(
        ticket_id=incident.incident_id,
        external_id=_extract_external_id(incident),
        source_system="platform",
        title=title,
        description=incident.description or "",
        status=canonical_status,
        priority=canonical_priority,
        category=category,
        reporter_id=incident.user_id,
        reporter_name=incident.user_name,
        reporter_contact=incident.user_phone,
        assignee_id=incident.assigned_agent_id,
        location=incident.location or incident.user_address,
        geo_location=incident.geo_location,
        resolution_code=resolution_code,
        resolution_notes=incident.resolution_notes,
        sla_due_at=incident.estimated_resolution_at,
        risk_score=incident.risk_score,
        confidence_score=incident.confidence_score,
        custom_fields={
            "tenant_id": incident.tenant_id,
            "incident_type": incident.incident_type,
            "classified_use_case": incident.classified_use_case,
            "outcome": incident.outcome.value if incident.outcome else None,
        },
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        resolved_at=incident.resolved_at,
    )


def canonical_to_sn_payload(ticket: CanonicalTicket) -> Dict[str, Any]:
    """Convert a CanonicalTicket to a ServiceNow incident table JSON payload.

    Uses the FieldMappingEngine for base field mapping, then applies SN-specific
    post-processing (risk_score priority, use_case categories, work_notes).
    """
    # Engine handles: title->short_description, description, state, priority,
    # category, assigned_to, assignment_group, location, close_code, close_notes, resolved_at
    payload = mapping_engine.canonical_ticket_to_external(
        ticket, ConnectorType.SERVICENOW
    )

    # SN-specific: override priority from risk_score (more precise than enum map)
    if ticket.risk_score is not None:
        payload["priority"] = risk_score_to_sn_priority(ticket.risk_score)

    # SN-specific: caller_id from reporter_name (SN uses name, not ID, for caller)
    if ticket.reporter_name:
        payload["caller_id"] = ticket.reporter_name

    # SN-specific: category/subcategory from classified_use_case
    use_case = (ticket.custom_fields or {}).get("classified_use_case")
    if use_case and use_case in USE_CASE_TO_SN_CATEGORY:
        cat_info = USE_CASE_TO_SN_CATEGORY[use_case]
        payload["category"] = cat_info["category"]
        payload["subcategory"] = cat_info["subcategory"]

    # Serialize datetime objects to ISO strings for the SN API
    for key in ("resolved_at", "closed_at"):
        if key in payload and isinstance(payload[key], datetime):
            payload[key] = payload[key].isoformat()

    # SN-specific: work_notes carries platform AI context
    context_parts = []
    if ticket.risk_score is not None:
        context_parts.append(f"Risk Score: {ticket.risk_score:.2f}")
    if ticket.confidence_score is not None:
        context_parts.append(f"Confidence: {ticket.confidence_score:.2f}")
    outcome = (ticket.custom_fields or {}).get("outcome")
    if outcome:
        context_parts.append(f"AI Outcome: {outcome}")
    if context_parts:
        payload["work_notes"] = "[Gas Incident Platform] " + " | ".join(context_parts)

    return payload


def sn_response_to_canonical(sn_data: Dict[str, Any]) -> CanonicalTicket:
    """Parse a ServiceNow Table API response into a CanonicalTicket (for pull/inbound).

    Uses the FieldMappingEngine for base field mapping, then applies SN-specific
    fallbacks (caller_id as reporter_name, sys_created_on as created_at).
    """
    # Engine handles: field mapping, display_value resolution, enum mapping,
    # datetime parsing, and risk_score derivation from priority
    ticket = mapping_engine.external_to_canonical_ticket(
        sn_data, ConnectorType.SERVICENOW
    )

    # SN-specific fallbacks
    updates: Dict[str, Any] = {}

    # Fallback: use caller_id string as reporter_name when caller_id.name is unavailable
    # (mock data and basic SN configs return caller_id as a plain string name)
    if not ticket.reporter_name:
        name = _resolve_sn_value(sn_data.get("caller_id"))
        if name:
            updates["reporter_name"] = name

    # Fallback: use sys_created_on when opened_at is missing
    if not ticket.created_at:
        raw = _resolve_sn_value(sn_data.get("sys_created_on"))
        if raw:
            try:
                updates["created_at"] = datetime.fromisoformat(
                    raw.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

    if updates:
        ticket = ticket.model_copy(update=updates)

    return ticket


# ── Helpers ───────────────────────────────────────────────────────────────

def _resolve_sn_value(val: Any) -> str:
    """Resolve a SN field value (could be str or display_value dict) to a plain string."""
    if val is None:
        return ""
    if isinstance(val, dict):
        return val.get("display_value") or val.get("value") or ""
    return str(val) if val else ""


def _build_title(incident: Incident) -> str:
    """Build a concise SN short_description from incident data."""
    parts = []
    use_case = incident.classified_use_case or incident.incident_type
    if use_case:
        parts.append(use_case.replace("_", " ").title())
    if incident.location:
        parts.append(f"at {incident.location}")
    if parts:
        return " ".join(parts)
    # Fallback: first 120 chars of description
    desc = (incident.description or "Gas incident reported")[:120]
    return desc


def _extract_external_id(incident: Incident) -> Optional[str]:
    """Extract the SN sys_id from an incident's external_ref if it exists."""
    ref = incident.external_ref
    if ref and isinstance(ref, dict):
        return ref.get("external_id")
    return None


def detect_changes(
    new_canonical: CanonicalTicket,
    old_canonical: Optional[CanonicalTicket] = None,
) -> Dict[str, Any]:
    """Detect what changed and return the best-fit SyncEventType.

    If *old_canonical* is ``None`` the ticket is treated as newly created.

    Returns::

        {
            "event_type": SyncEventType,
            "changed_fields": ["status", "assignee_id", ...],
        }
    """
    if old_canonical is None:
        return {
            "event_type": SyncEventType.TICKET_CREATED,
            "changed_fields": [],
        }

    changed: List[str] = []

    if new_canonical.status != old_canonical.status:
        changed.append("status")
    if new_canonical.assignee_id != old_canonical.assignee_id:
        changed.append("assignee_id")
    if new_canonical.priority != old_canonical.priority:
        changed.append("priority")
    if new_canonical.resolution_notes != old_canonical.resolution_notes:
        changed.append("resolution_notes")
    if new_canonical.resolution_code != old_canonical.resolution_code:
        changed.append("resolution_code")
    if new_canonical.resolved_at != old_canonical.resolved_at:
        changed.append("resolved_at")
    if new_canonical.closed_at != old_canonical.closed_at:
        changed.append("closed_at")
    if new_canonical.title != old_canonical.title:
        changed.append("title")
    if new_canonical.description != old_canonical.description:
        changed.append("description")

    # Also check sn_action from custom_fields (set by handle_webhook)
    sn_action = (new_canonical.custom_fields or {}).get("sn_action")

    # Determine best-fit event type
    if new_canonical.status in (CanonicalStatus.CLOSED,) or sn_action == "delete":
        event_type = SyncEventType.TICKET_CLOSED
    elif new_canonical.status == CanonicalStatus.RESOLVED or "resolved_at" in changed:
        event_type = SyncEventType.TICKET_RESOLVED
    elif "status" in changed:
        event_type = SyncEventType.STATUS_CHANGED
    elif "assignee_id" in changed:
        event_type = SyncEventType.ASSIGNEE_CHANGED
    elif changed:
        event_type = SyncEventType.TICKET_UPDATED
    else:
        # No visible changes — still treat as a generic update
        event_type = SyncEventType.TICKET_UPDATED

    return {
        "event_type": event_type,
        "changed_fields": changed,
    }
