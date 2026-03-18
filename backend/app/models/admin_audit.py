"""Admin audit log models."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel


class AdminAction(str, Enum):
    CONNECTOR_CREATE = "connector_create"
    CONNECTOR_CREDENTIALS = "connector_credentials"
    CONNECTOR_ACTIVATE = "connector_activate"
    CONNECTOR_DEACTIVATE = "connector_deactivate"
    CONNECTOR_DELETE = "connector_delete"
    CONNECTOR_UPDATE = "connector_update"
    CONNECTOR_REPLAY = "connector_replay"
    TENANT_CONFIG_UPDATE = "tenant_config_update"
    TENANT_MAPPING_UPDATE = "tenant_mapping_update"
    TENANT_MAPPING_ROLLBACK = "tenant_mapping_rollback"
    WORKFLOW_CREATE = "workflow_create"
    WORKFLOW_UPDATE = "workflow_update"
    CONNECTOR_BACKFILL = "connector_backfill"
    CONNECTOR_RECONCILE = "connector_reconcile"
    AUDIT_EXPORT = "audit_export"
    DATA_RETENTION_UPDATE = "data_retention_update"
    DATA_PURGE = "data_purge"


class AdminAuditLog(BaseModel):
    audit_id: str
    action: AdminAction
    actor_user_id: str
    actor_role: str
    tenant_id: Optional[str] = None
    target_id: Optional[str] = None
    details: Dict[str, Any] = {}
    created_at: datetime = datetime.utcnow()
