"""Risk configuration models"""
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime


class RiskFactor(BaseModel):
    factor_id: str
    name: str
    description: str
    weight: float = Field(ge=0, le=1)
    calculation_method: str
    source_node: str


class RiskThresholds(BaseModel):
    emergency: float = 0.8
    schedule_engineer: float = 0.5
    monitor: float = 0.3
    close: float = 0.0


class SafetyOverride(BaseModel):
    override_id: str
    name: str
    condition: str
    action: str
    priority: int
    enabled: bool = True


class RiskConfiguration(BaseModel):
    config_id: str
    tenant_id: str
    workflow_id: Optional[str] = None
    risk_factors: List[RiskFactor]
    thresholds: RiskThresholds
    safety_overrides: List[SafetyOverride]
    version: int
    created_by: str
    created_at: datetime
    is_active: bool = True
    
    class Config:
        from_attributes = True


class RiskConfigurationCreate(BaseModel):
    tenant_id: str
    workflow_id: Optional[str] = None
    risk_factors: List[RiskFactor]
    thresholds: RiskThresholds
    safety_overrides: List[SafetyOverride]


class RiskConfigurationUpdate(BaseModel):
    risk_factors: Optional[List[RiskFactor]] = None
    thresholds: Optional[RiskThresholds] = None
    safety_overrides: Optional[List[SafetyOverride]] = None
