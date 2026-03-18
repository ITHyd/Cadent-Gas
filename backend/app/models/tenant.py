"""Tenant configuration and branding models.

Each tenant represents a client organization (e.g., Cadent Gas Ltd)
with its own branding, users, incidents, and connector configuration.

Stored in the MongoDB `tenants` collection as a single document per tenant.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TenantStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    ONBOARDING = "onboarding"


class TenantBranding(BaseModel):
    """Visual branding configuration for the client portal."""

    company_name: str = "Gas Intelligence"
    subdomain: str = ""                          # e.g., "cadent" → /portal/cadent/
    logo_url: Optional[str] = None               # URL or path to logo image
    favicon_url: Optional[str] = None
    primary_color: str = "#0c4a6e"               # Main brand color
    secondary_color: str = "#0f766e"             # Accent color
    background_color: str = "#f8fbff"
    text_color: str = "#0f1f33"
    chatbot_name: str = "Gas Assistant"
    chatbot_avatar: Optional[str] = None
    welcome_message: str = "Welcome! How can we help you today?"
    powered_by_text: str = "Powered by Gas Intelligence Platform"
    powered_by_visible: bool = True


class TenantConfig(BaseModel):
    """Per-tenant operational configuration (extensible for Phase 2+)."""

    connector_overrides: Dict[str, Any] = {}     # Per-tenant connector settings
    ai_persona: Optional[str] = None             # Custom system prompt override
    default_workflow_routing: Dict[str, str] = {} # use_case → workflow_id
    timezone: str = "Europe/London"
    locale: str = "en-GB"


class AdminGroup(BaseModel):
    """An admin group within a tenant, scoping company users to specific connector types.

    connector_scope values: ConnectorType enum values (e.g., "sap", "servicenow")
    plus "portal" for chatbot/portal-reported incidents.
    Empty list = general admin (sees everything).
    """

    group_id: str
    display_name: str
    connector_scope: List[str] = []
    description: Optional[str] = None
    created_at: datetime = datetime.utcnow()


class Tenant(BaseModel):
    """Top-level tenant document stored in MongoDB."""

    tenant_id: str                                # Unique, e.g., "tenant_cadent"
    display_name: str                             # "Cadent Gas Ltd"
    status: TenantStatus = TenantStatus.ONBOARDING
    branding: TenantBranding = TenantBranding()
    config: TenantConfig = TenantConfig()
    admin_groups: List[AdminGroup] = []           # Connector-scoped admin groups
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()
    created_by: Optional[str] = None              # user_id of creator


# ── Request/Response Models ────────────────────────────────────────────────

class TenantCreate(BaseModel):
    """Request body for creating a new tenant."""

    tenant_id: str
    display_name: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    branding: Optional[TenantBranding] = None
    notes: Optional[str] = None


class TenantUpdate(BaseModel):
    """Request body for updating tenant fields."""

    display_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    branding: Optional[TenantBranding] = None
    config: Optional[TenantConfig] = None
    notes: Optional[str] = None


class TenantStatusUpdate(BaseModel):
    """Request body for changing tenant status."""

    status: TenantStatus


class AdminGroupCreate(BaseModel):
    """Request body for creating an admin group."""

    group_id: Optional[str] = None       # Auto-generated if not provided
    display_name: str
    connector_scope: List[str] = []
    description: Optional[str] = None


class AdminGroupUpdate(BaseModel):
    """Request body for updating an admin group."""

    display_name: Optional[str] = None
    connector_scope: Optional[List[str]] = None
    description: Optional[str] = None


class UserGroupAssignment(BaseModel):
    """Request body for assigning a user to an admin group."""

    admin_group_id: Optional[str] = None  # None to unassign
