"""ServiceNow default field mapping specification.

This is the global default template for mapping ServiceNow incident table fields
to the platform's CanonicalTicket model. Tenants can override individual entries
in Phase 2 via per-tenant mapping overrides.

Reference: ServiceNow Table API — incident table
https://docs.servicenow.com/bundle/latest/page/integrate/inbound-rest/concept/c_TableAPI.html

Source of truth: ServiceNow owns the operational ticket state.
Platform owns the AI classification, risk scoring, and customer interaction.
"""
from app.models.connector import (
    FieldMapping,
    FieldMapEntry,
    FieldMapDirection,
    FieldTransformType,
    ConnectorType,
)
from datetime import datetime
import uuid


# ── ServiceNow Status Mapping ────────────────────────────────────────────
# SN incident.state (integer) -> CanonicalStatus (string)
# Reference: https://docs.servicenow.com/bundle/latest/page/product/incident-management

SN_STATUS_TO_CANONICAL = {
    "1": "new",             # SN: New
    "2": "in_progress",     # SN: In Progress
    "3": "on_hold",         # SN: On Hold
    "6": "resolved",        # SN: Resolved
    "7": "closed",          # SN: Closed
    "8": "cancelled",       # SN: Cancelled
}

# Reverse: CanonicalStatus -> SN state integer
CANONICAL_TO_SN_STATUS = {
    "new": "1",
    "open": "2",            # Map our "open" to SN "In Progress"
    "in_progress": "2",
    "pending": "3",         # Map our "pending" to SN "On Hold"
    "on_hold": "3",
    "resolved": "6",
    "closed": "7",
    "cancelled": "8",
}


# ── ServiceNow Priority Mapping ──────────────────────────────────────────
# SN incident.priority (integer 1-5) -> CanonicalPriority

SN_PRIORITY_TO_CANONICAL = {
    "1": "critical",        # SN: 1 - Critical
    "2": "high",            # SN: 2 - High
    "3": "medium",          # SN: 3 - Moderate
    "4": "low",             # SN: 4 - Low
    "5": "planning",        # SN: 5 - Planning
}

# Reverse: CanonicalPriority -> SN priority integer
CANONICAL_PRIORITY_TO_SN = {
    "critical": "1",
    "high": "2",
    "medium": "3",
    "low": "4",
    "planning": "5",
}

# CanonicalPriority -> risk_score (0.0 - 1.0)
CANONICAL_PRIORITY_TO_RISK = {
    "critical": 0.9,
    "high": 0.7,
    "medium": 0.5,
    "low": 0.3,
    "planning": 0.1,
}

# Reverse: risk_score ranges -> SN priority
# Used when pushing platform incidents to SN
RISK_SCORE_TO_SN_PRIORITY = [
    # (min_risk, max_risk, sn_priority)
    (0.8, 1.0, "1"),    # Critical
    (0.6, 0.8, "2"),    # High
    (0.4, 0.6, "3"),    # Moderate
    (0.2, 0.4, "4"),    # Low
    (0.0, 0.2, "5"),    # Planning
]


# ── ServiceNow Category Mapping ──────────────────────────────────────────
# Platform use_case -> SN category + subcategory

USE_CASE_TO_SN_CATEGORY = {
    "co_alarm": {"category": "Carbon Monoxide", "subcategory": "CO Alarm"},
    "suspected_co_leak": {"category": "Carbon Monoxide", "subcategory": "CO Symptoms"},
    "co_orange_flames": {"category": "Carbon Monoxide", "subcategory": "CO Signs - Flames"},
    "co_sooting_scarring": {"category": "Carbon Monoxide", "subcategory": "CO Signs - Sooting"},
    "co_excessive_condensation": {"category": "Carbon Monoxide", "subcategory": "CO Signs - Condensation"},
    "co_visible_fumes": {"category": "Carbon Monoxide", "subcategory": "CO Signs - Fumes"},
    "co_blood_test": {"category": "Carbon Monoxide", "subcategory": "CO Blood Test"},
    "co_fatality": {"category": "Carbon Monoxide", "subcategory": "CO Fatality"},
    "co_smoke_alarm": {"category": "Carbon Monoxide", "subcategory": "Smoke Alarm"},
    "gas_smell": {"category": "Gas Safety", "subcategory": "Gas Leak / Smell"},
    "hissing_sound": {"category": "Gas Safety", "subcategory": "Gas Leak / Smell"},
}


# ── ServiceNow Outcome Mapping ───────────────────────────────────────────
# Platform IncidentOutcome -> SN close_code

OUTCOME_TO_SN_CLOSE_CODE = {
    "emergency_dispatch": "Emergency Response",
    "schedule_engineer": "Engineer Scheduled",
    "monitor": "Monitoring",
    "close_with_guidance": "Resolved with Guidance",
    "false_report": "False Alarm",
}


# ── Field-by-Field Mapping ───────────────────────────────────────────────
# Defines exactly how each SN field maps to CanonicalTicket fields.

SN_FIELD_MAPS = [
    # SN field               -> Canonical field          | Direction  | Transform
    FieldMapEntry(
        external_field="number",
        canonical_field="external_number",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
        is_required=True,
    ),
    FieldMapEntry(
        external_field="sys_id",
        canonical_field="external_id",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
        is_required=True,
    ),
    FieldMapEntry(
        external_field="short_description",
        canonical_field="title",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
        is_required=True,
    ),
    FieldMapEntry(
        external_field="description",
        canonical_field="description",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
        is_required=True,
    ),
    FieldMapEntry(
        external_field="state",
        canonical_field="status",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.ENUM_MAP,
        transform_config={"map": SN_STATUS_TO_CANONICAL, "reverse_map": CANONICAL_TO_SN_STATUS},
    ),
    FieldMapEntry(
        external_field="priority",
        canonical_field="priority",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.ENUM_MAP,
        transform_config={"map": SN_PRIORITY_TO_CANONICAL, "reverse_map": CANONICAL_PRIORITY_TO_SN},
    ),
    FieldMapEntry(
        external_field="category",
        canonical_field="category",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="caller_id",
        canonical_field="reporter_id",
        direction=FieldMapDirection.OUTBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="caller_id.name",
        canonical_field="reporter_name",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="assigned_to",
        canonical_field="assignee_id",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="assigned_to.name",
        canonical_field="assignee_name",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="assignment_group",
        canonical_field="assignment_group",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="location",
        canonical_field="location",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="close_code",
        canonical_field="resolution_code",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="close_notes",
        canonical_field="resolution_notes",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="sla_due",
        canonical_field="sla_due_at",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="opened_at",
        canonical_field="created_at",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="sys_updated_on",
        canonical_field="updated_at",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="resolved_at",
        canonical_field="resolved_at",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="closed_at",
        canonical_field="closed_at",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
]


def get_default_sn_mapping() -> FieldMapping:
    """Return the default global ServiceNow field mapping template.

    This is used for all tenants unless they have a per-tenant override.
    """
    return FieldMapping(
        mapping_id=f"FM_{uuid.uuid4().hex[:12].upper()}",
        tenant_id=None,  # Global default
        connector_type=ConnectorType.SERVICENOW,
        version=1,
        is_active=True,
        field_maps=SN_FIELD_MAPS,
        status_mapping=SN_STATUS_TO_CANONICAL,
        reverse_status_mapping=CANONICAL_TO_SN_STATUS,
        priority_mapping=SN_PRIORITY_TO_CANONICAL,
        priority_to_risk=CANONICAL_PRIORITY_TO_RISK,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def risk_score_to_sn_priority(risk_score: float) -> str:
    """Convert a platform risk score (0.0-1.0) to a ServiceNow priority (1-5)."""
    for min_risk, max_risk, sn_priority in RISK_SCORE_TO_SN_PRIORITY:
        if min_risk <= risk_score <= max_risk:
            return sn_priority
    return "3"  # Default to moderate


def sn_priority_to_risk_score(sn_priority: str) -> float:
    """Convert a ServiceNow priority (1-5) to a platform risk score (0.0-1.0)."""
    canonical = SN_PRIORITY_TO_CANONICAL.get(str(sn_priority), "medium")
    return CANONICAL_PRIORITY_TO_RISK.get(canonical, 0.5)
