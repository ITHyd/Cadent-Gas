"""Workflow data models"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from enum import Enum
from datetime import datetime


class NodeType(str, Enum):
    QUESTION = "question"
    CONDITION = "condition"
    ML_MODEL = "ml_model"
    API_CALL = "api_call"
    WAIT = "wait"
    PARALLEL = "parallel"
    HUMAN_OVERRIDE = "human_override"
    DECISION = "decision"
    UPLOAD = "upload"
    CALCULATE = "calculate"


class QuestionType(str, Enum):
    YES_NO = "yes_no"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT = "text"
    NUMBER = "number"


class WorkflowNode(BaseModel):
    node_id: str
    node_type: NodeType
    config: Dict[str, Any]
    next: Union[List[str], Dict[str, str]]
    timeout: Optional[int] = None
    retry_policy: Optional[Dict[str, Any]] = None


class RiskFactor(BaseModel):
    factor_id: str
    name: str
    weight: float = Field(ge=0, le=1)
    source_node: str


class SafetyOverride(BaseModel):
    condition: str
    trigger_node: str
    action: str


class DecisionThresholds(BaseModel):
    emergency: float = 0.8
    schedule_engineer: float = 0.5
    monitor: float = 0.3
    close: float = 0.0


class WorkflowMetadata(BaseModel):
    name: str
    description: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class Workflow(BaseModel):
    workflow_id: str
    tenant_id: str
    use_case: str
    version: str
    metadata: WorkflowMetadata
    nodes: List[WorkflowNode]
    start_node: str
    risk_factors: List[RiskFactor]
    safety_overrides: List[SafetyOverride]
    decision_thresholds: DecisionThresholds


class WorkflowState(BaseModel):
    """Runtime state of workflow execution"""
    execution_id: str
    workflow_id: str
    tenant_id: str
    user_id: str
    current_node: str
    variables: Dict[str, Any] = {}
    risk_scores: Dict[str, float] = {}
    preliminary_risk_score: Optional[float] = None
    final_risk_score: Optional[float] = None
    confidence_score: Optional[float] = None
    status: str = "running"  # running, completed, failed, waiting_input
    created_at: datetime
    updated_at: datetime
    history: List[Dict[str, Any]] = []


class WorkflowExecutionRequest(BaseModel):
    incident_id: str
    tenant_id: str
    user_id: str
    initial_data: Dict[str, Any]


class WorkflowExecutionResponse(BaseModel):
    execution_id: str
    status: str
    current_step: Dict[str, Any]
    message: str
