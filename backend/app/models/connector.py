"""Connector data models — canonical ticket, external links, sync events, config, and field mappings.

These models define the schema contract between the platform's internal incident system
and any external ticketing system (ServiceNow, SAP, Jira, etc.).

Data flow:
    Outbound: Incident -> CanonicalTicket -> ExternalTicket (SN/SAP/Jira format)
    Inbound:  ExternalTicket -> CanonicalTicket -> update Incident
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ── Canonical Enums ──────────────────────────────────────────────────────
# Normalized enums that every connector maps to/from.

class CanonicalStatus(str, Enum):
    """Normalized ticket status across all external systems."""
    NEW = "new"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    ON_HOLD = "on_hold"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class CanonicalPriority(str, Enum):
    """Normalized ticket priority across all external systems."""
    CRITICAL = "critical"       # P1 / SN priority 1
    HIGH = "high"               # P2 / SN priority 2
    MEDIUM = "medium"           # P3 / SN priority 3
    LOW = "low"                 # P4 / SN priority 4
    PLANNING = "planning"       # P5 / SN priority 5


class SyncStatus(str, Enum):
    """Status of the link between internal incident and external ticket."""
    LINKED = "linked"           # Successfully linked and synced
    PENDING = "pending"         # Waiting to be pushed/pulled
    SYNCING = "syncing"         # Sync in progress
    ERROR = "error"             # Last sync attempt failed
    UNLINKED = "unlinked"       # Link removed / disconnected


class SyncDirection(str, Enum):
    """Direction of a sync operation."""
    INBOUND = "inbound"         # External -> Platform
    OUTBOUND = "outbound"       # Platform -> External


class SyncEventType(str, Enum):
    """Types of sync events flowing through the event bus."""
    TICKET_CREATED = "ticket_created"
    TICKET_UPDATED = "ticket_updated"
    STATUS_CHANGED = "status_changed"
    ASSIGNEE_CHANGED = "assignee_changed"
    COMMENT_ADDED = "comment_added"
    ATTACHMENT_ADDED = "attachment_added"
    SLA_UPDATED = "sla_updated"
    TICKET_RESOLVED = "ticket_resolved"
    TICKET_CLOSED = "ticket_closed"


class SyncEventStatus(str, Enum):
    """Processing status of a sync event."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"     # Exhausted retries, needs manual review


class ConnectorType(str, Enum):
    """Supported external system types."""
    SERVICENOW = "servicenow"
    SAP = "sap"
    JIRA = "jira"
    AWS = "aws"
    ZENDESK = "zendesk"


class AuthMethod(str, Enum):
    """Authentication methods for connectors."""
    OAUTH2 = "oauth2"
    BASIC = "basic"
    API_KEY = "api_key"
    IAM = "iam"


class HealthStatus(str, Enum):
    """Connector health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


# ── Canonical Ticket Model ───────────────────────────────────────────────
# The universal ticket format that sits between internal incidents and
# external systems. Every connector translates to/from this model.

class TicketComment(BaseModel):
    """A single comment on a ticket (synced bidirectionally)."""
    comment_id: str
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    body: str
    is_public: bool = True              # Public comments only in v1
    source_system: str = "platform"     # Where the comment originated
    external_comment_id: Optional[str] = None   # ID in external system
    created_at: datetime
    updated_at: Optional[datetime] = None


class TicketAttachment(BaseModel):
    """A file attachment on a ticket (synced bidirectionally, <=5MB)."""
    attachment_id: str
    filename: str
    content_type: str                   # MIME type
    size_bytes: int
    source_system: str = "platform"
    external_attachment_id: Optional[str] = None
    file_path: Optional[str] = None     # Local storage path
    external_url: Optional[str] = None  # URL in external system
    uploaded_by: Optional[str] = None
    uploaded_at: datetime


class CanonicalTicket(BaseModel):
    """Universal ticket model — the bridge between internal incidents and external systems.

    Outbound: Incident fields are mapped into this model, then the connector
              transforms it into the external system's format.
    Inbound:  External webhook/pull data is parsed into this model, then
              applied to the internal incident.
    """
    # Identity
    ticket_id: str                              # Internal canonical ID (usually = incident_id)
    external_id: Optional[str] = None           # External system ID (SN sys_id, Jira issue id)
    external_number: Optional[str] = None       # Human-readable (INC0010001, PROJ-123)
    source_system: str = "platform"             # Origin: "platform", "servicenow", "sap", etc.

    # Core fields (every ticketing system has these)
    title: str                                  # Short description / summary
    description: str                            # Full description / long text
    status: CanonicalStatus = CanonicalStatus.NEW
    priority: CanonicalPriority = CanonicalPriority.MEDIUM
    category: Optional[str] = None              # Ticket category / use case type

    # People
    reporter_id: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_contact: Optional[str] = None      # Phone or email
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_contact: Optional[str] = None      # Phone or email of assignee
    assignment_group: Optional[str] = None      # Team / group

    # Location
    location: Optional[str] = None
    geo_location: Optional[Dict[str, float]] = None     # {"lat": float, "lng": float}

    # Resolution
    resolution_code: Optional[str] = None
    resolution_notes: Optional[str] = None

    # SLA
    sla_due_at: Optional[datetime] = None

    # Risk (platform-specific, carried through for context)
    risk_score: Optional[float] = None          # 0.0 - 1.0
    confidence_score: Optional[float] = None

    # Comments & Attachments
    comments: List[TicketComment] = []
    attachments: List[TicketAttachment] = []

    # Custom fields (catch-all for system-specific data that doesn't map to standard fields)
    custom_fields: Dict[str, Any] = {}

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── External Link Model ──────────────────────────────────────────────────
# Tracks the 1:1 mapping between an internal incident and its external ticket.
# One incident can be linked to one ticket per connector type.

class ExternalTicketLink(BaseModel):
    """Bidirectional link between an internal incident and an external ticket.

    MongoDB collection: external_ticket_links
    Unique constraint: (incident_id, connector_type) — one link per system per incident.
    """
    link_id: str                                # Unique link identifier
    incident_id: str                            # Internal incident ID (INC_XXXX)
    tenant_id: str                              # Tenant this belongs to

    # External system reference
    connector_type: ConnectorType               # servicenow, sap, jira, etc.
    external_id: str                            # External system's internal ID (SN sys_id)
    external_number: str                        # Human-readable ticket number (INC0010001)
    external_url: Optional[str] = None          # Deep link to ticket in external UI

    # Sync state
    sync_status: SyncStatus = SyncStatus.PENDING
    last_synced_at: Optional[datetime] = None
    last_sync_direction: Optional[SyncDirection] = None
    last_sync_event_id: Optional[str] = None    # Reference to the last sync event

    # Optimistic concurrency control
    version: int = 1                            # Incremented on every sync

    # Error tracking
    last_error: Optional[str] = None
    consecutive_errors: int = 0

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Sync Event Schema ────────────────────────────────────────────────────
# Every data movement between systems is recorded as a sync event.
# The event bus processes these: webhook → event → transform → apply → log.

class SyncEvent(BaseModel):
    """A single sync event flowing through the event bus.

    MongoDB collection: sync_events
    Index: (tenant_id, created_at), (idempotency_key) unique
    """
    event_id: str                               # Unique event identifier
    tenant_id: str
    connector_type: ConnectorType

    # What this event is about
    incident_id: Optional[str] = None           # Internal incident (if known)
    external_id: Optional[str] = None           # External ticket ID (if known)
    event_type: SyncEventType
    direction: SyncDirection
    source: str                                 # "webhook", "api_push", "manual_sync", "scheduled"

    # Payload
    payload: Dict[str, Any] = {}                # The actual data being synced
    transformed_payload: Optional[Dict[str, Any]] = None    # After mapping transformation

    # Processing state
    status: SyncEventStatus = SyncEventStatus.PENDING
    retry_count: int = 0
    max_retries: int = 5
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    # Idempotency — prevents duplicate processing
    idempotency_key: str                        # Hash of (source + external_id + event_type + timestamp)

    # Timestamps
    created_at: datetime
    processed_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Connector Configuration ──────────────────────────────────────────────
# Per-tenant connector setup. Stores which system they connect to and how.

class ConnectorConfig(BaseModel):
    """Configuration for a tenant's external system connection.

    MongoDB collection: connector_configs
    Unique constraint: (tenant_id, connector_type) — one config per system per tenant.
    """
    config_id: str                              # Unique config identifier
    tenant_id: str
    connector_type: ConnectorType
    display_name: str                           # "Cadent ServiceNow", "Client A SAP"

    # Connection details
    instance_url: str                           # e.g., https://dev12345.service-now.com
    auth_method: AuthMethod = AuthMethod.OAUTH2
    is_active: bool = False                     # Must be explicitly activated after testing

    # Connector-specific settings
    settings: Dict[str, Any] = {}
    # ServiceNow example settings:
    # {
    #     "table_name": "incident",
    #     "assignment_group": "Gas Safety Team",
    #     "default_category": "Gas Incident",
    #     "webhook_secret": "hmac_secret_for_verification",
    #     "sync_comments": true,
    #     "sync_attachments": true,
    #     "attachment_max_size_mb": 5,
    # }

    # Health monitoring
    health_status: HealthStatus = HealthStatus.UNKNOWN
    last_health_check_at: Optional[datetime] = None
    last_successful_sync_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Connector Credentials ────────────────────────────────────────────────
# Stored separately from config for security. Values are encrypted at rest.

class ConnectorCredentials(BaseModel):
    """Encrypted credentials for a connector.

    MongoDB collection: connector_credentials
    All secret values are AES-256 encrypted before storage.
    Unique constraint: (config_id)
    """
    credential_id: str
    config_id: str                              # References ConnectorConfig.config_id
    tenant_id: str                              # Denormalized for fast lookup + isolation

    auth_method: AuthMethod

    # OAuth 2.0 fields (ServiceNow, Jira Cloud, SAP BTP)
    client_id: Optional[str] = None             # ENCRYPTED
    client_secret: Optional[str] = None         # ENCRYPTED
    token_url: Optional[str] = None             # Token endpoint
    access_token: Optional[str] = None          # ENCRYPTED — current access token
    refresh_token: Optional[str] = None         # ENCRYPTED — for token refresh
    token_expires_at: Optional[datetime] = None

    # Basic auth fields
    username: Optional[str] = None              # ENCRYPTED
    password: Optional[str] = None              # ENCRYPTED

    # API key fields
    api_key: Optional[str] = None               # ENCRYPTED
    api_key_header: Optional[str] = None        # Header name (e.g., "X-API-Key")

    # IAM fields (AWS)
    access_key_id: Optional[str] = None         # ENCRYPTED
    secret_access_key: Optional[str] = None     # ENCRYPTED
    region: Optional[str] = None
    role_arn: Optional[str] = None              # For assume-role

    # Audit
    last_rotated_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Field Mapping ────────────────────────────────────────────────────────
# Defines how fields translate between external systems and canonical model.
# Global default + per-tenant overrides.

class FieldMapDirection(str, Enum):
    """Direction a field mapping applies."""
    BOTH = "both"               # Sync in both directions
    INBOUND = "inbound"         # External -> Platform only
    OUTBOUND = "outbound"       # Platform -> External only


class FieldTransformType(str, Enum):
    """Type of transformation to apply during mapping."""
    DIRECT = "direct"           # Copy as-is
    ENUM_MAP = "enum_map"       # Map between enum values
    SCALE = "scale"             # Numeric scaling (e.g., priority 1-5 -> risk 0-1)
    TEMPLATE = "template"       # String template with variable substitution
    CUSTOM = "custom"           # Custom function (named handler)


class FieldMapEntry(BaseModel):
    """A single field mapping rule between external and canonical fields."""
    external_field: str                         # Field name in external system
    canonical_field: str                        # Field name in CanonicalTicket
    direction: FieldMapDirection = FieldMapDirection.BOTH
    transform_type: FieldTransformType = FieldTransformType.DIRECT
    transform_config: Dict[str, Any] = {}
    # Examples:
    #   DIRECT:   {} (no config needed)
    #   ENUM_MAP: {"map": {"1": "critical", "2": "high", "3": "medium", "4": "low", "5": "planning"}}
    #   SCALE:    {"input_min": 1, "input_max": 5, "output_min": 0.1, "output_max": 0.9, "invert": true}
    #   TEMPLATE: {"template": "Gas Incident: {{description}}"}
    is_required: bool = False                   # Fail sync if this field is missing


class FieldMapping(BaseModel):
    """Complete field mapping configuration for a connector.

    MongoDB collection: field_mappings
    Unique constraint: (tenant_id, connector_type, version)
    tenant_id = None means this is the global default template.
    """
    mapping_id: str
    tenant_id: Optional[str] = None             # None = global default
    connector_type: ConnectorType
    version: int = 1                            # For versioning + rollback
    is_active: bool = True

    # Field-level mappings
    field_maps: List[FieldMapEntry] = []

    # Status mapping (external status string -> CanonicalStatus value)
    status_mapping: Dict[str, str] = {}
    # ServiceNow example:
    # {
    #     "1": "new",           # SN "New"
    #     "2": "in_progress",   # SN "In Progress"
    #     "3": "on_hold",       # SN "On Hold"
    #     "6": "resolved",      # SN "Resolved"
    #     "7": "closed",        # SN "Closed"
    #     "8": "cancelled",     # SN "Cancelled"
    # }

    # Reverse status mapping (CanonicalStatus -> external status string)
    reverse_status_mapping: Dict[str, str] = {}
    # {
    #     "new": "1",
    #     "in_progress": "2",
    #     "on_hold": "3",
    #     "resolved": "6",
    #     "closed": "7",
    #     "cancelled": "8",
    # }

    # Priority mapping (external priority -> CanonicalPriority)
    priority_mapping: Dict[str, str] = {}
    # ServiceNow: {"1": "critical", "2": "high", "3": "medium", "4": "low", "5": "planning"}

    # Priority to risk score mapping (CanonicalPriority -> float)
    priority_to_risk: Dict[str, float] = {}
    # {"critical": 0.9, "high": 0.7, "medium": 0.5, "low": 0.3, "planning": 0.1}

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Incident External Reference (added to Incident model) ───────────────
# Lightweight reference embedded in the Incident model pointing to external ticket.

class IncidentExternalRef(BaseModel):
    """Lightweight external ticket reference embedded in the Incident model.

    This avoids needing a separate query to find the external ticket link
    for display purposes (showing SN ticket number on dashboard).
    Full link details live in ExternalTicketLink collection.
    """
    connector_type: ConnectorType
    external_id: str                            # SN sys_id
    external_number: str                        # INC0010001
    external_url: Optional[str] = None
    sync_status: SyncStatus = SyncStatus.PENDING
    last_synced_at: Optional[datetime] = None


# ── SLO Metric Model ────────────────────────────────────────────────────

class SLOMetric(BaseModel):
    """SLO metric snapshot for a tenant + connector over a time period.

    MongoDB collection: slo_metrics
    Index: (tenant_id, connector_type, period_start)
    """
    metric_id: str
    tenant_id: str
    connector_type: ConnectorType
    period_start: datetime
    period_end: datetime
    period_type: str = "hourly"  # "hourly", "daily", "weekly"

    # Latency percentiles (milliseconds)
    latency_p50: Optional[float] = None
    latency_p90: Optional[float] = None
    latency_p99: Optional[float] = None
    latency_avg: Optional[float] = None

    # Throughput
    total_events: int = 0
    successful_events: int = 0
    failed_events: int = 0
    dead_letter_events: int = 0

    # Success rate
    success_rate: Optional[float] = None  # 0.0 - 1.0

    created_at: datetime

    class Config:
        from_attributes = True


# ── Data Retention Policy Model ─────────────────────────────────────────

class DataRetentionPolicy(BaseModel):
    """Data retention policy for a tenant's connector data.

    MongoDB collection: data_retention_policies
    Unique constraint: (tenant_id)
    """
    policy_id: str
    tenant_id: str

    # TTL settings (in days)
    sync_events_ttl_days: int = 90              # Delete sync events older than N days
    audit_logs_ttl_days: int = 365              # Delete audit logs older than N days
    dead_letter_ttl_days: int = 30              # Delete dead-letter events older than N days

    auto_cleanup_enabled: bool = False          # Auto-delete expired records on schedule

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
