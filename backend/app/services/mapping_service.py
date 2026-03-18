"""Field mapping persistence helpers."""
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from app.connectors.field_mapping_engine import mapping_engine
from app.core.mongodb import get_database
from app.models.connector import ConnectorType, FieldMapping

logger = logging.getLogger(__name__)


def _mappings_col():
    db = get_database()
    return db.field_mappings if db is not None else None


async def load_active_mappings() -> int:
    """Load active mappings from MongoDB into the in-memory engine."""
    col = _mappings_col()
    if col is None:
        return 0

    loaded = 0
    async for doc in col.find({"is_active": True}, {"_id": 0}):
        try:
            mapping = FieldMapping(**doc)
            mapping_engine.register_mapping(mapping)
            loaded += 1
        except Exception:
            logger.exception(
                "Failed to load field mapping mapping_id=%s",
                doc.get("mapping_id"),
            )
    return loaded


async def get_latest_version(tenant_id: Optional[str], connector_type: ConnectorType) -> int:
    col = _mappings_col()
    if col is None:
        return 0
    doc = await col.find_one(
        {"tenant_id": tenant_id, "connector_type": connector_type.value},
        {"version": 1},
        sort=[("version", -1)],
    )
    if not doc:
        return 0
    return int(doc.get("version", 0))


async def list_versions(
    tenant_id: Optional[str],
    connector_type: ConnectorType,
    limit: int = 25,
) -> List[Dict]:
    col = _mappings_col()
    if col is None:
        return []
    docs = []
    async for doc in col.find(
        {"tenant_id": tenant_id, "connector_type": connector_type.value},
        {"_id": 0},
    ).sort("version", -1).limit(limit):
        docs.append(doc)
    return docs


async def save_new_version(
    tenant_id: Optional[str],
    connector_type: ConnectorType,
    base_payload: Dict,
) -> FieldMapping:
    """Create and persist a new active mapping version for a tenant + connector."""
    col = _mappings_col()
    if col is None:
        raise RuntimeError("Database unavailable")

    next_version = await get_latest_version(tenant_id, connector_type) + 1
    now = datetime.utcnow()
    mapping = FieldMapping(
        mapping_id=f"FM_{uuid.uuid4().hex[:12].upper()}",
        tenant_id=tenant_id,
        connector_type=connector_type,
        version=next_version,
        is_active=True,
        field_maps=base_payload.get("field_maps", []),
        status_mapping=base_payload.get("status_mapping", {}),
        reverse_status_mapping=base_payload.get("reverse_status_mapping", {}),
        priority_mapping=base_payload.get("priority_mapping", {}),
        priority_to_risk=base_payload.get("priority_to_risk", {}),
        created_at=now,
        updated_at=now,
    )

    await col.update_many(
        {"tenant_id": tenant_id, "connector_type": connector_type.value, "is_active": True},
        {"$set": {"is_active": False, "updated_at": now}},
    )
    await col.insert_one(mapping.model_dump())
    mapping_engine.register_mapping(mapping)
    return mapping


async def rollback_version(
    tenant_id: Optional[str],
    connector_type: ConnectorType,
    version: int,
) -> Optional[FieldMapping]:
    col = _mappings_col()
    if col is None:
        return None

    target = await col.find_one(
        {"tenant_id": tenant_id, "connector_type": connector_type.value, "version": version},
        {"_id": 0},
    )
    if not target:
        return None

    now = datetime.utcnow()
    await col.update_many(
        {"tenant_id": tenant_id, "connector_type": connector_type.value, "is_active": True},
        {"$set": {"is_active": False, "updated_at": now}},
    )
    await col.update_one(
        {"mapping_id": target["mapping_id"]},
        {"$set": {"is_active": True, "updated_at": now}},
    )
    mapping = FieldMapping(**{**target, "is_active": True, "updated_at": now})
    mapping_engine.register_mapping(mapping)
    return mapping
