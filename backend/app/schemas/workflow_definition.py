"""Graph-based workflow definition models."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowNodeType(str, Enum):
    QUESTION = "QUESTION"
    CONDITION = "CONDITION"
    SWITCH = "SWITCH"          # Switch-case routing based on a variable value
    SUB_WORKFLOW = "SUB_WORKFLOW"  # Invoke another workflow and optionally resume parent
    ML_MODEL = "ML_MODEL"
    CALCULATE = "CALCULATE"
    DECISION = "DECISION"
    WAIT = "WAIT"
    PARALLEL = "PARALLEL"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
    TIMER = "TIMER"
    NOTIFICATION = "NOTIFICATION"
    ALERT = "ALERT"
    ESCALATION = "ESCALATION"
    SCRIPT = "SCRIPT"
    DATA_FETCH = "DATA_FETCH"


class WorkflowNode(BaseModel):
    id: str
    type: WorkflowNodeType
    data: Dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    condition: Optional[str] = None


class WorkflowDefinition(BaseModel):
    workflow_id: str
    tenant_id: str
    use_case: str
    version: int = Field(default=1, ge=1)
    version_label: Optional[str] = None
    start_node: str
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
