"""Knowledge Base API endpoints"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from app.core.auth_dependencies import get_current_user, require_role
from app.models.user import UserRole
from app.services.agent_orchestrator import AgentOrchestrator

router = APIRouter()
require_kb_admin = require_role(UserRole.COMPANY, UserRole.SUPER_USER, UserRole.ADMIN)

def get_orchestrator() -> AgentOrchestrator:
    """Get shared orchestrator instance from agents module."""
    from app.api.agents import agent_orchestrator
    return agent_orchestrator


def _resolve_tenant_scope(current_user: Dict[str, Any], tenant_id: Optional[str]) -> Optional[str]:
    """Enforce tenant isolation for KB endpoints."""
    role = current_user.get("role")
    user_tenant = current_user.get("tenant_id")
    if role in (UserRole.SUPER_USER.value, UserRole.ADMIN.value):
        return tenant_id
    if tenant_id and user_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")
    return user_tenant


class TrueIncidentKBEntry(BaseModel):
    use_case: str
    description: str
    key_indicators: Dict[str, Any]
    risk_factors: Dict[str, Any]
    outcome: str
    tags: List[str] = []
    tenant_id: Optional[str] = None


class FalseIncidentKBEntry(BaseModel):
    reported_as: str
    actual_issue: str
    false_positive_reason: str
    key_indicators: Dict[str, Any]
    tags: List[str] = []
    tenant_id: Optional[str] = None


class KBUpdateRequest(BaseModel):
    description: Optional[str] = None
    key_indicators: Optional[Dict[str, Any]] = None
    risk_factors: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    outcome: Optional[str] = None
    reported_as: Optional[str] = None
    actual_issue: Optional[str] = None
    false_positive_reason: Optional[str] = None


@router.get("/stats")
async def get_kb_stats(
    tenant_id: Optional[str] = Query(None),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get Knowledge Base statistics
    
    Args:
        tenant_id: Optional tenant filter
    """
    try:
        scoped_tenant = _resolve_tenant_scope(current_user, tenant_id)
        stats = orchestrator.kb_service.get_kb_stats(scoped_tenant)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/true")
async def get_true_incidents_kb(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: Optional[str] = Query(None),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get paginated true incidents from Knowledge Base
    
    Args:
        page: Page number (1-indexed)
        limit: Items per page
        tenant_id: Optional tenant filter (includes global if specified)
    """
    try:
        scoped_tenant = _resolve_tenant_scope(current_user, tenant_id)
        result = orchestrator.kb_service.get_paginated_true_incidents(
            page=page,
            limit=limit,
            tenant_id=scoped_tenant
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/false")
async def get_false_incidents_kb(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: Optional[str] = Query(None),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get paginated false incidents from Knowledge Base
    
    Args:
        page: Page number (1-indexed)
        limit: Items per page
        tenant_id: Optional tenant filter (includes global if specified)
    """
    try:
        scoped_tenant = _resolve_tenant_scope(current_user, tenant_id)
        result = orchestrator.kb_service.get_paginated_false_incidents(
            page=page,
            limit=limit,
            tenant_id=scoped_tenant
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_kb_entries(
    limit: int = Query(10, ge=1, le=50),
    tenant_id: Optional[str] = Query(None),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get recent KB entries (both true and false)
    
    Args:
        limit: Max number of entries
        tenant_id: Optional tenant filter
    """
    try:
        scoped_tenant = _resolve_tenant_scope(current_user, tenant_id)
        entries = orchestrator.kb_service.get_recent_kb_entries(
            limit=limit,
            tenant_id=scoped_tenant
        )
        return {
            "total": len(entries),
            "entries": entries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/true")
async def add_true_incident_to_kb(
    entry: TrueIncidentKBEntry,
    verified_by: str = Query(..., description="User ID who verified this entry"),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(require_kb_admin),
):
    """
    Manually add verified true incident to Knowledge Base
    
    Requires COMPANY or SUPER_USER role
    """
    try:
        entry_dict = entry.dict()
        entry_dict["tenant_id"] = _resolve_tenant_scope(current_user, entry.tenant_id)
        entry_dict["source"] = "manual"
        entry_dict["verified_by"] = verified_by
        
        kb_id = orchestrator.add_to_true_kb(entry_dict)
        return {
            "kb_id": kb_id,
            "message": "True incident added to KB successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/false")
async def add_false_incident_to_kb(
    entry: FalseIncidentKBEntry,
    verified_by: str = Query(..., description="User ID who verified this entry"),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(require_kb_admin),
):
    """
    Manually add verified false incident to Knowledge Base
    
    Requires COMPANY or SUPER_USER role
    """
    try:
        entry_dict = entry.dict()
        entry_dict["tenant_id"] = _resolve_tenant_scope(current_user, entry.tenant_id)
        entry_dict["source"] = "manual"
        entry_dict["verified_by"] = verified_by
        
        kb_id = orchestrator.add_to_false_kb(entry_dict)
        return {
            "kb_id": kb_id,
            "message": "False incident added to KB successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{kb_type}/{kb_id}")
async def update_kb_entry(
    kb_type: str,
    kb_id: str,
    updates: KBUpdateRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(require_kb_admin),
):
    """
    Update KB entry
    
    Args:
        kb_type: "true" or "false"
        kb_id: KB entry ID
        updates: Fields to update
    
    Requires COMPANY or SUPER_USER role
    """
    if kb_type not in ["true", "false"]:
        raise HTTPException(status_code=400, detail="kb_type must be 'true' or 'false'")
    
    try:
        # Filter out None values
        update_dict = {k: v for k, v in updates.dict().items() if v is not None}
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        _ = current_user
        updated_entry = orchestrator.kb_service.update_kb_entry(
            kb_id=kb_id,
            kb_type=kb_type,
            updates=update_dict
        )
        
        if not updated_entry:
            raise HTTPException(status_code=404, detail=f"KB entry {kb_type}/{kb_id} not found")
        
        return {
            "message": "KB entry updated successfully",
            "entry": updated_entry
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_type}/{kb_id}")
async def delete_kb_entry(
    kb_type: str,
    kb_id: str,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(require_kb_admin),
):
    """
    Delete KB entry
    
    Args:
        kb_type: "true" or "false"
        kb_id: KB entry ID
    
    Requires COMPANY or SUPER_USER role
    """
    if kb_type not in ["true", "false"]:
        raise HTTPException(status_code=400, detail="kb_type must be 'true' or 'false'")
    
    try:
        _ = current_user
        deleted = orchestrator.kb_service.delete_kb_entry(kb_id=kb_id, kb_type=kb_type)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"KB entry {kb_type}/{kb_id} not found")
        
        return {
            "message": "KB entry deleted successfully",
            "kb_id": kb_id,
            "kb_type": kb_type
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_kb(
    query: str = Query(..., min_length=1),
    kb_type: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    tenant_id: Optional[str] = Query(None),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Search Knowledge Base
    
    Args:
        query: Search text
        kb_type: "true" or "false" or None for both
        limit: Max results (default 10)
    """
    try:
        scoped_tenant = _resolve_tenant_scope(current_user, tenant_id)
        results = orchestrator.search_kb(query, kb_type, limit)
        if scoped_tenant:
            results = [r for r in results if r.get("tenant_id") in (None, scoped_tenant)]
        return {
            "query": query,
            "total": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
async def verify_incident_against_kb(
    incident_data: Dict[str, Any],
    use_case: str,
    tenant_id: Optional[str] = Query(None),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Verify an incident against Knowledge Base
    
    Returns similarity scores and confidence adjustment
    """
    try:
        scoped_tenant = _resolve_tenant_scope(current_user, tenant_id)
        if scoped_tenant:
            incident_data = {**incident_data, "tenant_id": scoped_tenant}
        verification = orchestrator.kb_service.verify_incident(
            incident_data=incident_data,
            use_case=use_case
        )
        return verification
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
