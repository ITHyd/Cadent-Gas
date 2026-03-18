"""Workflow management API endpoints."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth_dependencies import get_current_user, require_role
from app.models.admin_audit import AdminAction
from app.models.user import UserRole
from app.schemas.workflow_definition import WorkflowDefinition
from app.services.admin_audit_service import log_admin_action
from app.services.workflow_repository import workflow_repository

router = APIRouter()
require_super_user = require_role(UserRole.SUPER_USER, UserRole.ADMIN)


def _is_super(user: dict) -> bool:
    return user.get("role") in (UserRole.SUPER_USER.value, UserRole.ADMIN.value)


def _enforce_tenant_scope(current_user: dict, tenant_id: str) -> None:
    if _is_super(current_user):
        return
    if current_user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")


@router.get("/tenant/{tenant_id}")
async def get_tenant_workflows(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
) -> List[WorkflowDefinition]:
    """Get all workflows for a tenant (tenant-scoped)."""
    _enforce_tenant_scope(current_user, tenant_id)
    return workflow_repository.list_by_tenant(tenant_id)


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
) -> WorkflowDefinition:
    """Get specific workflow definition with tenant authorization."""
    workflow = workflow_repository.get_by_id(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    _enforce_tenant_scope(current_user, workflow.tenant_id)
    return workflow


@router.post("/")
async def create_workflow(
    workflow: WorkflowDefinition,
    current_user: dict = Depends(require_super_user),
) -> WorkflowDefinition:
    """Create new workflow (Super User/Admin only)."""
    try:
        saved = workflow_repository.save(workflow)
        await log_admin_action(
            action=AdminAction.WORKFLOW_CREATE,
            actor=current_user,
            tenant_id=saved.tenant_id,
            target_id=saved.workflow_id,
            details={"version": saved.version, "use_case": saved.use_case},
        )
        return saved
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    workflow: WorkflowDefinition,
    current_user: dict = Depends(require_super_user),
) -> WorkflowDefinition:
    """Update workflow by creating a new version (Super User/Admin only)."""
    try:
        updated = workflow_repository.update(workflow_id, workflow)
        await log_admin_action(
            action=AdminAction.WORKFLOW_UPDATE,
            actor=current_user,
            tenant_id=updated.tenant_id,
            target_id=workflow_id,
            details={"version": updated.version, "use_case": updated.use_case},
        )
        return updated
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{workflow_id}/mermaid")
async def get_workflow_mermaid(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get workflow as Mermaid diagram."""
    workflow = workflow_repository.get_by_id(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    _enforce_tenant_scope(current_user, workflow.tenant_id)

    # Placeholder - implement Mermaid generation from workflow graph
    mermaid = """
graph TD
    A[Start] --> B{Smell Gas?}
    B -->|Yes| C[Intensity?]
    B -->|No| D[Close]
    C --> E[Calculate Risk]
    E --> F{Decision}
    F -->|High| G[Emergency]
    F -->|Medium| H[Schedule]
    F -->|Low| I[Monitor]
    """
    return {"workflow_id": workflow_id, "mermaid": mermaid}
