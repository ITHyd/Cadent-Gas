"""Tenant management API — CRUD, admin groups, mappings, user creation.

Endpoints:
    POST   /api/v1/tenants/                          — create tenant
    GET    /api/v1/tenants/                          — list all tenants
    GET    /api/v1/tenants/{tenant_id}               — get tenant detail
    PUT    /api/v1/tenants/{tenant_id}               — update tenant
    PUT    /api/v1/tenants/{tenant_id}/status        — change status
    POST   /api/v1/tenants/{tenant_id}/users         — create tenant user
    DELETE /api/v1/tenants/{tenant_id}               — soft delete (suspend)
"""
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.connectors.field_mapping_engine import mapping_engine
from app.core.auth_dependencies import require_role
from app.core.mongodb import get_database
from app.models.admin_audit import AdminAction
from app.models.connector import ConnectorType, FieldMapEntry
from app.models.user import UserRole
from app.services.admin_audit_service import log_admin_action
from app.services.auth_service import auth_service
from app.services.mapping_service import (
    list_versions as list_mapping_versions,
    rollback_version as rollback_mapping_version,
    save_new_version as save_mapping_version,
)
from app.models.tenant import (
    AdminGroup,
    AdminGroupCreate,
    AdminGroupUpdate,
    Tenant,
    TenantBranding,
    TenantConfig,
    TenantCreate,
    TenantStatus,
    TenantStatusUpdate,
    TenantUpdate,
    UserGroupAssignment,
)

logger = logging.getLogger(__name__)
router = APIRouter()

require_super_user = require_role(UserRole.SUPER_USER, UserRole.ADMIN)


class TenantUserCreate(BaseModel):
    """Request body for creating a user under a tenant."""

    user_id: Optional[str] = None
    full_name: str
    phone: str
    role: UserRole = UserRole.COMPANY
    username: Optional[str] = None
    password: Optional[str] = None


class TenantMappingUpdate(BaseModel):
    """Request body for creating a new tenant-specific mapping version."""

    field_maps: list[FieldMapEntry] = []
    status_mapping: Dict[str, str] = {}
    reverse_status_mapping: Dict[str, str] = {}
    priority_mapping: Dict[str, str] = {}
    priority_to_risk: Dict[str, float] = {}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _tenants_col():
    return get_database().tenants


async def _get_tenant_or_404(tenant_id: str) -> dict:
    doc = await _tenants_col().find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    return doc


async def _get_tenant_stats(tenant_id: str) -> dict:
    """Aggregate user, incident, and workflow counts for a tenant."""
    db = get_database()

    # User counts by role
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$role", "count": {"$sum": 1}}},
    ]
    role_counts = {}
    async for doc in db.users.aggregate(pipeline):
        role_counts[doc["_id"]] = doc["count"]

    total_users = sum(role_counts.values())

    # Incident counts
    try:
        from app.api.agents import agent_orchestrator
        inc_stats = agent_orchestrator.incident_service.get_incident_stats(tenant_id)
    except Exception:
        inc_stats = {"total": 0, "pending": 0, "dispatched": 0, "resolved": 0}

    # Workflow count
    try:
        from app.services.workflow_repository import workflow_repository
        wf_count = len(workflow_repository.list_by_tenant(tenant_id))
    except Exception:
        wf_count = 0

    return {
        "users": {"total": total_users, "by_role": role_counts},
        "incidents": inc_stats,
        "workflows": wf_count,
    }


def _parse_connector_type_or_400(connector_type: str) -> ConnectorType:
    try:
        return ConnectorType(connector_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown connector type: {connector_type}",
        )


# ── Authenticated CRUD endpoints ───────────────────────────────────────────

@router.post("/")
async def create_tenant(body: TenantCreate, current_user=Depends(require_super_user)):
    """Create a new tenant."""
    col = _tenants_col()

    # Check uniqueness
    existing = await col.find_one({"tenant_id": body.tenant_id})
    if existing:
        raise HTTPException(status_code=409, detail=f"Tenant '{body.tenant_id}' already exists")

    now = datetime.utcnow()
    tenant = Tenant(
        tenant_id=body.tenant_id,
        display_name=body.display_name,
        status=TenantStatus.ONBOARDING,
        branding=body.branding or TenantBranding(),
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        notes=body.notes,
        created_at=now,
        updated_at=now,
        created_by=current_user.get("user_id"),
    )

    await col.insert_one(tenant.model_dump())
    logger.info("Created tenant: %s", body.tenant_id)

    return {
        "tenant_id": tenant.tenant_id,
        "display_name": tenant.display_name,
        "status": tenant.status.value,
        "message": "Tenant created",
    }


@router.get("/")
async def list_tenants(current_user=Depends(require_super_user)):
    """List all tenants with aggregated stats."""
    col = _tenants_col()

    tenants = []
    async for doc in col.find({}, {"_id": 0}).sort("created_at", 1):
        tid = doc["tenant_id"]
        stats = await _get_tenant_stats(tid)
        tenants.append({
            **doc,
            "created_at": doc["created_at"].isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at"),
            "updated_at": doc["updated_at"].isoformat() if isinstance(doc.get("updated_at"), datetime) else doc.get("updated_at"),
            **stats,
        })

    return {"tenants": tenants, "total": len(tenants)}


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: str, current_user=Depends(require_super_user)):
    """Get tenant detail with stats."""
    doc = await _get_tenant_or_404(tenant_id)
    stats = await _get_tenant_stats(tenant_id)

    # Serialize datetimes
    for field in ("created_at", "updated_at"):
        if isinstance(doc.get(field), datetime):
            doc[field] = doc[field].isoformat()

    return {**doc, **stats}


@router.put("/{tenant_id}")
async def update_tenant(
    tenant_id: str, body: TenantUpdate, current_user=Depends(require_super_user)
):
    """Update tenant fields."""
    await _get_tenant_or_404(tenant_id)

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Flatten nested models for MongoDB $set
    set_fields = {"updated_at": datetime.utcnow()}
    for key, val in update_data.items():
        if isinstance(val, dict):
            for nested_key, nested_val in val.items():
                set_fields[f"{key}.{nested_key}"] = nested_val
        else:
            set_fields[key] = val

    await _tenants_col().update_one(
        {"tenant_id": tenant_id},
        {"$set": set_fields},
    )
    logger.info("Updated tenant: %s", tenant_id)

    return {"tenant_id": tenant_id, "message": "Tenant updated"}


@router.put("/{tenant_id}/config")
async def update_tenant_config(
    tenant_id: str,
    config: TenantConfig,
    current_user=Depends(require_super_user),
):
    """Update tenant behavior config (AI persona, routing, locale, timezone)."""
    await _get_tenant_or_404(tenant_id)

    await _tenants_col().update_one(
        {"tenant_id": tenant_id},
        {"$set": {"config": config.model_dump(), "updated_at": datetime.utcnow()}},
    )
    await log_admin_action(
        action=AdminAction.TENANT_CONFIG_UPDATE,
        actor=current_user,
        tenant_id=tenant_id,
        target_id=tenant_id,
        details={
            "has_ai_persona": bool(config.ai_persona),
            "routing_rules": len(config.default_workflow_routing or {}),
            "timezone": config.timezone,
            "locale": config.locale,
        },
    )
    logger.info("Updated config for tenant: %s", tenant_id)
    return {"tenant_id": tenant_id, "message": "Tenant config updated"}


@router.get("/{tenant_id}/mappings/{connector_type}")
async def get_tenant_mapping(
    tenant_id: str,
    connector_type: str,
    current_user=Depends(require_super_user),
):
    """Get active mapping for a tenant connector (fallback to global mapping)."""
    _ = current_user
    await _get_tenant_or_404(tenant_id)
    ctype = _parse_connector_type_or_400(connector_type)
    mapping = mapping_engine.get_mapping(ctype, tenant_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    scope = "tenant" if mapping.tenant_id == tenant_id else "global"
    return {"scope": scope, "mapping": mapping.model_dump()}


@router.put("/{tenant_id}/mappings/{connector_type}")
async def update_tenant_mapping(
    tenant_id: str,
    connector_type: str,
    body: TenantMappingUpdate,
    current_user=Depends(require_super_user),
):
    """Create and activate a new versioned tenant-specific field mapping."""
    await _get_tenant_or_404(tenant_id)
    ctype = _parse_connector_type_or_400(connector_type)

    mapping = await save_mapping_version(
        tenant_id=tenant_id,
        connector_type=ctype,
        base_payload=body.model_dump(),
    )
    await log_admin_action(
        action=AdminAction.TENANT_MAPPING_UPDATE,
        actor=current_user,
        tenant_id=tenant_id,
        target_id=mapping.mapping_id,
        details={"connector_type": ctype.value, "version": mapping.version},
    )
    return {
        "tenant_id": tenant_id,
        "connector_type": ctype.value,
        "mapping_id": mapping.mapping_id,
        "version": mapping.version,
        "message": "Mapping updated",
    }


@router.get("/{tenant_id}/mappings/{connector_type}/versions")
async def get_tenant_mapping_versions(
    tenant_id: str,
    connector_type: str,
    limit: int = 25,
    current_user=Depends(require_super_user),
):
    """List mapping versions for a tenant connector."""
    _ = current_user
    await _get_tenant_or_404(tenant_id)
    ctype = _parse_connector_type_or_400(connector_type)
    versions = await list_mapping_versions(tenant_id, ctype, limit=limit)
    return {
        "tenant_id": tenant_id,
        "connector_type": ctype.value,
        "versions": versions,
        "total": len(versions),
    }


@router.post("/{tenant_id}/mappings/{connector_type}/rollback/{version}")
async def rollback_tenant_mapping(
    tenant_id: str,
    connector_type: str,
    version: int,
    current_user=Depends(require_super_user),
):
    """Rollback active mapping to a previous version."""
    await _get_tenant_or_404(tenant_id)
    ctype = _parse_connector_type_or_400(connector_type)
    mapping = await rollback_mapping_version(tenant_id, ctype, version)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Mapping version not found")

    await log_admin_action(
        action=AdminAction.TENANT_MAPPING_ROLLBACK,
        actor=current_user,
        tenant_id=tenant_id,
        target_id=mapping.mapping_id,
        details={"connector_type": ctype.value, "version": version},
    )
    return {
        "tenant_id": tenant_id,
        "connector_type": ctype.value,
        "mapping_id": mapping.mapping_id,
        "active_version": mapping.version,
        "message": "Mapping rolled back",
    }


@router.put("/{tenant_id}/status")
async def update_tenant_status(
    tenant_id: str, body: TenantStatusUpdate, current_user=Depends(require_super_user)
):
    """Change tenant status (activate, deactivate, suspend)."""
    await _get_tenant_or_404(tenant_id)

    await _tenants_col().update_one(
        {"tenant_id": tenant_id},
        {"$set": {"status": body.status.value, "updated_at": datetime.utcnow()}},
    )
    logger.info("Tenant %s status → %s", tenant_id, body.status.value)

    return {"tenant_id": tenant_id, "status": body.status.value}


@router.post("/{tenant_id}/users")
async def create_tenant_user(
    tenant_id: str,
    body: TenantUserCreate,
    current_user=Depends(require_super_user),
):
    """Create a user under a tenant (used by onboarding wizard)."""
    await _get_tenant_or_404(tenant_id)
    db = get_database()

    role_value = body.role.value if isinstance(body.role, UserRole) else str(body.role)
    allowed_roles = {UserRole.USER.value, UserRole.AGENT.value, UserRole.COMPANY.value}
    if role_value not in allowed_roles:
        raise HTTPException(status_code=400, detail="Only user, agent, or company roles are allowed")

    if body.username and not body.password:
        raise HTTPException(status_code=400, detail="Password is required when username is provided")

    if await db.users.find_one({"phone": body.phone}, {"_id": 1}):
        raise HTTPException(status_code=409, detail=f"Phone '{body.phone}' is already in use")

    if body.username and await db.users.find_one({"username": body.username}, {"_id": 1}):
        raise HTTPException(status_code=409, detail=f"Username '{body.username}' is already in use")

    user_id = body.user_id or f"{tenant_id}_{role_value}_{int(datetime.utcnow().timestamp())}"
    if await db.users.find_one({"user_id": user_id}, {"_id": 1}):
        raise HTTPException(status_code=409, detail=f"User ID '{user_id}' already exists")

    now = datetime.utcnow()
    doc = {
        "user_id": user_id,
        "phone": body.phone,
        "full_name": body.full_name,
        "role": role_value,
        "tenant_id": tenant_id,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    }
    if body.username:
        doc["username"] = body.username
    if body.password:
        doc["password_hash"] = auth_service.hash_password(body.password)

    await db.users.insert_one(doc)
    logger.info("Created tenant user: tenant=%s user_id=%s role=%s", tenant_id, user_id, role_value)

    return {"tenant_id": tenant_id, "user_id": user_id, "role": role_value, "message": "User created"}


@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    hard: bool = Query(False, description="Permanently remove tenant and all related data"),
    current_user=Depends(require_super_user),
):
    """Delete tenant. Default: soft-delete (suspend). With ?hard=true: permanently remove all data."""
    await _get_tenant_or_404(tenant_id)

    if not hard:
        await _tenants_col().update_one(
            {"tenant_id": tenant_id},
            {"$set": {"status": TenantStatus.SUSPENDED.value, "updated_at": datetime.utcnow()}},
        )
        logger.info("Suspended tenant: %s", tenant_id)
        return {"tenant_id": tenant_id, "status": "suspended", "message": "Tenant suspended"}

    # Hard delete — remove all related data
    db = get_database()
    deleted = {}
    for col_name in (
        "admin_audit_logs", "field_mappings", "sync_events",
        "external_ticket_links", "connector_credentials", "connector_configs",
        "users",
    ):
        result = await db[col_name].delete_many({"tenant_id": tenant_id})
        deleted[col_name] = result.deleted_count

    result = await _tenants_col().delete_one({"tenant_id": tenant_id})
    deleted["tenants"] = result.deleted_count

    logger.info("Hard-deleted tenant %s: %s", tenant_id, deleted)
    return {"tenant_id": tenant_id, "status": "deleted", "message": "Tenant permanently removed", "deleted": deleted}


# ── Admin Group CRUD ──────────────────────────────────────────────────────────

_VALID_SCOPE_VALUES = {ct.value for ct in ConnectorType}


@router.get("/{tenant_id}/admin-groups")
async def list_admin_groups(tenant_id: str, current_user=Depends(require_super_user)):
    """List all admin groups for a tenant."""
    tenant = await _get_tenant_or_404(tenant_id)
    return {"tenant_id": tenant_id, "admin_groups": tenant.get("admin_groups", [])}


@router.post("/{tenant_id}/admin-groups")
async def create_admin_group(
    tenant_id: str, body: AdminGroupCreate, current_user=Depends(require_super_user)
):
    """Add an admin group to a tenant."""
    await _get_tenant_or_404(tenant_id)

    for s in body.connector_scope:
        if s not in _VALID_SCOPE_VALUES:
            raise HTTPException(400, f"Invalid scope value: {s}. Valid: {sorted(_VALID_SCOPE_VALUES)}")

    group_id = body.group_id or f"grp_{uuid.uuid4().hex[:8]}"

    existing = await _tenants_col().find_one(
        {"tenant_id": tenant_id, "admin_groups.group_id": group_id}
    )
    if existing:
        raise HTTPException(409, f"Group '{group_id}' already exists in this tenant")

    group_doc = {
        "group_id": group_id,
        "display_name": body.display_name,
        "connector_scope": body.connector_scope,
        "description": body.description,
        "created_at": datetime.utcnow().isoformat(),
    }

    await _tenants_col().update_one(
        {"tenant_id": tenant_id},
        {"$push": {"admin_groups": group_doc}, "$set": {"updated_at": datetime.utcnow()}},
    )
    logger.info("Created admin group %s for tenant %s", group_id, tenant_id)
    return {"tenant_id": tenant_id, "group": group_doc}


@router.put("/{tenant_id}/admin-groups/{group_id}")
async def update_admin_group(
    tenant_id: str, group_id: str, body: AdminGroupUpdate, current_user=Depends(require_super_user)
):
    """Update an existing admin group."""
    updates = {}
    if body.display_name is not None:
        updates["admin_groups.$.display_name"] = body.display_name
    if body.connector_scope is not None:
        for s in body.connector_scope:
            if s not in _VALID_SCOPE_VALUES:
                raise HTTPException(400, f"Invalid scope value: {s}")
        updates["admin_groups.$.connector_scope"] = body.connector_scope
    if body.description is not None:
        updates["admin_groups.$.description"] = body.description

    if not updates:
        raise HTTPException(400, "No fields to update")

    result = await _tenants_col().update_one(
        {"tenant_id": tenant_id, "admin_groups.group_id": group_id},
        {"$set": {**updates, "updated_at": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Admin group not found")

    logger.info("Updated admin group %s for tenant %s", group_id, tenant_id)
    return {"message": "Admin group updated", "group_id": group_id}


@router.delete("/{tenant_id}/admin-groups/{group_id}")
async def delete_admin_group(
    tenant_id: str, group_id: str, current_user=Depends(require_super_user)
):
    """Remove an admin group. Users in the group become unscoped (see all)."""
    result = await _tenants_col().update_one(
        {"tenant_id": tenant_id},
        {
            "$pull": {"admin_groups": {"group_id": group_id}},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.modified_count == 0:
        raise HTTPException(404, "Admin group not found")

    # Clear admin_group_id from users that referenced this group
    db = get_database()
    await db.users.update_many(
        {"tenant_id": tenant_id, "admin_group_id": group_id},
        {"$unset": {"admin_group_id": ""}},
    )
    logger.info("Deleted admin group %s from tenant %s", group_id, tenant_id)
    return {"message": "Admin group deleted", "group_id": group_id}


@router.put("/{tenant_id}/users/{user_id}/admin-group")
async def assign_user_to_group(
    tenant_id: str,
    user_id: str,
    body: UserGroupAssignment,
    current_user=Depends(require_super_user),
):
    """Assign or unassign a company user to/from an admin group."""
    db = get_database()
    user = await db.users.find_one({"user_id": user_id, "tenant_id": tenant_id})
    if not user:
        raise HTTPException(404, "User not found in this tenant")
    if user.get("role") != "company":
        raise HTTPException(400, "Only company-role users can be assigned to admin groups")

    if body.admin_group_id:
        tenant = await _get_tenant_or_404(tenant_id)
        group_ids = [g.get("group_id") for g in tenant.get("admin_groups", [])]
        if body.admin_group_id not in group_ids:
            raise HTTPException(404, f"Admin group '{body.admin_group_id}' not found in this tenant")

        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"admin_group_id": body.admin_group_id, "updated_at": datetime.utcnow()}},
        )
    else:
        await db.users.update_one(
            {"user_id": user_id},
            {"$unset": {"admin_group_id": ""}, "$set": {"updated_at": datetime.utcnow()}},
        )

    logger.info("Assigned user %s to group %s in tenant %s", user_id, body.admin_group_id, tenant_id)
    return {"user_id": user_id, "admin_group_id": body.admin_group_id}


# ── Seed function ───────────────────────────────────────────────────────────

async def seed_tenants():
    """Ensure default demo tenant documents exist."""
    col = _tenants_col()

    now = datetime.utcnow()
    defaults = [
        Tenant(
            tenant_id="tenant_demo",
            display_name="Cadent Gas Ltd",
            status=TenantStatus.ACTIVE,
            branding=TenantBranding(company_name="Cadent Gas Ltd"),
            admin_groups=[
                AdminGroup(
                    group_id="grp_sn_team",
                    display_name="ServiceNow Team",
                    connector_scope=["servicenow"],
                    description="Manages incidents synced from ServiceNow",
                    created_at=now,
                ),
            ],
            created_at=now,
            updated_at=now,
        ),
    ]

    for tenant in defaults:
        exists = await col.find_one({"tenant_id": tenant.tenant_id}, {"_id": 1})
        if exists:
            # Backfill admin_groups if missing
            if tenant.admin_groups:
                doc = await col.find_one({"tenant_id": tenant.tenant_id}, {"admin_groups": 1})
                if not doc.get("admin_groups"):
                    await col.update_one(
                        {"tenant_id": tenant.tenant_id},
                        {"$set": {"admin_groups": [g.model_dump() for g in tenant.admin_groups]}},
                    )
                    logger.info("Backfilled admin_groups for tenant: %s", tenant.tenant_id)
            continue
        await col.insert_one(tenant.model_dump())
        logger.info("Seeded tenant: %s", tenant.tenant_id)
