"""Workflow execution engine for graph-based workflow definitions."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.workflow_definition import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
)
from app.services.workflow_repository import workflow_repository

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowCallFrame(BaseModel):
    parent_workflow_id: str
    parent_workflow_version: int
    parent_node_id: str
    result_prefix: str


class WorkflowExecutionState(BaseModel):
    execution_id: str
    workflow_id: str
    workflow_version: int
    tenant_id: str
    current_node: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    is_complete: bool = False
    call_stack: List[WorkflowCallFrame] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class WorkflowEngine:
    """Executes graph-based workflow nodes and manages in-memory execution state."""

    def __init__(self):
        self.workflow_repository = workflow_repository
        self.active_executions: Dict[str, WorkflowExecutionState] = {}
        self._execution_workflows: Dict[str, WorkflowDefinition] = {}

    async def start_execution(
        self, workflow_id: str, tenant_id: str, *_: Any, **__: Any
    ) -> WorkflowExecutionState:
        """
        Start a new workflow execution.

        Required signature:
            start_execution(workflow_id: str, tenant_id: str)
        """
        if not isinstance(workflow_id, str):
            # Compatibility for legacy callers that still pass a Workflow object.
            legacy_workflow = workflow_id
            self._ensure_legacy_workflow_in_repository(legacy_workflow, tenant_id)
            workflow_id = getattr(legacy_workflow, "workflow_id")
            tenant_id = getattr(legacy_workflow, "tenant_id", tenant_id)

        workflow = self.workflow_repository.get_by_id(workflow_id)
        if workflow is None or workflow.tenant_id != tenant_id:
            raise ValueError(
                f"Workflow '{workflow_id}' not found for tenant '{tenant_id}'"
            )

        execution_id = str(uuid.uuid4())
        state = WorkflowExecutionState(
            execution_id=execution_id,
            workflow_id=workflow.workflow_id,
            workflow_version=workflow.version,
            tenant_id=tenant_id,
            current_node=workflow.start_node,
            variables={},
            is_complete=False,
        )

        self.active_executions[execution_id] = state
        self._execution_workflows[execution_id] = workflow
        logger.info("Started workflow execution: %s", execution_id)
        return state

    async def continue_execution(
        self, execution_id: str, user_input: Optional[str]
    ) -> Dict[str, Any]:
        """Continue a running execution by processing the current graph node."""
        state = self.active_executions.get(execution_id)
        if state is None:
            raise ValueError(f"Execution '{execution_id}' not found")

        workflow = self._execution_workflows.get(execution_id)
        if workflow is None:
            raise ValueError(f"Workflow for execution '{execution_id}' not found")

        if state.is_complete:
            return self._build_response(
                state=state,
                action="complete",
                message="Workflow already complete",
                data={},
            )

        normalized_input = self._normalize_input(user_input)
        return await self._process_current_node(state, workflow, normalized_input)

    async def execute_node(
        self,
        execution_id: str,
        workflow: Optional[Any] = None,
        user_input: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Compatibility wrapper for legacy callers.

        Current graph execution path uses continue_execution(execution_id, user_input).
        """
        if execution_id not in self.active_executions:
            raise ValueError(f"Execution '{execution_id}' not found")

        normalized_input = self._extract_input_from_payload(user_input)
        return await self.continue_execution(execution_id, normalized_input)

    async def _process_current_node(
        self,
        state: WorkflowExecutionState,
        workflow: WorkflowDefinition,
        user_input: Optional[str],
    ) -> Dict[str, Any]:
        max_hops = 100
        hops = 0

        while hops < max_hops:
            hops += 1
            node = self._get_node(workflow, state.current_node)
            if node is None:
                raise ValueError(
                    f"Node '{state.current_node}' not found in workflow '{workflow.workflow_id}'"
                )

            if node.type == WorkflowNodeType.QUESTION:
                question = str(
                    node.data.get("question", node.data.get("question_text", ""))
                )
                variable_name = node.data.get("variable") or node.id
                options = node.data.get("options", [])  # Extract options from node data

                if user_input is None:
                    state.updated_at = _utc_now()
                    resp_data = {
                        "node_id": node.id,
                        "question": question,
                        "options": options,  # Include options in response
                    }
                    # Forward the expected input_type (e.g. "image") so the
                    # orchestrator knows to accept media uploads as valid
                    # answers instead of matching them against option labels.
                    node_input_type = node.data.get("input_type")
                    if node_input_type:
                        resp_data["input_type"] = node_input_type
                    return self._build_response(
                        state=state,
                        action="question",
                        message=question,
                        data=resp_data,
                    )

                if variable_name:
                    state.variables[str(variable_name)] = user_input

                # Score accumulation for scored options
                if options and user_input:
                    match_result = self._extract_score_for_answer(user_input, options)
                    if match_result is not None:
                        matched_score, score_op = match_result
                        score_var = f"{variable_name}_score" if variable_name else f"{node.id}_score"
                        state.variables[score_var] = matched_score
                        current_total = state.variables.get("total_score", 0)
                        if score_op == "subtract":
                            state.variables["total_score"] = current_total - matched_score
                        elif score_op == "multiply":
                            state.variables["total_score"] = current_total * matched_score
                        else:
                            state.variables["total_score"] = current_total + matched_score
                        logger.info(
                            "Score accumulated: %s=%s (op=%s), total_score=%s",
                            score_var, matched_score, score_op, state.variables["total_score"],
                        )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    user_input = None
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                user_input = None
                continue

            if node.type == WorkflowNodeType.CONDITION:
                expression = str(node.data.get("expression", "False"))
                condition_result = self._evaluate_expression(expression, state.variables)
                next_node = self._resolve_condition_target(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                    condition_result=condition_result,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.SWITCH:
                # Switch-case: evaluate the variable and follow the matching edge.
                # Edges use condition like "value == 'FireAngel'" or "default".
                variable = node.data.get("variable", "")
                value = state.variables.get(variable, "")
                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables={**state.variables, "__switch_value__": value},
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.SUB_WORKFLOW:
                sub_workflow = self._resolve_subworkflow(node=node, state=state)
                result_prefix = str(
                    node.data.get("result_prefix")
                    or node.data.get("output_prefix")
                    or node.id
                )
                state.call_stack.append(
                    WorkflowCallFrame(
                        parent_workflow_id=workflow.workflow_id,
                        parent_workflow_version=workflow.version,
                        parent_node_id=node.id,
                        result_prefix=result_prefix,
                    )
                )
                state.variables[f"{result_prefix}_invoked"] = True
                state.variables[f"{result_prefix}_target_workflow_id"] = sub_workflow.workflow_id
                state.workflow_id = sub_workflow.workflow_id
                state.workflow_version = sub_workflow.version
                state.current_node = sub_workflow.start_node
                state.updated_at = _utc_now()
                self._execution_workflows[state.execution_id] = sub_workflow
                workflow = sub_workflow
                user_input = None
                logger.info(
                    "SUB_WORKFLOW node '%s': entered '%s' (return prefix=%s)",
                    node.id,
                    sub_workflow.workflow_id,
                    result_prefix,
                )
                continue

            if node.type == WorkflowNodeType.DECISION:
                outcome = node.data.get("outcome")
                decision_message = node.data.get("message")
                completion_response = self._complete_current_path(
                    state=state,
                    workflow=workflow,
                    completed_node_id=node.id,
                    message=str(decision_message or outcome or "Workflow complete"),
                    data={
                        "outcome": outcome,
                        "decision_message": decision_message,
                    },
                )
                if completion_response is not None:
                    return completion_response
                workflow = self._execution_workflows[state.execution_id]
                continue

            if node.type == WorkflowNodeType.CALCULATE:
                # Execute calculation and store result in variables
                calculation = str(node.data.get("calculation", ""))
                result_variable = node.data.get("result_variable")
                
                if calculation and result_variable:
                    try:
                        # Execute the calculation in a safe environment
                        local_vars = dict(state.variables)
                        safe_builtins = {
                            "min": min, "max": max, "abs": abs,
                            "int": int, "float": float, "round": round,
                            "len": len, "sum": sum, "bool": bool,
                            "str": str, "True": True, "False": False,
                            "None": None,
                        }
                        exec(calculation, {"__builtins__": safe_builtins}, local_vars)
                        
                        # Store the result
                        if result_variable in local_vars:
                            state.variables[result_variable] = local_vars[result_variable]
                            logger.info(f"CALCULATE node '{node.id}': {result_variable} = {local_vars[result_variable]}")
                    except Exception as e:
                        logger.error(f"Error executing calculation in node '{node.id}': {e}")
                        # Continue anyway, don't fail the workflow
                
                # Move to next node
                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.ML_MODEL:
                model_name = node.data.get("model_name", "unknown")
                input_vars = node.data.get("input_variables", [])
                output_var = node.data.get("output_variable", f"{node.id}_result")

                # Gather inputs from workflow variables
                model_inputs = {}
                for var in input_vars:
                    model_inputs[var] = state.variables.get(var)

                # Placeholder prediction — replace with real ML inference later
                prediction = f"prediction_from_{model_name}"
                state.variables[output_var] = prediction
                state.variables[f"{node.id}_inputs"] = model_inputs
                logger.info(
                    "ML_MODEL node '%s': %s = %s (inputs: %s)",
                    node.id, output_var, prediction, model_inputs,
                )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.WAIT:
                wait_condition = node.data.get("wait_condition", "Waiting...")
                timeout = node.data.get("timeout")
                timeout_action = node.data.get("timeout_action", "continue")

                if user_input is None:
                    # Pause execution and present wait condition to user
                    state.updated_at = _utc_now()
                    return self._build_response(
                        state=state,
                        action="question",
                        message=wait_condition,
                        data={
                            "node_id": node.id,
                            "question": wait_condition,
                            "wait_node": True,
                            "timeout": timeout,
                            "timeout_action": timeout_action,
                            "options": ["Continue", "Skip"],
                        },
                    )

                # User responded — store response and move on
                state.variables[f"{node.id}_response"] = user_input

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    user_input = None
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                user_input = None
                continue

            if node.type == WorkflowNodeType.PARALLEL:
                merge_strategy = node.data.get("merge_strategy", "all")
                state.variables[f"{node.id}_merge_strategy"] = merge_strategy
                logger.info(
                    "PARALLEL node '%s': strategy=%s (following first branch)",
                    node.id, merge_strategy,
                )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.HUMAN_OVERRIDE:
                instruction = node.data.get(
                    "override_instruction", "Manual review required"
                )
                role = node.data.get("assigned_role", "operator")

                if user_input is None:
                    # Pause execution and present override prompt to user
                    state.updated_at = _utc_now()
                    return self._build_response(
                        state=state,
                        action="question",
                        message=f"[{role}] {instruction}",
                        data={
                            "node_id": node.id,
                            "question": instruction,
                            "human_override": True,
                            "assigned_role": role,
                            "options": ["Approve", "Reject", "Override"],
                        },
                    )

                # Store human decision and move on
                state.variables[f"{node.id}_decision"] = user_input
                state.variables[f"{node.id}_role"] = role

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    user_input = None
                    continue

                state.current_node = next_node
                state.updated_at = _utc_now()
                user_input = None
                continue

            if node.type == WorkflowNodeType.TIMER:
                duration = node.data.get("duration", 0)
                timer_label = node.data.get("timer_label", "Timer")
                timeout_action = node.data.get("timeout_action", "continue")

                state.variables[f"{node.id}_duration"] = duration
                state.variables[f"{node.id}_timer_label"] = timer_label
                state.variables[f"{node.id}_timeout_action"] = timeout_action
                logger.info(
                    "TIMER node '%s': label=%s, duration=%ss, action=%s",
                    node.id, timer_label, duration, timeout_action,
                )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue
                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.NOTIFICATION:
                message = node.data.get("notification_message") or node.data.get("message", "")
                channel = node.data.get("channel") or node.data.get("notification_type", "in_app")
                recipient = node.data.get("recipient")
                if recipient is None:
                    recipients = node.data.get("recipients", [])
                    if isinstance(recipients, list):
                        recipient = ", ".join(str(item) for item in recipients if item)
                    else:
                        recipient = recipients or ""

                state.variables[f"{node.id}_notification"] = {
                    "message": message,
                    "channel": channel,
                    "recipient": recipient,
                }
                logger.info(
                    "NOTIFICATION node '%s': channel=%s, recipient=%s",
                    node.id, channel, recipient,
                )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue
                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.ALERT:
                alert_message = node.data.get("alert_message", "")
                severity = node.data.get("severity", "medium")
                alert_type = node.data.get("alert_type", "")

                state.variables[f"{node.id}_alert"] = {
                    "message": alert_message,
                    "severity": severity,
                    "alert_type": alert_type,
                }
                logger.info(
                    "ALERT node '%s': severity=%s, type=%s",
                    node.id, severity, alert_type,
                )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue
                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.ESCALATION:
                reason = node.data.get("escalation_reason") or node.data.get("reason", "Escalation required")
                level = node.data.get("escalation_level", 1)
                target_role = node.data.get("target_role") or node.data.get("escalation_to", "supervisor")

                if user_input is None:
                    state.updated_at = _utc_now()
                    return self._build_response(
                        state=state,
                        action="question",
                        message=f"[Escalation L{level} -> {target_role}] {reason}",
                        data={
                            "node_id": node.id,
                            "question": reason,
                            "escalation": True,
                            "escalation_level": level,
                            "target_role": target_role,
                            "options": ["Acknowledge", "Reassign", "Override"],
                        },
                    )

                state.variables[f"{node.id}_response"] = user_input
                state.variables[f"{node.id}_level"] = level

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    user_input = None
                    continue
                state.current_node = next_node
                state.updated_at = _utc_now()
                user_input = None
                continue

            if node.type == WorkflowNodeType.SCRIPT:
                script_code = str(node.data.get("script_code", ""))
                output_variables = node.data.get("output_variables", "")

                if script_code:
                    try:
                        local_vars = dict(state.variables)
                        safe_builtins = {
                            "min": min, "max": max, "abs": abs,
                            "int": int, "float": float, "round": round,
                            "len": len, "sum": sum, "bool": bool,
                            "str": str, "True": True, "False": False,
                            "None": None,
                        }
                        exec(script_code, {"__builtins__": safe_builtins}, local_vars)

                        output_names = [
                            v.strip() for v in output_variables.split(",") if v.strip()
                        ]
                        for var_name in output_names:
                            if var_name in local_vars:
                                state.variables[var_name] = local_vars[var_name]
                        logger.info(
                            "SCRIPT node '%s': stored outputs %s",
                            node.id, output_names,
                        )
                    except Exception as e:
                        logger.error(
                            "Error executing script in node '%s': %s", node.id, e
                        )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue
                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            if node.type == WorkflowNodeType.DATA_FETCH:
                source_name = node.data.get("source_name", "unknown")
                endpoint = node.data.get("endpoint", "")
                query_params = node.data.get("query_params", "")
                output_variable = node.data.get(
                    "output_variable", f"{node.id}_result"
                )

                fetch_result = f"data_from_{source_name}"
                state.variables[output_variable] = fetch_result
                state.variables[f"{node.id}_source"] = {
                    "source_name": source_name,
                    "endpoint": endpoint,
                    "query_params": query_params,
                }
                logger.info(
                    "DATA_FETCH node '%s': %s = %s (source: %s)",
                    node.id, output_variable, fetch_result, source_name,
                )

                next_node = self._resolve_next_node(
                    workflow=workflow,
                    current_node=node.id,
                    variables=state.variables,
                )
                if next_node is None:
                    completion_response = self._complete_current_path(
                        state=state,
                        workflow=workflow,
                        completed_node_id=node.id,
                        message="Workflow complete",
                        data={},
                    )
                    if completion_response is not None:
                        return completion_response
                    workflow = self._execution_workflows[state.execution_id]
                    continue
                state.current_node = next_node
                state.updated_at = _utc_now()
                continue

            # Unhandled node types are traversed by graph edges only.
            next_node = self._resolve_next_node(
                workflow=workflow,
                current_node=node.id,
                variables=state.variables,
            )
            if next_node is None:
                completion_response = self._complete_current_path(
                    state=state,
                    workflow=workflow,
                    completed_node_id=node.id,
                    message="Workflow complete",
                    data={},
                )
                if completion_response is not None:
                    return completion_response
                workflow = self._execution_workflows[state.execution_id]
                continue

            state.current_node = next_node
            state.updated_at = _utc_now()

        raise ValueError(f"Execution '{state.execution_id}' exceeded max graph hops")

    def _resolve_next_node(
        self,
        workflow: WorkflowDefinition,
        current_node: str,
        variables: Dict[str, Any],
    ) -> Optional[str]:
        edges = self._get_outgoing_edges(workflow, current_node)
        first_unconditional: Optional[str] = None

        for edge in edges:
            if edge.condition is None:
                if first_unconditional is None:
                    first_unconditional = edge.target
                continue

            if self._evaluate_expression(edge.condition, variables):
                return edge.target

        return first_unconditional

    def _resolve_condition_target(
        self,
        workflow: WorkflowDefinition,
        current_node: str,
        variables: Dict[str, Any],
        condition_result: bool,
    ) -> Optional[str]:
        edges = self._get_outgoing_edges(workflow, current_node)

        for edge in edges:
            if edge.condition is None:
                continue
            normalized = edge.condition.strip().lower()
            if normalized in {"true", "false"}:
                expected = normalized == "true"
                if expected == condition_result:
                    return edge.target

        eval_variables = {
            **variables,
            "condition_result": condition_result,
            "result": condition_result,
        }
        for edge in edges:
            if edge.condition is None:
                continue
            normalized = edge.condition.strip().lower()
            if normalized in {"true", "false"}:
                continue
            if self._evaluate_expression(edge.condition, eval_variables):
                return edge.target

        for edge in edges:
            if edge.condition is None:
                return edge.target

        return None

    def _get_node(
        self, workflow: WorkflowDefinition, node_id: str
    ) -> Optional[WorkflowNode]:
        for node in workflow.nodes:
            if node.id == node_id:
                return node
        return None

    def _get_outgoing_edges(
        self, workflow: WorkflowDefinition, node_id: str
    ) -> List[WorkflowEdge]:
        return [edge for edge in workflow.edges if edge.source == node_id]

    def _evaluate_expression(self, expression: str, variables: Dict[str, Any]) -> bool:
        try:
            rendered_expression = expression
            for key, value in variables.items():
                rendered_expression = rendered_expression.replace(
                    f"{{{{{key}}}}}", repr(value)
                )

            return bool(
                eval(rendered_expression, {"__builtins__": {}}, dict(variables))
            )
        except Exception as exc:
            logger.warning("Expression evaluation failed for '%s': %s", expression, exc)
            return False

    def _build_response(
        self,
        state: WorkflowExecutionState,
        action: str,
        message: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "execution_id": state.execution_id,
            "workflow_id": state.workflow_id,
            "workflow_version": state.workflow_version,
            "current_node": state.current_node,
            "variables": state.variables,
            "is_complete": state.is_complete,
            "action": action,
            "message": message,
            "data": data,
        }

    def _complete_current_path(
        self,
        state: WorkflowExecutionState,
        workflow: WorkflowDefinition,
        completed_node_id: str,
        message: str,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        outcome = data.get("outcome")
        completion_data = dict(data)
        completion_message = message

        while state.call_stack:
            frame = state.call_stack.pop()
            self._store_subworkflow_result(
                state=state,
                frame=frame,
                completed_workflow=workflow,
                message=completion_message,
                data=completion_data,
            )
            parent_workflow = self._get_workflow_version(
                workflow_id=frame.parent_workflow_id,
                version=frame.parent_workflow_version,
            )
            self._execution_workflows[state.execution_id] = parent_workflow
            state.workflow_id = parent_workflow.workflow_id
            state.workflow_version = parent_workflow.version

            next_node = self._resolve_next_node(
                workflow=parent_workflow,
                current_node=frame.parent_node_id,
                variables=state.variables,
            )
            if next_node is not None:
                state.current_node = next_node
                state.updated_at = _utc_now()
                return None

            workflow = parent_workflow
            completion_data = {
                **completion_data,
                "outcome": outcome,
                "decision_message": completion_message,
            }

        state.is_complete = True
        state.updated_at = _utc_now()
        return self._build_response(
            state=state,
            action="complete",
            message=completion_message,
            data=completion_data,
        )

    def _store_subworkflow_result(
        self,
        state: WorkflowExecutionState,
        frame: WorkflowCallFrame,
        completed_workflow: WorkflowDefinition,
        message: str,
        data: Dict[str, Any],
    ) -> None:
        outcome = data.get("outcome")
        prefix = frame.result_prefix
        state.variables[f"{prefix}_completed"] = True
        state.variables[f"{prefix}_workflow_id"] = completed_workflow.workflow_id
        state.variables[f"{prefix}_workflow_version"] = completed_workflow.version
        state.variables[f"{prefix}_message"] = message
        if outcome is not None:
            state.variables[f"{prefix}_outcome"] = outcome
            state.variables["last_subworkflow_outcome"] = outcome
        state.variables["last_subworkflow_message"] = message
        state.variables["last_subworkflow_workflow_id"] = completed_workflow.workflow_id

        for key, value in data.items():
            if key in {"outcome", "decision_message"}:
                continue
            state.variables[f"{prefix}_{key}"] = value

    def _resolve_subworkflow(
        self,
        node: WorkflowNode,
        state: WorkflowExecutionState,
    ) -> WorkflowDefinition:
        workflow_id = node.data.get("workflow_id")
        workflow_id_template = node.data.get("workflow_id_template")
        use_case = node.data.get("use_case")

        if workflow_id_template:
            workflow_id = self._render_template_string(
                str(workflow_id_template),
                state.variables,
            )

        workflow: Optional[WorkflowDefinition] = None
        if workflow_id:
            workflow = self.workflow_repository.get_by_id(str(workflow_id))
        elif use_case:
            workflow = self.workflow_repository.get_latest_by_tenant_use_case(
                state.tenant_id,
                str(use_case),
            )

        if workflow is None:
            raise ValueError(
                f"Sub-workflow not found for node '{node.id}' "
                f"(workflow_id={workflow_id!r}, use_case={use_case!r})"
            )
        if workflow.tenant_id != state.tenant_id:
            raise ValueError(
                f"Sub-workflow '{workflow.workflow_id}' does not belong to tenant '{state.tenant_id}'"
            )
        return workflow

    def _render_template_string(
        self,
        template: str,
        variables: Dict[str, Any],
    ) -> str:
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def _get_workflow_version(
        self,
        workflow_id: str,
        version: int,
    ) -> WorkflowDefinition:
        workflow = self.workflow_repository.get_version(workflow_id, version)
        if workflow is None:
            raise ValueError(
                f"Workflow '{workflow_id}' version '{version}' not found"
            )
        return workflow

    def _extract_score_for_answer(
        self, user_input: str, options: list
    ) -> Optional[tuple]:
        """Return (score, operation) for the matched option, or None for plain string options.

        operation is one of: 'add' (default), 'subtract', 'multiply'.
        """
        if not options:
            return None

        first = options[0]
        if not isinstance(first, dict) or "score" not in first:
            return None

        normalized_input = user_input.strip().lower()
        for opt in options:
            if not isinstance(opt, dict):
                continue
            label = str(opt.get("label", "")).strip().lower()
            if label == normalized_input:
                return (opt.get("score", 0), opt.get("operation", "add"))

        # Fuzzy fallback: partial match
        for opt in options:
            if not isinstance(opt, dict):
                continue
            label = str(opt.get("label", "")).strip().lower()
            if label in normalized_input or normalized_input in label:
                return (opt.get("score", 0), opt.get("operation", "add"))

        return None

    def _normalize_input(self, user_input: Optional[str]) -> Optional[str]:
        if user_input is None:
            return None
        normalized = user_input.strip()
        return normalized if normalized else None

    def _extract_input_from_payload(
        self, user_input: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        if user_input is None:
            return None
        if isinstance(user_input, str):
            return self._normalize_input(user_input)
        if not isinstance(user_input, dict):
            return self._normalize_input(str(user_input))

        for key in ("answer", "text", "input", "message", "value"):
            value = user_input.get(key)
            if isinstance(value, str):
                return self._normalize_input(value)

        return self._normalize_input(json.dumps(user_input, default=str))

    def _ensure_legacy_workflow_in_repository(
        self, legacy_workflow: Any, tenant_id: str
    ) -> None:
        workflow_id = getattr(legacy_workflow, "workflow_id", None)
        if not workflow_id:
            raise ValueError("Invalid legacy workflow object: missing workflow_id")

        existing = self.workflow_repository.get_by_id(workflow_id)
        if existing is not None:
            return

        graph_workflow = self._convert_legacy_workflow(legacy_workflow, tenant_id)
        try:
            self.workflow_repository.save(graph_workflow)
        except ValueError:
            logger.warning("Workflow '%s' already exists in repository", workflow_id)

    def _convert_legacy_workflow(
        self, legacy_workflow: Any, tenant_id: str
    ) -> WorkflowDefinition:
        nodes: List[WorkflowNode] = []
        edges: List[WorkflowEdge] = []

        def add_edge(source: str, target: Any, condition: Optional[str] = None) -> None:
            if not target:
                return
            edge = WorkflowEdge(
                source=source,
                target=str(target),
                condition=condition if condition else None,
            )
            if edge not in edges:
                edges.append(edge)

        for legacy_node in getattr(legacy_workflow, "nodes", []):
            legacy_type = getattr(legacy_node, "node_type", "")
            type_value = getattr(legacy_type, "value", legacy_type)
            type_name = str(type_value).upper()
            mapped_type = self._map_legacy_node_type(type_name)

            node_id = str(getattr(legacy_node, "node_id"))
            node_data = dict(getattr(legacy_node, "config", {}) or {})
            nodes.append(WorkflowNode(id=node_id, type=mapped_type, data=node_data))

            node_next = getattr(legacy_node, "next", None)
            if isinstance(node_next, list):
                for target in node_next:
                    add_edge(node_id, target)
            elif isinstance(node_next, dict):
                for key, target in node_next.items():
                    condition = self._normalize_branch_condition(str(key))
                    add_edge(node_id, target, condition)

            branches = node_data.get("branches", {})
            if isinstance(branches, dict):
                for key, branch_data in branches.items():
                    condition = None
                    target = None

                    if isinstance(branch_data, str):
                        target = branch_data
                        condition = self._normalize_branch_condition(str(key))
                    elif isinstance(branch_data, dict):
                        target = branch_data.get("next")
                        condition = branch_data.get("condition")
                        if condition is None:
                            condition = self._normalize_branch_condition(str(key))

                    add_edge(node_id, target, condition)

        return WorkflowDefinition(
            workflow_id=str(getattr(legacy_workflow, "workflow_id")),
            tenant_id=str(getattr(legacy_workflow, "tenant_id", tenant_id)),
            use_case=str(getattr(legacy_workflow, "use_case", "legacy")),
            version=self._coerce_legacy_version(getattr(legacy_workflow, "version", 1)),
            start_node=str(getattr(legacy_workflow, "start_node")),
            nodes=nodes,
            edges=edges,
        )

    def _map_legacy_node_type(self, type_name: str) -> WorkflowNodeType:
        if type_name in WorkflowNodeType.__members__:
            return WorkflowNodeType[type_name]

        # Fallback for legacy node types that are not part of the new schema.
        return WorkflowNodeType.WAIT

    def _normalize_branch_condition(self, branch_key: str) -> Optional[str]:
        lowered = branch_key.strip().lower()
        if lowered == "true":
            return "True"
        if lowered == "false":
            return "False"
        return None

    def _coerce_legacy_version(self, version: Any) -> int:
        if isinstance(version, int) and version > 0:
            return version
        if isinstance(version, str):
            token = version.strip().split(".")[0]
            if token.isdigit():
                parsed = int(token)
                if parsed > 0:
                    return parsed
        return 1
