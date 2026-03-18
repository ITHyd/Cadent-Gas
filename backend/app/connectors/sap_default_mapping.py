"""SAP default field mapping specification.

Global default template for mapping SAP Service Cloud / S/4HANA service order
fields to the platform's CanonicalTicket model.

Reference: SAP Service Cloud OData API — ServiceOrder entity
https://api.sap.com/api/API_SERVICE_ORDER_SRV

Source of truth: SAP owns the operational ticket state.
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


# ── SAP Status Mapping ────────────────────────────────────────────────────
# SAP Service Order status codes -> CanonicalStatus
# Reference: SAP Service Cloud status profile

SAP_STATUS_TO_CANONICAL = {
    "E0001": "new",             # SAP: Open
    "E0002": "in_progress",     # SAP: In Process
    "E0003": "on_hold",         # SAP: On Hold / Waiting
    "E0004": "resolved",        # SAP: Completed
    "E0005": "closed",          # SAP: Closed
    "E0006": "cancelled",       # SAP: Cancelled
}

# Reverse: CanonicalStatus -> SAP status code
CANONICAL_TO_SAP_STATUS = {
    "new": "E0001",
    "open": "E0002",
    "in_progress": "E0002",
    "pending": "E0003",
    "on_hold": "E0003",
    "resolved": "E0004",
    "closed": "E0005",
    "cancelled": "E0006",
}


# ── SAP Priority Mapping ─────────────────────────────────────────────────
# SAP uses 1-4 priority: 1=Very High, 2=High, 3=Medium, 4=Low

SAP_PRIORITY_TO_CANONICAL = {
    "1": "critical",     # SAP: Very High
    "2": "high",         # SAP: High
    "3": "medium",       # SAP: Medium
    "4": "low",          # SAP: Low
}

CANONICAL_PRIORITY_TO_SAP = {
    "critical": "1",
    "high": "2",
    "medium": "3",
    "low": "4",
    "planning": "4",     # SAP has no planning priority, map to low
}

# CanonicalPriority -> risk_score (0.0 - 1.0)
CANONICAL_PRIORITY_TO_RISK = {
    "critical": 0.9,
    "high": 0.7,
    "medium": 0.5,
    "low": 0.3,
    "planning": 0.1,
}

# Reverse: risk_score ranges -> SAP priority
RISK_SCORE_TO_SAP_PRIORITY = [
    # (min_risk, max_risk, sap_priority)
    (0.8, 1.0, "1"),    # Very High
    (0.6, 0.8, "2"),    # High
    (0.4, 0.6, "3"),    # Medium
    (0.0, 0.4, "4"),    # Low
]


# ── SAP Category Mapping ─────────────────────────────────────────────────
# Platform use_case -> SAP service order category

USE_CASE_TO_SAP_CATEGORY = {
    "co_alarm": {"ServiceOrderType": "GS01", "CategoryCode": "CO_ALARM"},
    "suspected_co_leak": {"ServiceOrderType": "GS01", "CategoryCode": "CO_LEAK"},
    "co_orange_flames": {"ServiceOrderType": "GS01", "CategoryCode": "CO_FLAMES"},
    "co_sooting_scarring": {"ServiceOrderType": "GS01", "CategoryCode": "CO_SOOTING"},
    "co_excessive_condensation": {"ServiceOrderType": "GS01", "CategoryCode": "CO_CONDENSATION"},
    "co_visible_fumes": {"ServiceOrderType": "GS01", "CategoryCode": "CO_FUMES"},
    "co_blood_test": {"ServiceOrderType": "GS01", "CategoryCode": "CO_BLOOD_TEST"},
    "co_fatality": {"ServiceOrderType": "GS01", "CategoryCode": "CO_FATALITY"},
    "co_smoke_alarm": {"ServiceOrderType": "GS01", "CategoryCode": "SMOKE_ALARM"},
    "gas_smell": {"ServiceOrderType": "GS01", "CategoryCode": "GAS_SAFETY"},
    "hissing_sound": {"ServiceOrderType": "GS01", "CategoryCode": "GAS_LEAK"},
}


# ── Field-by-Field Mapping ───────────────────────────────────────────────

SAP_FIELD_MAPS = [
    FieldMapEntry(
        external_field="ServiceOrderID",
        canonical_field="external_id",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
        is_required=True,
    ),
    FieldMapEntry(
        external_field="ServiceOrderDescription",
        canonical_field="title",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
        is_required=True,
    ),
    FieldMapEntry(
        external_field="LongText",
        canonical_field="description",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="ServiceOrderStatusCode",
        canonical_field="status",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.ENUM_MAP,
        transform_config={
            "map": SAP_STATUS_TO_CANONICAL,
            "reverse_map": CANONICAL_TO_SAP_STATUS,
        },
    ),
    FieldMapEntry(
        external_field="ServiceOrderPriorityCode",
        canonical_field="priority",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.ENUM_MAP,
        transform_config={
            "map": SAP_PRIORITY_TO_CANONICAL,
            "reverse_map": CANONICAL_PRIORITY_TO_SAP,
        },
    ),
    FieldMapEntry(
        external_field="ServiceOrderCategoryCode",
        canonical_field="category",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="ReportedByParty",
        canonical_field="reporter_name",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="ReporterPhone",
        canonical_field="reporter_contact",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="ResponsibleEmployee",
        canonical_field="assignee_name",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="EmployeePhone",
        canonical_field="assignee_contact",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="ServiceTeam",
        canonical_field="assignment_group",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="InstallationPointAddress",
        canonical_field="location",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="ResolutionCode",
        canonical_field="resolution_code",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="ResolutionDescription",
        canonical_field="resolution_notes",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="RequestedServiceStartDate",
        canonical_field="sla_due_at",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="CreatedDateTime",
        canonical_field="created_at",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="LastChangedDateTime",
        canonical_field="updated_at",
        direction=FieldMapDirection.INBOUND,
        transform_type=FieldTransformType.DIRECT,
    ),
    FieldMapEntry(
        external_field="CompletionDateTime",
        canonical_field="resolved_at",
        direction=FieldMapDirection.BOTH,
        transform_type=FieldTransformType.DIRECT,
    ),
]


def get_default_sap_mapping() -> FieldMapping:
    """Return the default global SAP field mapping template."""
    return FieldMapping(
        mapping_id=f"FM_{uuid.uuid4().hex[:12].upper()}",
        tenant_id=None,
        connector_type=ConnectorType.SAP,
        version=1,
        is_active=True,
        field_maps=SAP_FIELD_MAPS,
        status_mapping=SAP_STATUS_TO_CANONICAL,
        reverse_status_mapping=CANONICAL_TO_SAP_STATUS,
        priority_mapping=SAP_PRIORITY_TO_CANONICAL,
        priority_to_risk=CANONICAL_PRIORITY_TO_RISK,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def risk_score_to_sap_priority(risk_score: float) -> str:
    """Convert a platform risk score (0.0-1.0) to a SAP priority (1-4)."""
    for min_risk, max_risk, sap_priority in RISK_SCORE_TO_SAP_PRIORITY:
        if min_risk <= risk_score <= max_risk:
            return sap_priority
    return "3"  # Default to medium


def sap_priority_to_risk_score(sap_priority: str) -> float:
    """Convert a SAP priority (1-4) to a platform risk score (0.0-1.0)."""
    canonical = SAP_PRIORITY_TO_CANONICAL.get(str(sap_priority), "medium")
    return CANONICAL_PRIORITY_TO_RISK.get(canonical, 0.5)
