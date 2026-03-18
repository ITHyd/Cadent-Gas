"""Data retention service — TTL policies, cleanup, and tenant data purge."""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.mongodb import get_database

logger = logging.getLogger(__name__)


async def get_retention_policy(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the data retention policy for a tenant."""
    db = get_database()
    if db is None:
        return None
    doc = await db.data_retention_policies.find_one(
        {"tenant_id": tenant_id}, {"_id": 0}
    )
    return doc


async def upsert_retention_policy(
    tenant_id: str,
    sync_events_ttl_days: int = 90,
    audit_logs_ttl_days: int = 365,
    dead_letter_ttl_days: int = 30,
    auto_cleanup_enabled: bool = False,
) -> Dict[str, Any]:
    """Create or update a retention policy for a tenant."""
    db = get_database()
    if db is None:
        raise RuntimeError("Database not available")

    now = datetime.utcnow()
    existing = await db.data_retention_policies.find_one({"tenant_id": tenant_id})

    policy = {
        "tenant_id": tenant_id,
        "sync_events_ttl_days": sync_events_ttl_days,
        "audit_logs_ttl_days": audit_logs_ttl_days,
        "dead_letter_ttl_days": dead_letter_ttl_days,
        "auto_cleanup_enabled": auto_cleanup_enabled,
        "updated_at": now,
    }

    if existing:
        await db.data_retention_policies.update_one(
            {"tenant_id": tenant_id}, {"$set": policy}
        )
        policy["policy_id"] = existing.get("policy_id", "")
        policy["created_at"] = existing.get("created_at", now)
    else:
        policy["policy_id"] = f"RET_{uuid.uuid4().hex[:12].upper()}"
        policy["created_at"] = now
        await db.data_retention_policies.insert_one(policy)

    return {k: v for k, v in policy.items() if k != "_id"}


async def cleanup_expired_events(tenant_id: str) -> Dict[str, int]:
    """Delete sync events, audit logs, and DLQ entries older than their TTL.

    Skips events still in PENDING or PROCESSING status.
    Returns counts of deleted records by collection.
    """
    db = get_database()
    if db is None:
        return {"sync_events": 0, "audit_logs": 0, "dead_letter": 0}

    policy = await get_retention_policy(tenant_id)
    if not policy:
        # Use defaults
        policy = {
            "sync_events_ttl_days": 90,
            "audit_logs_ttl_days": 365,
            "dead_letter_ttl_days": 30,
        }

    now = datetime.utcnow()
    results = {"sync_events": 0, "audit_logs": 0, "dead_letter": 0}

    # Clean sync events (skip pending/processing)
    sync_cutoff = now - timedelta(days=policy["sync_events_ttl_days"])
    sync_result = await db.sync_events.delete_many({
        "tenant_id": tenant_id,
        "created_at": {"$lt": sync_cutoff},
        "status": {"$nin": ["pending", "processing"]},
    })
    results["sync_events"] = sync_result.deleted_count

    # Clean audit logs
    audit_cutoff = now - timedelta(days=policy["audit_logs_ttl_days"])
    audit_result = await db.admin_audit_logs.delete_many({
        "tenant_id": tenant_id,
        "created_at": {"$lt": audit_cutoff},
    })
    results["audit_logs"] = audit_result.deleted_count

    # Clean dead-letter events
    dlq_cutoff = now - timedelta(days=policy["dead_letter_ttl_days"])
    dlq_result = await db.sync_events.delete_many({
        "tenant_id": tenant_id,
        "status": "dead_letter",
        "created_at": {"$lt": dlq_cutoff},
    })
    results["dead_letter"] = dlq_result.deleted_count

    logger.info(
        "Cleanup completed for tenant=%s: sync_events=%d audit_logs=%d dead_letter=%d",
        tenant_id, results["sync_events"], results["audit_logs"], results["dead_letter"],
    )
    return results


async def purge_tenant_data(tenant_id: str) -> Dict[str, int]:
    """Destructive: delete ALL connector-related data for a tenant.

    Removes: sync events, connector configs, credentials, field mappings,
    external ticket links, SLO metrics, audit logs, retention policies.
    """
    db = get_database()
    if db is None:
        return {}

    results = {}
    collections_to_purge = [
        "sync_events",
        "connector_configs",
        "connector_credentials",
        "field_mappings",
        "external_ticket_links",
        "slo_metrics",
        "admin_audit_logs",
        "data_retention_policies",
    ]

    for col_name in collections_to_purge:
        col = db[col_name]
        result = await col.delete_many({"tenant_id": tenant_id})
        results[col_name] = result.deleted_count

    logger.warning(
        "PURGE completed for tenant=%s: %s",
        tenant_id,
        ", ".join(f"{k}={v}" for k, v in results.items()),
    )
    return results
