"""Workflow execution log models"""
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime


class ExecutionStatus(str):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_INPUT = "waiting_input"
    OVERRIDDEN = "overridden"


class WorkflowExecutionLog(BaseModel):
    log_id: str
    execution_id: str
    workflow_id: str
    tenant_id: str
    incident_id: str
    user_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    current_node: Optional[str] = None
    execution_path: List[Dict[str, Any]] = []
    variables: Dict[str, Any] = {}
    risk_score: Optional[float] = None
    final_decision: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class DecisionOverride(BaseModel):
    override_id: str
    execution_id: str
    incident_id: str
    original_decision: str
    overridden_decision: str
    reason: str
    overridden_by: str
    overridden_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class DecisionOverrideCreate(BaseModel):
    execution_id: str
    incident_id: str
    overridden_decision: str
    reason: str


class ExecutionStats(BaseModel):
    total_executions: int
    completed: int
    failed: int
    overridden: int
    avg_execution_time: float
    avg_risk_score: float
    decision_distribution: Dict[str, int]
    by_use_case: Dict[str, int]
