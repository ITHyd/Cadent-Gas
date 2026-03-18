"""Bidirectional data transformer: Incident ↔ CanonicalTicket ↔ SAP payload.

Uses the FieldMappingEngine for declarative field mapping, with SAP-specific
post-processing for OData quirks (date formats, nested structures, etc.).
"""
import logging
import re
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
from app.connectors.sap_default_mapping import (
    CANONICAL_TO_SAP_STATUS,
    SAP_PRIORITY_TO_CANONICAL,
    SAP_STATUS_TO_CANONICAL,
    USE_CASE_TO_SAP_CATEGORY,
    risk_score_to_sap_priority,
    sap_priority_to_risk_score,
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
    """Convert an internal Incident to a CanonicalTicket for outbound push to SAP."""
    status_str = incident.status.value if isinstance(incident.status, IncidentStatus) else str(incident.status)
    canonical_status = _INCIDENT_STATUS_TO_CANONICAL.get(status_str, CanonicalStatus.NEW)

    if incident.risk_score is not None:
        sap_pri = risk_score_to_sap_priority(incident.risk_score)
        canonical_priority = CanonicalPriority(SAP_PRIORITY_TO_CANONICAL.get(sap_pri, "medium"))
    else:
        canonical_priority = CanonicalPriority.MEDIUM

    category = None
    use_case = incident.classified_use_case or incident.incident_type
    if use_case:
        sap_cat = USE_CASE_TO_SAP_CATEGORY.get(use_case)
        if sap_cat:
            category = sap_cat["CategoryCode"]
        else:
            category = use_case

    resolution_code = None
    if incident.outcome:
        outcome_val = incident.outcome.value if isinstance(incident.outcome, IncidentOutcome) else str(incident.outcome)
        resolution_code = outcome_val

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


def canonical_to_sap_payload(
    ticket: CanonicalTicket,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a CanonicalTicket to a SAP OData payload."""
    payload = mapping_engine.canonical_ticket_to_external(
        ticket,
        ConnectorType.SAP,
        tenant_id=tenant_id,
    )

    # SAP-specific: override priority from risk_score
    if ticket.risk_score is not None:
        payload["ServiceOrderPriorityCode"] = risk_score_to_sap_priority(ticket.risk_score)

    # SAP-specific: category mapping from use_case
    use_case = (ticket.custom_fields or {}).get("classified_use_case")
    if use_case and use_case in USE_CASE_TO_SAP_CATEGORY:
        cat_info = USE_CASE_TO_SAP_CATEGORY[use_case]
        payload["ServiceOrderType"] = cat_info["ServiceOrderType"]
        payload["ServiceOrderCategoryCode"] = cat_info["CategoryCode"]

    # Serialize datetime objects to ISO strings for OData
    for key in ("CompletionDateTime", "RequestedServiceStartDate"):
        if key in payload and isinstance(payload[key], datetime):
            payload[key] = payload[key].isoformat()

    # SAP-specific: add platform context as LongText
    context_parts = []
    if ticket.risk_score is not None:
        context_parts.append(f"Risk Score: {ticket.risk_score:.2f}")
    if ticket.confidence_score is not None:
        context_parts.append(f"Confidence: {ticket.confidence_score:.2f}")
    outcome = (ticket.custom_fields or {}).get("outcome")
    if outcome:
        context_parts.append(f"AI Outcome: {outcome}")
    if context_parts:
        payload["_platform_notes"] = "[Gas Incident Platform] " + " | ".join(context_parts)

    return payload


def sap_response_to_canonical(
    sap_data: Dict[str, Any],
    tenant_id: Optional[str] = None,
) -> CanonicalTicket:
    """Parse a SAP OData API response into a CanonicalTicket."""
    # Unwrap OData {"d": {...}} envelope if present
    if "d" in sap_data and isinstance(sap_data["d"], dict):
        sap_data = sap_data["d"]

    ticket = mapping_engine.external_to_canonical_ticket(
        sap_data,
        ConnectorType.SAP,
        tenant_id=tenant_id,
    )

    updates: Dict[str, Any] = {}

    # Fallback: SAP ServiceOrderID as external_number for display
    if not ticket.external_number:
        order_id = sap_data.get("ServiceOrderID", "")
        if order_id:
            updates["external_number"] = f"SO-{order_id}"

    # Compatibility shim for legacy mappings:
    # ensure reporter/assignee identity fields still resolve correctly even when
    # older tenant/global mappings miss phone fields or map names into *_id.
    reporter_name = str(sap_data.get("ReportedByParty") or "").strip()
    reporter_phone = str(sap_data.get("ReporterPhone") or "").strip()
    assignee_name = str(sap_data.get("ResponsibleEmployee") or "").strip()
    assignee_phone = str(sap_data.get("EmployeePhone") or "").strip()

    if reporter_name and not ticket.reporter_name:
        updates["reporter_name"] = reporter_name
    if reporter_phone and not ticket.reporter_contact:
        updates["reporter_contact"] = reporter_phone
    if assignee_name and not ticket.assignee_name:
        updates["assignee_name"] = assignee_name
    if assignee_phone and not ticket.assignee_contact:
        updates["assignee_contact"] = assignee_phone

    # Legacy mapping bug fallback: name was mapped into reporter_id/assignee_id.
    # Promote that value back into name and clear ID so identity resolver can
    # match/provision the correct platform account by phone/name.
    if _looks_like_person_name(ticket.reporter_id):
        if not ticket.reporter_name:
            updates["reporter_name"] = ticket.reporter_id
        updates["reporter_id"] = None
    if _looks_like_person_name(ticket.assignee_id):
        if not ticket.assignee_name:
            updates["assignee_name"] = ticket.assignee_id
        updates["assignee_id"] = None

    if updates:
        ticket = ticket.model_copy(update=updates)

    return ticket


# ── Helpers ───────────────────────────────────────────────────────────────

def _build_title(incident: Incident) -> str:
    """Build a concise SAP short description from incident data."""
    parts = []
    use_case = incident.classified_use_case or incident.incident_type
    if use_case:
        parts.append(use_case.replace("_", " ").title())
    if incident.location:
        parts.append(f"at {incident.location}")
    if parts:
        return " ".join(parts)
    desc = (incident.description or "Gas incident reported")[:120]
    return desc


def _extract_external_id(incident: Incident) -> Optional[str]:
    """Extract the SAP order ID from an incident's external_ref."""
    ref = incident.external_ref
    if ref and isinstance(ref, dict):
        return ref.get("external_id")
    return None


def _looks_like_person_name(value: Optional[str]) -> bool:
    """Heuristic: detect human names accidentally mapped into *_id fields."""
    if not value or not isinstance(value, str):
        return False
    cleaned = value.strip()
    if not cleaned:
        return False

    # Known platform ID prefixes.
    if re.match(r"^(user|agent|company|super|admin|ext)_[A-Za-z0-9_-]+$", cleaned):
        return False

    # Names from SAP mock/real systems usually include spaces or punctuation.
    if " " in cleaned:
        return True
    if "." in cleaned or "-" in cleaned:
        return True
    return False


def detect_changes(
    new_canonical: CanonicalTicket,
    old_canonical: Optional[CanonicalTicket] = None,
) -> Dict[str, Any]:
    """Detect what changed and return the best-fit SyncEventType."""
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

    sap_action = (new_canonical.custom_fields or {}).get("sap_action")

    if new_canonical.status in (CanonicalStatus.CLOSED,) or sap_action == "delete":
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
        event_type = SyncEventType.TICKET_UPDATED

    return {
        "event_type": event_type,
        "changed_fields": changed,
    }
