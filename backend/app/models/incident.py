"""Incident data models"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    pass


class IncidentStatus(str, Enum):
    NEW = "new"
    SUBMITTED = "submitted"
    CLASSIFYING = "classifying"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"                     # User disconnected mid-workflow (resumable)
    WAITING_INPUT = "waiting_input"
    ANALYZING = "analyzing"
    PENDING_COMPANY_ACTION = "pending_company_action"
    DISPATCHED = "dispatched"
    RESOLVED = "resolved"
    COMPLETED = "completed"
    EMERGENCY = "emergency"
    FALSE_REPORT = "false_report"
    CLOSED = "closed"


class AgentStatus(str, Enum):
    """Field agent status for assigned incidents"""
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    ON_SITE = "on_site"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Agent(BaseModel):
    """Professional field agent / engineer details"""
    agent_id: str
    full_name: str
    phone: str
    email: Optional[str] = None
    specialization: str
    experience_years: int = 0
    rating: float = 4.5
    total_jobs_completed: int = 0
    certifications: List[str] = []
    is_available: bool = True
    location: Optional[str] = None          # Human-readable service area
    location_area: Optional[str] = None     # urban/suburban/rural for SLA
    geo_coordinates: Optional[Dict[str, float]] = None  # {"lat": float, "lng": float}
    vehicle_type: Optional[str] = None
    vehicle_registration: Optional[str] = None

    class Config:
        from_attributes = True


class IncidentOutcome(str, Enum):
    EMERGENCY_DISPATCH = "emergency_dispatch"
    SCHEDULE_ENGINEER = "schedule_engineer"
    MONITOR = "monitor"
    CLOSE_WITH_GUIDANCE = "close_with_guidance"
    FALSE_REPORT = "false_report"


class MediaType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    SENSOR_DATA = "sensor_data"


class IncidentMedia(BaseModel):
    media_id: str
    media_type: MediaType
    file_path: str
    uploaded_at: datetime
    metadata: Optional[Dict[str, Any]] = None


class IncidentCreate(BaseModel):
    tenant_id: str
    user_id: str
    description: str
    location: Optional[str] = None
    media: Optional[List[IncidentMedia]] = None
    sensor_data: Optional[Dict[str, Any]] = None


class Incident(BaseModel):
    incident_id: str
    tenant_id: str
    user_id: str
    
    # User details
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_address: Optional[str] = None
    reference_id: Optional[str] = None
    reported_by_staff_id: Optional[str] = None  # Admin who reported on behalf of customer

    # Incident details
    description: str
    incident_type: Optional[str] = None
    location: Optional[str] = None
    geo_location: Optional[Dict[str, float]] = None  # {"lat": float, "lng": float}
    user_geo_location: Optional[Dict[str, float]] = None  # {"lat": float, "lng": float}
    classified_use_case: Optional[str] = None
    
    # Status and outcome
    status: IncidentStatus
    outcome: Optional[IncidentOutcome] = None
    
    # Risk and confidence
    risk_score: Optional[float] = None
    confidence_score: Optional[float] = None
    kb_similarity_score: Optional[float] = None
    kb_match_type: Optional[str] = None  # "true" | "false" | "unknown"
    kb_validation_details: Optional[Dict[str, Any]] = None  # Full KB verification result
    incident_pattern: Optional[Dict[str, Any]] = None  # Normalized workflow-answer pattern for KB matching
    
    # Workflow
    workflow_execution_id: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None  # Extracted structured variables
    workflow_snapshot: Optional[Dict[str, Any]] = None  # Saved state for resume across sessions
    conversation_history: Optional[List[Dict[str, Any]]] = None  # Chat messages [{role, content, timestamp}]
    
    # Media and sensors
    media: List[IncidentMedia] = []
    sensor_data: Optional[Dict[str, Any]] = None
    
    # Company actions
    assigned_agent_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    agent_status: Optional[str] = None  # ASSIGNED | EN_ROUTE | ON_SITE | IN_PROGRESS | COMPLETED
    estimated_arrival_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None
    items_used: Optional[List[str]] = None  # Items/equipment used by field agent
    resolution_checklist: Optional[Dict[str, Any]] = None
    agent_live_location: Optional[Dict[str, Any]] = None
    agent_location_history: Optional[List[Dict[str, Any]]] = None
    field_activity: Optional[List[Dict[str, Any]]] = None
    assistance_requests: Optional[List[Dict[str, Any]]] = None
    item_requests: Optional[List[Dict[str, Any]]] = None
    customer_notifications: Optional[List[Dict[str, Any]]] = None  # [{notification_id, type, title, message, severity, created_at, read}]
    backup_agents: Optional[List[Dict[str, Any]]] = None  # [{agent_id, request_id, role, status, assigned_at}]
    resolution_media: Optional[List[Dict[str, Any]]] = None  # [{media_id, filename, file_path, content_type, size_bytes, uploaded_at}]

    # SLA
    sla_hours: Optional[float] = None
    estimated_resolution_at: Optional[datetime] = None

    # Status timeline
    status_history: Optional[List[Dict[str, Any]]] = None  # [{status, timestamp, message}]

    # ── External System Integration ──────────────────────────────────────
    # Lightweight reference to the linked external ticket (SN, SAP, Jira).
    # Full link details live in the external_ticket_links collection.
    external_ref: Optional[Dict[str, Any]] = None
    # Structure (matches IncidentExternalRef):
    # {
    #     "connector_type": "servicenow",
    #     "external_id": "sys_id_abc123",
    #     "external_number": "INC0010001",
    #     "external_url": "https://dev12345.service-now.com/incident.do?sys_id=abc123",
    #     "sync_status": "linked",
    #     "last_synced_at": "2026-02-24T10:30:00Z",
    # }

    # Optimistic concurrency — incremented on every update to detect conflicts
    # during bidirectional sync. If SN and platform both update the same incident,
    # the higher version wins (last-write-wins with audit trail).
    sync_version: int = 0

    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True
