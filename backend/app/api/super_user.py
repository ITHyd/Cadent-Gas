"""Super User API endpoints for workflow management and tenant administration"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
import uuid
from datetime import datetime

from app.models.workflow import Workflow, WorkflowNode
from app.models.risk_config import RiskConfiguration, RiskConfigurationCreate, RiskConfigurationUpdate
from app.models.knowledge_base import (
    TrueIncidentKB, TrueIncidentKBCreate,
    FalseIncidentKB, FalseIncidentKBCreate
)
from app.models.execution_log import WorkflowExecutionLog, DecisionOverride, DecisionOverrideCreate, ExecutionStats

from app.core.auth_dependencies import require_role
from app.core.mongodb import get_database
from app.models.user import UserRole

router = APIRouter()

# Real role-based dependency — requires SUPER_USER or ADMIN
require_super_user = require_role(UserRole.SUPER_USER, UserRole.ADMIN)


def _get_orchestrator():
    from app.api.agents import agent_orchestrator
    return agent_orchestrator


def _workflow_to_dict(wf, active_version=None):
    return {
        "workflow_id": wf.workflow_id,
        "tenant_id": wf.tenant_id,
        "use_case": wf.use_case,
        "version": wf.version,
        "version_label": getattr(wf, "version_label", None),
        "is_active": wf.version == active_version if active_version is not None else None,
        "start_node": wf.start_node,
        "nodes": wf.nodes,
        "edges": wf.edges,
        "created_at": wf.created_at.isoformat() if getattr(wf, "created_at", None) else None,
        "updated_at": wf.updated_at.isoformat() if getattr(wf, "updated_at", None) else None,
    }


def _edge_key(edge):
    return (
        edge.source,
        edge.target,
        edge.source_handle,
        edge.target_handle,
        edge.condition,
    )


def _compare_workflows(wf1, wf2):
    nodes1 = {n.id: n for n in (wf1.nodes or [])}
    nodes2 = {n.id: n for n in (wf2.nodes or [])}

    added_nodes = sorted(set(nodes2.keys()) - set(nodes1.keys()))
    removed_nodes = sorted(set(nodes1.keys()) - set(nodes2.keys()))
    changed_nodes = sorted(
        node_id
        for node_id in set(nodes1.keys()) & set(nodes2.keys())
        if nodes1[node_id].type != nodes2[node_id].type
        or nodes1[node_id].data != nodes2[node_id].data
    )

    edges1 = {_edge_key(e) for e in (wf1.edges or [])}
    edges2 = {_edge_key(e) for e in (wf2.edges or [])}
    added_edges = sorted(list(edges2 - edges1))
    removed_edges = sorted(list(edges1 - edges2))

    return {
        "start_node_changed": wf1.start_node != wf2.start_node,
        "nodes_added": added_nodes,
        "nodes_removed": removed_nodes,
        "nodes_changed": changed_nodes,
        "edges_added": added_edges,
        "edges_removed": removed_edges,
    }


# ============================================================================
# TENANT MANAGEMENT
# ============================================================================

@router.get("/tenants")
async def list_tenants(current_user=Depends(require_super_user)):
    """List all tenants with aggregated stats.

    Reads from the `tenants` collection and merges with user/incident/workflow
    aggregation data.  Falls back to user-derived tenant list for any tenant_ids
    that exist in users but not yet in the tenants collection.
    """
    db = get_database()
    orchestrator = _get_orchestrator()

    # 1. Read tenant configs from the tenants collection
    tenant_docs = {}
    async for doc in db.tenants.find({}, {"_id": 0}):
        tenant_docs[doc["tenant_id"]] = doc

    # 2. Aggregate users grouped by tenant_id and role
    pipeline = [
        {"$group": {
            "_id": {"tenant_id": "$tenant_id", "role": "$role"},
            "count": {"$sum": 1},
        }},
    ]
    cursor = db.users.aggregate(pipeline)
    role_counts = {}
    all_tenant_ids = set(tenant_docs.keys())
    async for doc in cursor:
        tid = doc["_id"]["tenant_id"]
        role = doc["_id"]["role"]
        all_tenant_ids.add(tid)
        role_counts.setdefault(tid, {})
        role_counts[tid][role] = doc["count"]

    # 3. Get earliest created_at and latest login per tenant
    tenant_dates = {}
    date_cursor = db.users.aggregate([
        {"$group": {
            "_id": "$tenant_id",
            "earliest": {"$min": "$created_at"},
            "latest_login": {"$max": "$last_login"},
        }},
    ])
    async for doc in date_cursor:
        tenant_dates[doc["_id"]] = {
            "created_at": doc["earliest"].isoformat() if doc.get("earliest") else None,
            "latest_login": doc["latest_login"].isoformat() if doc.get("latest_login") else None,
        }

    # 4. Count auto-provisioned users grouped by tenant + source
    auto_prov_counts: Dict[str, Dict[str, int]] = {}
    async for doc in db.users.aggregate([
        {"$match": {"auto_provisioned": True}},
        {"$group": {
            "_id": {"tenant_id": "$tenant_id", "source": "$provisioned_from"},
            "count": {"$sum": 1},
        }},
    ]):
        tid = doc["_id"]["tenant_id"]
        source = doc["_id"]["source"] or "unknown"
        auto_prov_counts.setdefault(tid, {})[source] = doc["count"]

    from app.services.workflow_repository import workflow_repository

    tenants = []
    for tid in sorted(all_tenant_ids):
        roles = role_counts.get(tid, {})
        total_users = sum(roles.values())

        inc_stats = orchestrator.incident_service.get_incident_stats(tid)
        wf_count = len(workflow_repository.list_by_tenant(tid))

        # Merge tenant config (from tenants collection) with aggregated stats
        tenant_cfg = tenant_docs.get(tid, {})
        branding = tenant_cfg.get("branding", {})

        tenants.append({
            "tenant_id": tid,
            "display_name": tenant_cfg.get("display_name", tid),
            "status": tenant_cfg.get("status", "active"),
            "subdomain": branding.get("subdomain", ""),
            "users": {
                "total": total_users,
                "by_role": roles,
                "auto_provisioned_by_source": auto_prov_counts.get(tid, {}),
            },
            "incidents": {
                "total": inc_stats.get("total", 0),
                "pending": inc_stats.get("pending", 0),
                "dispatched": inc_stats.get("dispatched", 0),
                "resolved": inc_stats.get("resolved", 0),
            },
            "workflows": wf_count,
            "created_at": tenant_dates.get(tid, {}).get("created_at"),
            "latest_login": tenant_dates.get(tid, {}).get("latest_login"),
        })

    return {"tenants": tenants, "total": len(tenants)}


@router.get("/tenants/{tenant_id}")
async def get_tenant_detail(tenant_id: str, current_user=Depends(require_super_user)):
    """Get detailed tenant info: users list, incidents, workflows, agents."""
    db = get_database()
    orchestrator = _get_orchestrator()

    # Users for this tenant
    users_cursor = db.users.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "user_id": 1, "full_name": 1, "phone": 1, "role": 1,
         "is_active": 1, "created_at": 1, "last_login": 1,
         "username": 1, "admin_group_id": 1,
         "auto_provisioned": 1, "provisioned_from": 1},
    )
    users = []
    async for u in users_cursor:
        u["created_at"] = u["created_at"].isoformat() if u.get("created_at") else None
        u["last_login"] = u["last_login"].isoformat() if u.get("last_login") else None
        users.append(u)

    if not users:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # User summary by role
    by_role = {}
    for u in users:
        by_role[u["role"]] = by_role.get(u["role"], 0) + 1

    # Incident stats
    inc_stats = orchestrator.incident_service.get_incident_stats(tenant_id)

    # Recent incidents (last 10)
    all_incidents = [
        inc for inc in orchestrator.incident_service.incidents.values()
        if inc.tenant_id == tenant_id
    ]
    all_incidents.sort(key=lambda x: x.created_at, reverse=True)
    recent_incidents = [
        {
            "incident_id": inc.incident_id,
            "type": inc.incident_type or inc.classified_use_case,
            "status": inc.status.value,
            "risk_score": inc.risk_score,
            "created_at": inc.created_at.isoformat(),
        }
        for inc in all_incidents[:10]
    ]

    # Workflows
    from app.services.workflow_repository import workflow_repository
    workflows = [
        {
            "workflow_id": wf.workflow_id,
            "use_case": wf.use_case,
            "version": wf.version,
            "nodes": len(wf.nodes) if wf.nodes else 0,
        }
        for wf in workflow_repository.list_by_tenant(tenant_id)
    ]

    # Field agents
    agents = [
        {
            "agent_id": a.agent_id,
            "full_name": a.full_name,
            "specialization": a.specialization,
            "is_available": a.is_available,
            "rating": a.rating,
            "total_jobs": a.total_jobs_completed,
        }
        for a in orchestrator.incident_service.get_all_agents()
    ]

    # Tenant config from tenants collection
    tenant_cfg = await db.tenants.find_one({"tenant_id": tenant_id}, {"_id": 0})

    return {
        "tenant_id": tenant_id,
        "display_name": tenant_cfg.get("display_name", tenant_id) if tenant_cfg else tenant_id,
        "status": tenant_cfg.get("status", "active") if tenant_cfg else "active",
        "branding": tenant_cfg.get("branding") if tenant_cfg else None,
        "config": tenant_cfg.get("config") if tenant_cfg else None,
        "contact_email": tenant_cfg.get("contact_email") if tenant_cfg else None,
        "users": users,
        "user_summary": {"total": len(users), "by_role": by_role},
        "incidents": inc_stats,
        "recent_incidents": recent_incidents,
        "workflows": workflows,
        "agents": agents,
    }


# ============================================================================
# WORKFLOW MANAGEMENT
# ============================================================================

@router.get("/workflows")
async def list_workflows(
    tenant_id: Optional[str] = None,
    use_case: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user = Depends(require_super_user)
):
    """List all workflows with optional filters"""
    from app.services.workflow_repository import workflow_repository

    workflows = workflow_repository.list_all()

    if tenant_id:
        workflows = [wf for wf in workflows if wf.tenant_id == tenant_id]
    if use_case:
        workflows = [wf for wf in workflows if wf.use_case == use_case]
    if is_active is not None:
        active_map = {}
        for wf in workflows:
            if wf.workflow_id not in active_map:
                active_map[wf.workflow_id] = workflow_repository.get_active_version(wf.workflow_id)
        if is_active:
            workflows = [wf for wf in workflows if active_map.get(wf.workflow_id) == wf.version]
        else:
            workflows = [wf for wf in workflows if active_map.get(wf.workflow_id) != wf.version]

    payload = [_workflow_to_dict(wf) for wf in workflows]
    return {"workflows": payload, "total": len(payload)}


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """Get workflow details"""
    from app.services.workflow_repository import workflow_repository

    workflow = workflow_repository.get_by_id(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflow_to_dict(workflow)


@router.post("/workflows")
async def create_workflow(
    workflow: Workflow,
    current_user = Depends(require_super_user)
):
    """Create new workflow"""
    workflow_id = str(uuid.uuid4())
    # Placeholder - implement database insert
    return {
        "workflow_id": workflow_id,
        "message": "Workflow created successfully"
    }


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    workflow: Workflow,
    current_user = Depends(require_super_user)
):
    """Update existing workflow"""
    # Placeholder - implement database update
    return {
        "workflow_id": workflow_id,
        "message": "Workflow updated successfully"
    }


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """Delete workflow (soft delete)"""
    # Placeholder - implement soft delete
    return {
        "workflow_id": workflow_id,
        "message": "Workflow deleted successfully"
    }


@router.post("/workflows/{workflow_id}/publish")
async def publish_workflow(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """Publish workflow to production"""
    # Placeholder - implement publish logic
    return {
        "workflow_id": workflow_id,
        "message": "Workflow published successfully",
        "published_at": datetime.utcnow().isoformat()
    }


@router.post("/workflows/{workflow_id}/duplicate")
async def duplicate_workflow(
    workflow_id: str,
    new_name: str,
    current_user = Depends(require_super_user)
):
    """Duplicate existing workflow"""
    new_workflow_id = str(uuid.uuid4())
    # Placeholder - implement duplication
    return {
        "original_workflow_id": workflow_id,
        "new_workflow_id": new_workflow_id,
        "message": "Workflow duplicated successfully"
    }


# ============================================================================
# WORKFLOW VERSIONING
# ============================================================================

@router.get("/workflows/{workflow_id}/versions")
async def list_workflow_versions(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """List all versions of a workflow"""
    from app.services.workflow_repository import workflow_repository

    versions = workflow_repository.list_versions(workflow_id)
    active_version = workflow_repository.get_active_version(workflow_id)
    return {
        "workflow_id": workflow_id,
        "versions": [_workflow_to_dict(wf, active_version=active_version) for wf in versions],
        "active_version": active_version,
        "total": len(versions),
    }


@router.get("/workflows/{workflow_id}/versions/{version}")
async def get_workflow_version(
    workflow_id: str,
    version: int,
    current_user = Depends(require_super_user)
):
    """Get specific workflow version"""
    from app.services.workflow_repository import workflow_repository

    workflow = workflow_repository.get_version(workflow_id, version)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow version not found")
    return _workflow_to_dict(workflow)


@router.post("/workflows/{workflow_id}/versions")
async def create_workflow_version(
    workflow_id: str,
    change_summary: str,
    current_user = Depends(require_super_user)
):
    """Create new version of workflow"""
    from app.services.workflow_repository import workflow_repository

    latest = workflow_repository.get_by_id(workflow_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    new_version = workflow_repository.update(workflow_id, latest)
    return {
        "workflow_id": workflow_id,
        "version": new_version.version,
        "message": "New version created",
        "change_summary": change_summary,
    }


@router.patch("/workflows/{workflow_id}/versions/{version}")
async def rename_workflow_version(
    workflow_id: str,
    version: int,
    payload: dict,
    current_user = Depends(require_super_user)
):
    """Rename workflow version label"""
    from app.services.workflow_repository import workflow_repository

    label = (payload.get("version_label") or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="version_label is required")
    try:
        updated = workflow_repository.rename_version(workflow_id, version, label)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workflow_to_dict(updated)


@router.delete("/workflows/{workflow_id}/versions/{version}")
async def delete_workflow_version(
    workflow_id: str,
    version: int,
    current_user = Depends(require_super_user)
):
    """Delete workflow version"""
    from app.services.workflow_repository import workflow_repository

    try:
        workflow_repository.delete_version(workflow_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"workflow_id": workflow_id, "deleted_version": version}


@router.post("/workflows/{workflow_id}/rollback/{version}")
async def rollback_workflow(
    workflow_id: str,
    version: int,
    current_user = Depends(require_super_user)
):
    """Rollback workflow to specific version"""
    from app.services.workflow_repository import workflow_repository

    try:
        new_version = workflow_repository.rollback_to_version(workflow_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "workflow_id": workflow_id,
        "rolled_back_to": version,
        "new_version": new_version.version,
        "message": "Workflow rolled back successfully",
    }


@router.post("/workflows/{workflow_id}/versions/{version}/activate")
async def activate_workflow_version(
    workflow_id: str,
    version: int,
    current_user=Depends(require_super_user),
):
    """Set a specific version as the active version for chatbot execution"""
    from app.services.workflow_repository import workflow_repository

    try:
        activated = workflow_repository.activate_version(workflow_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "workflow_id": workflow_id,
        "activated_version": version,
        "message": f"Version {version} is now active",
    }


@router.get("/workflows/{workflow_id}/compare/{v1}/{v2}")
async def compare_workflow_versions(
    workflow_id: str,
    v1: int,
    v2: int,
    current_user = Depends(require_super_user)
):
    """Compare two workflow versions"""
    from app.services.workflow_repository import workflow_repository

    wf1 = workflow_repository.get_version(workflow_id, v1)
    wf2 = workflow_repository.get_version(workflow_id, v2)
    if wf1 is None or wf2 is None:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    differences = _compare_workflows(wf1, wf2)
    return {
        "workflow_id": workflow_id,
        "version_1": v1,
        "version_2": v2,
        "differences": differences,
    }


# ============================================================================
# WORKFLOW NODES
# ============================================================================

@router.get("/workflows/{workflow_id}/nodes")
async def list_workflow_nodes(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """List all nodes in workflow"""
    # Placeholder
    return {"nodes": []}


@router.post("/workflows/{workflow_id}/nodes")
async def add_workflow_node(
    workflow_id: str,
    node: WorkflowNode,
    current_user = Depends(require_super_user)
):
    """Add node to workflow"""
    # Placeholder
    return {"node_id": str(uuid.uuid4())}


@router.put("/workflows/{workflow_id}/nodes/{node_id}")
async def update_workflow_node(
    workflow_id: str,
    node_id: str,
    node: WorkflowNode,
    current_user = Depends(require_super_user)
):
    """Update workflow node"""
    # Placeholder
    return {"node_id": node_id}


@router.delete("/workflows/{workflow_id}/nodes/{node_id}")
async def delete_workflow_node(
    workflow_id: str,
    node_id: str,
    current_user = Depends(require_super_user)
):
    """Delete workflow node"""
    # Placeholder
    return {"node_id": node_id}


@router.post("/workflows/{workflow_id}/validate")
async def validate_workflow(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """Validate workflow structure"""
    # Placeholder - implement validation
    return {
        "valid": True,
        "errors": [],
        "warnings": []
    }


# ============================================================================
# RISK CONFIGURATION
# ============================================================================

@router.get("/risk-config/{tenant_id}")
async def get_risk_configuration(
    tenant_id: str,
    current_user = Depends(require_super_user)
):
    """Get risk configuration for tenant"""
    # Placeholder
    return {}


@router.put("/risk-config/{tenant_id}")
async def update_risk_configuration(
    tenant_id: str,
    config: RiskConfigurationUpdate,
    current_user = Depends(require_super_user)
):
    """Update risk configuration"""
    # Placeholder
    return {"message": "Risk configuration updated"}


# ============================================================================
# KNOWLEDGE BASE
# ============================================================================

@router.get("/kb/true-incidents")
async def list_true_incidents(
    tenant_id: Optional[str] = None,
    use_case: Optional[str] = None,
    limit: int = 50,
    current_user = Depends(require_super_user)
):
    """List true incident KB entries"""
    # Placeholder
    return {"entries": [], "total": 0}


@router.post("/kb/true-incidents")
async def create_true_incident(
    entry: TrueIncidentKBCreate,
    current_user = Depends(require_super_user)
):
    """Create true incident KB entry"""
    kb_id = str(uuid.uuid4())
    # Placeholder
    return {"kb_id": kb_id}


@router.get("/kb/false-incidents")
async def list_false_incidents(
    tenant_id: Optional[str] = None,
    limit: int = 50,
    current_user = Depends(require_super_user)
):
    """List false incident KB entries"""
    # Placeholder
    return {"entries": [], "total": 0}


@router.post("/kb/false-incidents")
async def create_false_incident(
    entry: FalseIncidentKBCreate,
    current_user = Depends(require_super_user)
):
    """Create false incident KB entry"""
    kb_id = str(uuid.uuid4())
    # Placeholder
    return {"kb_id": kb_id}


# ============================================================================
# EXECUTION LOGS & MONITORING
# ============================================================================

@router.get("/executions")
async def list_executions(
    tenant_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    current_user = Depends(require_super_user)
):
    """List workflow executions"""
    # Placeholder
    return {"executions": [], "total": 0}


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    current_user = Depends(require_super_user)
):
    """Get execution details"""
    # Placeholder
    return {}


@router.get("/executions/{execution_id}/logs")
async def get_execution_logs(
    execution_id: str,
    current_user = Depends(require_super_user)
):
    """Get detailed execution logs"""
    # Placeholder
    return {"logs": []}


@router.get("/executions/stats")
async def get_execution_stats(
    tenant_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user = Depends(require_super_user)
):
    """Get execution statistics"""
    # Placeholder
    return {}


@router.post("/executions/{execution_id}/override")
async def override_decision(
    execution_id: str,
    override: DecisionOverrideCreate,
    current_user = Depends(require_super_user)
):
    """Override workflow decision"""
    override_id = str(uuid.uuid4())
    # Placeholder
    return {
        "override_id": override_id,
        "message": "Decision overridden successfully"
    }


# ============================================================================
# WORKFLOW VISUALIZATION
# ============================================================================

@router.get("/workflows/{workflow_id}/mermaid")
async def get_workflow_mermaid(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """Get Mermaid diagram for workflow"""
    # Placeholder - implement Mermaid generation
    mermaid = """
graph TD
    A[Start] --> B{Condition}
    B -->|Yes| C[Action]
    B -->|No| D[End]
    """
    return {"mermaid": mermaid}


@router.get("/workflows/{workflow_id}/graph")
async def get_workflow_graph(
    workflow_id: str,
    current_user = Depends(require_super_user)
):
    """Get graph data for React Flow"""
    # Placeholder - implement graph data generation
    return {
        "nodes": [],
        "edges": []
    }


@router.post("/workflows/{workflow_id}/preview")
async def preview_workflow_execution(
    workflow_id: str,
    test_data: dict,
    current_user = Depends(require_super_user)
):
    """Preview workflow execution with test data"""
    # Placeholder - implement preview
    return {
        "execution_path": [],
        "risk_score": 0.5,
        "final_decision": "schedule_engineer"
    }
