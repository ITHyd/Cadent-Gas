"""Admin audit logging helpers."""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.mongodb import get_database
from app.models.admin_audit import AdminAction

logger = logging.getLogger(__name__)


async def log_admin_action(
    *,
    action: AdminAction,
    actor: Dict[str, Any],
    tenant_id: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a best-effort admin audit log entry."""
    db = get_database()
    if db is None:
        return

    actor_user_id = str(actor.get("user_id", "unknown"))
    actor_role = str(actor.get("role", "unknown"))
    payload = {
        "audit_id": f"AUD_{uuid.uuid4().hex[:12].upper()}",
        "action": action.value if isinstance(action, AdminAction) else str(action),
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "tenant_id": tenant_id,
        "target_id": target_id,
        "details": details or {},
        "created_at": datetime.utcnow(),
    }
    try:
        await db.admin_audit_logs.insert_one(payload)
    except Exception:
        logger.exception("Failed to write admin audit log: action=%s", payload["action"])


async def query_audit_logs(
    *,
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """Query audit logs with filters and pagination.

    Returns:
        Dict with "total", "limit", "offset", and "logs" list.
    """
    db = get_database()
    if db is None:
        return {"total": 0, "limit": limit, "offset": offset, "logs": []}

    query: Dict[str, Any] = {}
    if action:
        query["action"] = action
    if actor_user_id:
        query["actor_user_id"] = actor_user_id
    if tenant_id:
        query["tenant_id"] = tenant_id
    if date_from or date_to:
        date_filter: Dict[str, Any] = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        query["created_at"] = date_filter

    total = await db.admin_audit_logs.count_documents(query)

    cursor = (
        db.admin_audit_logs
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    logs: List[Dict[str, Any]] = []
    async for doc in cursor:
        # Serialize datetimes
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        logs.append(doc)

    return {"total": total, "limit": limit, "offset": offset, "logs": logs}
