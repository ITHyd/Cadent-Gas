"""Webhook receiver endpoints — unauthenticated, signature-verified.

These endpoints are called by external systems (ServiceNow, SAP, etc.) to
notify the platform of changes.  They are intentionally separate from the
connectors.py management API because:
  - No user authentication (webhooks come from machines, not users)
  - Signature verification (HMAC-SHA256) replaces user auth
  - Different URL pattern: /api/v1/webhooks/{system}/{tenant_id}

Endpoints:
    POST /api/v1/webhooks/servicenow/{tenant_id}  — ServiceNow webhook receiver
    POST /api/v1/webhooks/sap/{tenant_id}          — SAP webhook receiver
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.models.connector import ConnectorType

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Shared state (injected at startup from main.py) ───────────────────
_connector_manager = None
_sync_event_bus = None
_sync_service = None


def init_webhook_api(connector_manager, sync_event_bus, sync_service):
    """Called once at app startup to inject dependencies."""
    global _connector_manager, _sync_event_bus, _sync_service
    _connector_manager = connector_manager
    _sync_event_bus = sync_event_bus
    _sync_service = sync_service


def _mgr():
    if _connector_manager is None:
        raise HTTPException(status_code=503, detail="Connector subsystem not initialized")
    return _connector_manager


def _svc():
    if _sync_service is None:
        raise HTTPException(status_code=503, detail="Sync service not initialized")
    return _sync_service


# ── ServiceNow Webhook ────────────────────────────────────────────────

@router.post("/servicenow/{tenant_id}")
async def servicenow_webhook(tenant_id: str, request: Request):
    """Receive a webhook from ServiceNow.

    Flow:
      1. Read raw body bytes (needed for HMAC verification)
      2. Verify signature via connector.verify_webhook_signature()
      3. Parse payload via connector.handle_webhook()
      4. Publish inbound SyncEvent and process immediately
      5. Return 200 OK (ServiceNow expects 2xx to confirm delivery)
    """
    # Read raw body for signature verification
    raw_body = await request.body()

    # Parse JSON payload
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Normalize headers to a plain dict (lowercase keys for consistency)
    headers = {k.lower(): v for k, v in request.headers.items()}

    # Get the active ServiceNow connector for this tenant
    connector = _mgr().get_active_connector(tenant_id, ConnectorType.SERVICENOW)
    if not connector:
        raise HTTPException(
            status_code=404,
            detail=f"No active ServiceNow connector for tenant {tenant_id}",
        )

    # Verify webhook signature (HMAC-SHA256 + replay protection)
    is_valid = await connector.verify_webhook_signature(raw_body, headers)
    if not is_valid:
        logger.warning(
            "Webhook signature verification failed: tenant=%s", tenant_id,
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse the SN payload into a CanonicalTicket
    canonical = await connector.handle_webhook(payload, headers)
    if not canonical:
        # Payload parsed but no actionable data — still acknowledge
        return {"status": "ignored", "reason": "No actionable data in payload"}

    # Publish inbound SyncEvent and process
    event = await _svc().on_webhook_received(
        tenant_id=tenant_id,
        connector_type=ConnectorType.SERVICENOW,
        canonical=canonical,
        raw_payload=payload,
    )

    event_id = event.event_id if event else None
    status = "processed" if event else "duplicate"

    logger.info(
        "ServiceNow webhook processed: tenant=%s event=%s status=%s",
        tenant_id, event_id, status,
    )

    return {
        "status": status,
        "event_id": event_id,
        "external_id": canonical.external_id,
    }


# ── SAP Webhook ──────────────────────────────────────────────────────

@router.post("/sap/{tenant_id}")
async def sap_webhook(tenant_id: str, request: Request):
    """Receive a webhook from SAP.

    Flow:
      1. Read raw body bytes (needed for HMAC verification)
      2. Verify signature via connector.verify_webhook_signature()
      3. Parse payload via connector.handle_webhook()
      4. Publish inbound SyncEvent and process immediately
      5. Return 200 OK (SAP expects 2xx to confirm delivery)
    """
    raw_body = await request.body()

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    headers = {k.lower(): v for k, v in request.headers.items()}

    connector = _mgr().get_active_connector(tenant_id, ConnectorType.SAP)
    if not connector:
        raise HTTPException(
            status_code=404,
            detail=f"No active SAP connector for tenant {tenant_id}",
        )

    is_valid = await connector.verify_webhook_signature(raw_body, headers)
    if not is_valid:
        logger.warning(
            "SAP webhook signature verification failed: tenant=%s", tenant_id,
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    canonical = await connector.handle_webhook(payload, headers)
    if not canonical:
        return {"status": "ignored", "reason": "No actionable data in payload"}

    event = await _svc().on_webhook_received(
        tenant_id=tenant_id,
        connector_type=ConnectorType.SAP,
        canonical=canonical,
        raw_payload=payload,
    )

    event_id = event.event_id if event else None
    status = "processed" if event else "duplicate"

    logger.info(
        "SAP webhook processed: tenant=%s event=%s status=%s",
        tenant_id, event_id, status,
    )

    return {
        "status": status,
        "event_id": event_id,
        "external_id": canonical.external_id,
    }
