"""Knowledge Base models"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class TrueIncidentKBBase(BaseModel):
    tenant_id: str
    incident_id: Optional[str] = None
    use_case: str
    description: str
    key_indicators: Dict[str, Any]
    risk_factors: Dict[str, Any]
    outcome: str
    tags: List[str] = []
    metadata: Optional[Dict[str, Any]] = None


class TrueIncidentKBCreate(TrueIncidentKBBase):
    pass


class TrueIncidentKB(TrueIncidentKBBase):
    kb_id: str
    verified_by: str
    verified_at: datetime
    
    class Config:
        from_attributes = True


class FalseIncidentKBBase(BaseModel):
    tenant_id: str
    incident_id: Optional[str] = None
    reported_as: str
    actual_issue: str
    false_positive_reason: str
    key_indicators: Dict[str, Any]
    tags: List[str] = []
    metadata: Optional[Dict[str, Any]] = None


class FalseIncidentKBCreate(FalseIncidentKBBase):
    pass


class FalseIncidentKB(FalseIncidentKBBase):
    kb_id: str
    verified_by: str
    verified_at: datetime
    
    class Config:
        from_attributes = True


class KBSearchQuery(BaseModel):
    query: str
    use_case: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: int = 10


class KBSearchResult(BaseModel):
    kb_id: str
    kb_type: str  # "true" or "false"
    description: str
    relevance_score: float
    key_indicators: Dict[str, Any]
