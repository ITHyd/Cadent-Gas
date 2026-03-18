"""Connector management API - configure, test, activate, and monitor connectors."""
import csv
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.auth_dependencies import get_current_user, require_role
from app.models.admin_audit import AdminAction
from app.models.user import UserRole
from app.services.admin_audit_service import log_admin_action, query_audit_logs

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared state (injected at startup from main.py)
_connector_manager = None
_sync_event_bus = None
_sync_service = None


def init_connector_api(connector_manager, sync_event_bus, sync_service):
    """Called once at app startup to inject dependencies."""
    global _connector_manager, _sync_event_bus, _sync_service
    _connector_manager = connector_manager
    _sync_event_bus = sync_event_bus
    _sync_service = sync_service


def _mgr():
    if _connector_manager is None:
        raise HTTPException(status_code=503, detail="Connector subsystem not initialized")
    return _connector_manager


def _bus():
    if _sync_event_bus is None:
        raise HTTPException(status_code=503, detail="Sync event bus not initialized")
    return _sync_event_bus


def _is_super(user: Dict[str, Any]) -> bool:
    return user.get("role") in (UserRole.SUPER_USER.value, UserRole.ADMIN.value)


def _enforce_tenant_scope(current_user: Dict[str, Any], tenant_id: str) -> None:
    """Non-super users can only access their own tenant scope."""
    if _is_super(current_user):
        return
    user_tid = current_user.get("tenant_id")
    if user_tid != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")


require_super_user = require_role(UserRole.SUPER_USER, UserRole.ADMIN)


class ConnectorConfigCreate(BaseModel):
    tenant_id: str
    connector_type: str
    display_name: str
    instance_url: str
    auth_method: str = "basic"
    settings: Dict[str, Any] = {}


class ConnectorConfigUpdate(BaseModel):
    tenant_id: str
    display_name: Optional[str] = None
    instance_url: Optional[str] = None
    auth_method: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class CredentialStore(BaseModel):
    tenant_id: str
    credentials: Dict[str, Any]


@router.get("/available")
async def list_available_connectors(current_user=Depends(require_super_user)):
    """List all registered connector types."""
    _ = current_user
    return {"connectors": _mgr().list_available_connectors()}


@router.get("/tenant/{tenant_id}")
async def get_tenant_connectors(tenant_id: str, current_user=Depends(get_current_user)):
    """Get all connector configs and status for a tenant."""
    _enforce_tenant_scope(current_user, tenant_id)
    return {"tenant_id": tenant_id, "connectors": _mgr().get_status_summary(tenant_id)}


@router.post("/configure")
async def create_connector_config(body: ConnectorConfigCreate, current_user=Depends(require_super_user)):
    """Create a new connector config for a tenant."""
    from app.models.connector import AuthMethod, ConnectorType

    try:
        connector_type = ConnectorType(body.connector_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown connector type: {body.connector_type}. Available: {[t.value for t in ConnectorType]}",
        )

    try:
        auth_method = AuthMethod(body.auth_method)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown auth method: {body.auth_method}. Available: {[m.value for m in AuthMethod]}",
        )

    try:
        config = await _mgr().create_config(
            tenant_id=body.tenant_id,
            connector_type=connector_type,
            display_name=body.display_name,
            instance_url=body.instance_url,
            auth_method=auth_method,
            settings=body.settings,
        )
        await log_admin_action(
            action=AdminAction.CONNECTOR_CREATE,
            actor=current_user,
            tenant_id=body.tenant_id,
            target_id=config.config_id,
            details={"connector_type": connector_type.value},
        )
        return {
            "config_id": config.config_id,
            "connector_type": config.connector_type.value,
            "display_name": config.display_name,
            "status": "created",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{config_id}")
async def update_connector_config(config_id: str, body: ConnectorConfigUpdate, current_user=Depends(require_super_user)):
    """Update a connector configuration. Auto-deactivates if currently active."""
    from app.models.connector import AuthMethod

    updates = {k: v for k, v in body.model_dump(exclude={"tenant_id"}).items() if v is not None}

    if "auth_method" in updates:
        try:
            updates["auth_method"] = AuthMethod(updates["auth_method"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid auth_method: {updates['auth_method']}. Available: {[m.value for m in AuthMethod]}",
            )

    config = await _mgr().update_config(config_id, body.tenant_id, updates)
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    await log_admin_action(
        action=AdminAction.CONNECTOR_UPDATE,
        actor=current_user,
        tenant_id=body.tenant_id,
        target_id=config_id,
        details={"updated_fields": list(updates.keys())},
    )
    return {
        "config_id": config.config_id,
        "status": "updated",
        "updated_fields": list(updates.keys()),
        "is_active": config.is_active,
    }


@router.post("/{config_id}/credentials")
async def store_credentials(config_id: str, body: CredentialStore, current_user=Depends(require_super_user)):
    """Store encrypted credentials for a connector."""
    try:
        cred_id = await _mgr().store_credentials(
            config_id=config_id,
            tenant_id=body.tenant_id,
            credentials=body.credentials,
        )
        await log_admin_action(
            action=AdminAction.CONNECTOR_CREDENTIALS,
            actor=current_user,
            tenant_id=body.tenant_id,
            target_id=config_id,
            details={"credential_id": cred_id, "credential_keys": list(body.credentials.keys())},
        )
        return {"credential_id": cred_id, "status": "stored"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{config_id}/test")
async def test_connection(config_id: str, tenant_id: str, current_user=Depends(require_super_user)):
    """Test connectivity without activating."""
    _ = current_user
    result = await _mgr().test_connection(config_id, tenant_id)
    return result


@router.post("/{config_id}/activate")
async def activate_connector(config_id: str, tenant_id: str, current_user=Depends(require_super_user)):
    """Activate a connector - makes it live for sync."""
    from app.models.connector import ConnectorType

    try:
        success = await _mgr().activate(config_id, tenant_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to activate connector")

        identity_sync = None
        cfg = _mgr().get_config(config_id)
        if (
            cfg is not None
            and _sync_service is not None
            and cfg.connector_type == ConnectorType.SAP
        ):
            try:
                identity_sync = await _sync_service.sync_external_identities(
                    tenant_id=tenant_id,
                    connector_type=ConnectorType.SAP,
                    limit=500,
                )
            except Exception as exc:
                logger.warning(
                    "SAP identity sync failed after activation: tenant=%s config=%s error=%s",
                    tenant_id,
                    config_id,
                    exc,
                )
                identity_sync = {"status": "failed", "error": str(exc)}

        await log_admin_action(
            action=AdminAction.CONNECTOR_ACTIVATE,
            actor=current_user,
            tenant_id=tenant_id,
            target_id=config_id,
        )
        response = {"config_id": config_id, "status": "active"}
        if identity_sync is not None:
            response["identity_sync"] = identity_sync
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{config_id}/deactivate")
async def deactivate_connector(config_id: str, tenant_id: str, current_user=Depends(require_super_user)):
    """Deactivate a connector."""
    success = await _mgr().deactivate(config_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Config not found")
    await log_admin_action(
        action=AdminAction.CONNECTOR_DEACTIVATE,
        actor=current_user,
        tenant_id=tenant_id,
        target_id=config_id,
    )
    return {"config_id": config_id, "status": "inactive"}


@router.delete("/{config_id}")
async def delete_connector_config(config_id: str, tenant_id: str, current_user=Depends(require_super_user)):
    """Delete a connector config, credentials, and all related sync data."""
    success = await _mgr().delete_config(config_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Config not found")

    # Check if tenant has any remaining connectors
    remaining = _mgr().get_tenant_configs(tenant_id)
    cleanup = {}
    if not remaining and _sync_service is not None:
        cleanup = await _sync_service.clear_tenant_data(tenant_id)

    await log_admin_action(
        action=AdminAction.CONNECTOR_DELETE,
        actor=current_user,
        tenant_id=tenant_id,
        target_id=config_id,
    )
    return {"config_id": config_id, "status": "deleted", "cleanup": cleanup}


@router.get("/{config_id}/health")
async def connector_health(config_id: str, current_user=Depends(get_current_user)):
    """Run a health check on an active connector."""
    config = _mgr().get_config(config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")
    _enforce_tenant_scope(current_user, config.tenant_id)
    status = await _mgr().health_check(config_id)
    return {"config_id": config_id, "health_status": status.value}


@router.get("/sync/{tenant_id}/status")
async def sync_status(tenant_id: str, current_user=Depends(get_current_user)):
    """Get sync status summary for a tenant."""
    _enforce_tenant_scope(current_user, tenant_id)
    return _bus().get_sync_status(tenant_id)


@router.get("/sync/{tenant_id}/logs")
async def sync_logs(
    tenant_id: str,
    status: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user=Depends(get_current_user),
):
    """Get sync event logs for a tenant."""
    from app.models.connector import SyncDirection, SyncEventStatus

    _enforce_tenant_scope(current_user, tenant_id)

    try:
        status_filter = SyncEventStatus(status) if status else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status filter: {status}")

    try:
        dir_filter = SyncDirection(direction) if direction else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid direction filter: {direction}")

    events, total = _bus().get_events(
        tenant_id=tenant_id,
        status=status_filter,
        direction=dir_filter,
        limit=limit,
        offset=offset,
    )
    return {
        "tenant_id": tenant_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [e.model_dump() for e in events],
    }


@router.get("/sync/{tenant_id}/dead-letter")
async def get_dead_letter_events(
    tenant_id: str,
    limit: int = 50,
    current_user=Depends(get_current_user),
):
    """List dead-letter events for a tenant."""
    _enforce_tenant_scope(current_user, tenant_id)
    events = _bus().get_dead_letter_events(tenant_id=tenant_id, limit=limit)
    return {
        "tenant_id": tenant_id,
        "total": len(events),
        "events": [e.model_dump() for e in events],
    }


@router.post("/sync/{tenant_id}/dead-letter/{event_id}/replay")
async def replay_dead_letter_event(
    tenant_id: str,
    event_id: str,
    current_user=Depends(require_super_user),
):
    """Replay one DLQ event by ID."""
    existing = _bus().get_event(event_id)
    if existing is None or existing.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Dead-letter event not found")
    event = await _bus().replay_dead_letter(event_id)
    if event is None:
        raise HTTPException(status_code=400, detail="Event is not in dead-letter queue")

    await log_admin_action(
        action=AdminAction.CONNECTOR_REPLAY,
        actor=current_user,
        tenant_id=tenant_id,
        target_id=event_id,
        details={"mode": "single"},
    )
    return {"tenant_id": tenant_id, "event_id": event_id, "status": "replayed"}


@router.post("/sync/{tenant_id}/dead-letter/replay-all")
async def replay_all_dead_letter_events(
    tenant_id: str,
    current_user=Depends(require_super_user),
):
    """Replay all DLQ events for a tenant."""
    count = await _bus().replay_all_dead_letter(tenant_id)
    await log_admin_action(
        action=AdminAction.CONNECTOR_REPLAY,
        actor=current_user,
        tenant_id=tenant_id,
        details={"mode": "all", "count": count},
    )
    return {"tenant_id": tenant_id, "replayed": count}


@router.get("/sync/{tenant_id}/events/{event_id}/trace")
async def get_event_trace(
    tenant_id: str,
    event_id: str,
    current_user=Depends(get_current_user),
):
    """Get trace details for a sync event."""
    _enforce_tenant_scope(current_user, tenant_id)
    event = _bus().get_event(event_id)
    if event is None or event.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Event not found")

    timeline = [
        {"step": "published", "at": event.created_at.isoformat(), "status": "pending"},
    ]
    if event.retry_count:
        timeline.append(
            {
                "step": "retries",
                "at": (event.next_retry_at.isoformat() if event.next_retry_at else None),
                "status": f"retry_count={event.retry_count}",
            }
        )
    if event.processed_at:
        timeline.append(
            {
                "step": "processed",
                "at": event.processed_at.isoformat(),
                "status": event.status.value,
            }
        )

    return {
        "tenant_id": tenant_id,
        "event": event.model_dump(),
        "timeline": timeline,
    }


# ── SLO Monitoring ────────────────────────────────────────────────────

@router.get("/slo/{tenant_id}/metrics")
async def slo_metrics(
    tenant_id: str,
    connector_type: Optional[str] = None,
    period_type: str = "hourly",
    limit: int = 24,
    current_user=Depends(get_current_user),
):
    """Get historical SLO metrics for a tenant."""
    _enforce_tenant_scope(current_user, tenant_id)
    metrics = await _bus().get_slo_metrics(
        tenant_id=tenant_id,
        connector_type=connector_type,
        period_type=period_type,
        limit=limit,
    )
    return {"tenant_id": tenant_id, "period_type": period_type, "metrics": metrics}


@router.get("/slo/{tenant_id}/summary")
async def slo_summary(
    tenant_id: str,
    connector_type: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """Get real-time SLO summary from in-memory accumulators."""
    from app.models.connector import ConnectorType

    _enforce_tenant_scope(current_user, tenant_id)
    ct = ConnectorType(connector_type) if connector_type else None
    summary = _bus().get_slo_summary(tenant_id, ct)
    return {"tenant_id": tenant_id, "connectors": summary}


# ── Backfill & Reconciliation ────────────────────────────────────────

class BackfillRequest(BaseModel):
    connector_type: str
    limit: int = 100
    offset: int = 0
    filters: Dict[str, Any] = {}


@router.post("/backfill/{tenant_id}")
async def trigger_backfill(
    tenant_id: str,
    body: BackfillRequest,
    current_user=Depends(require_super_user),
):
    """Trigger historical import from external system."""
    from app.models.connector import ConnectorType

    try:
        ct = ConnectorType(body.connector_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown connector type: {body.connector_type}")

    if _sync_service is None:
        raise HTTPException(status_code=503, detail="Sync service not initialized")

    try:
        result = await _sync_service.backfill(
            tenant_id=tenant_id,
            connector_type=ct,
            limit=body.limit,
            offset=body.offset,
            filters=body.filters or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await log_admin_action(
        action=AdminAction.CONNECTOR_BACKFILL,
        actor=current_user,
        tenant_id=tenant_id,
        details={"connector_type": ct.value, "result": result},
    )
    return {"tenant_id": tenant_id, **result}


@router.post("/reconcile/{tenant_id}")
async def trigger_reconciliation(
    tenant_id: str,
    connector_type: str = "servicenow",
    current_user=Depends(require_super_user),
):
    """Trigger drift detection between platform and external system."""
    from app.models.connector import ConnectorType

    try:
        ct = ConnectorType(connector_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown connector type: {connector_type}")

    if _sync_service is None:
        raise HTTPException(status_code=503, detail="Sync service not initialized")

    try:
        result = await _sync_service.reconcile(tenant_id=tenant_id, connector_type=ct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await log_admin_action(
        action=AdminAction.CONNECTOR_RECONCILE,
        actor=current_user,
        tenant_id=tenant_id,
        details={"connector_type": ct.value, "total_checked": result["total_checked"], "drifted": result["drifted"]},
    )
    return {"tenant_id": tenant_id, **result}


# ── Audit Export ──────────────────────────────────────────────────────

@router.get("/audit/export")
async def export_audit_logs(
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
    format: str = "json",
    current_user=Depends(require_super_user),
):
    """Export audit logs as JSON or CSV."""
    parsed_from = datetime.fromisoformat(date_from) if date_from else None
    parsed_to = datetime.fromisoformat(date_to) if date_to else None

    result = await query_audit_logs(
        action=action,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        date_from=parsed_from,
        date_to=parsed_to,
        limit=limit,
        offset=offset,
    )

    await log_admin_action(
        action=AdminAction.AUDIT_EXPORT,
        actor=current_user,
        tenant_id=tenant_id,
        details={"format": format, "total": result["total"], "limit": limit},
    )

    if format == "csv":
        return _audit_logs_to_csv(result["logs"])

    return result


def _audit_logs_to_csv(logs: List[Dict[str, Any]]) -> StreamingResponse:
    """Convert audit log entries to a CSV streaming response."""
    output = io.StringIO()
    if not logs:
        output.write("No audit logs found\n")
    else:
        fieldnames = ["audit_id", "action", "actor_user_id", "actor_role", "tenant_id", "target_id", "details", "created_at"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for log_entry in logs:
            row = {k: log_entry.get(k, "") for k in fieldnames}
            if isinstance(row.get("details"), dict):
                row["details"] = str(row["details"])
            writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


# ── Data Retention ────────────────────────────────────────────────────

class RetentionPolicyUpdate(BaseModel):
    sync_events_ttl_days: int = 90
    audit_logs_ttl_days: int = 365
    dead_letter_ttl_days: int = 30
    auto_cleanup_enabled: bool = False


@router.get("/retention/{tenant_id}")
async def get_retention_policy(
    tenant_id: str,
    current_user=Depends(require_super_user),
):
    """Get data retention policy for a tenant."""
    from app.services.data_retention_service import get_retention_policy as _get_policy

    _ = current_user
    policy = await _get_policy(tenant_id)
    if not policy:
        return {
            "tenant_id": tenant_id,
            "policy": None,
            "message": "No custom retention policy — using defaults (sync=90d, audit=365d, dlq=30d)",
        }
    return {"tenant_id": tenant_id, "policy": policy}


@router.put("/retention/{tenant_id}")
async def set_retention_policy(
    tenant_id: str,
    body: RetentionPolicyUpdate,
    current_user=Depends(require_super_user),
):
    """Create or update data retention policy for a tenant."""
    from app.services.data_retention_service import upsert_retention_policy

    policy = await upsert_retention_policy(
        tenant_id=tenant_id,
        sync_events_ttl_days=body.sync_events_ttl_days,
        audit_logs_ttl_days=body.audit_logs_ttl_days,
        dead_letter_ttl_days=body.dead_letter_ttl_days,
        auto_cleanup_enabled=body.auto_cleanup_enabled,
    )

    await log_admin_action(
        action=AdminAction.DATA_RETENTION_UPDATE,
        actor=current_user,
        tenant_id=tenant_id,
        details={
            "sync_events_ttl_days": body.sync_events_ttl_days,
            "audit_logs_ttl_days": body.audit_logs_ttl_days,
            "dead_letter_ttl_days": body.dead_letter_ttl_days,
            "auto_cleanup_enabled": body.auto_cleanup_enabled,
        },
    )
    return {"tenant_id": tenant_id, "policy": policy}


@router.post("/retention/{tenant_id}/cleanup")
async def trigger_cleanup(
    tenant_id: str,
    current_user=Depends(require_super_user),
):
    """Manually trigger cleanup of expired data for a tenant."""
    from app.services.data_retention_service import cleanup_expired_events

    results = await cleanup_expired_events(tenant_id)
    await log_admin_action(
        action=AdminAction.DATA_RETENTION_UPDATE,
        actor=current_user,
        tenant_id=tenant_id,
        details={"action": "manual_cleanup", "deleted": results},
    )
    return {"tenant_id": tenant_id, "deleted": results}


@router.delete("/data/{tenant_id}/purge")
async def purge_tenant_data(
    tenant_id: str,
    current_user=Depends(require_super_user),
):
    """Destructive: delete ALL connector data for a tenant."""
    from app.services.data_retention_service import purge_tenant_data as _purge

    results = await _purge(tenant_id)
    await log_admin_action(
        action=AdminAction.DATA_PURGE,
        actor=current_user,
        tenant_id=tenant_id,
        details={"purged_collections": results},
    )
    return {"tenant_id": tenant_id, "status": "purged", "deleted": results}
