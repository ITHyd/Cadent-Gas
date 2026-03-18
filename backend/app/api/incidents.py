"""Incident API endpoints with KB validation and lifecycle management"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
import uuid

logger = logging.getLogger(__name__)

from app.models.incident import IncidentCreate, Incident, IncidentOutcome, IncidentStatus
from app.services.classifier import IncidentClassifier
from app.services.incident_service import IncidentService
from app.core.auth_dependencies import get_current_user

router = APIRouter()
classifier = IncidentClassifier()

def get_orchestrator():
    """Get shared orchestrator instance from agents module"""
    from app.api.agents import agent_orchestrator
    return agent_orchestrator


class AgentLocationUpdateRequest(BaseModel):
    lat: float
    lng: float
    source: str = "gps"
    accuracy: Optional[float] = None
    updated_by: Optional[str] = None


class FieldMilestoneRequest(BaseModel):
    milestone: str
    created_by: str
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AssistanceRequestCreate(BaseModel):
    request_type: str
    priority: str
    reason: str
    details: Optional[str] = None
    created_by: str


class ItemRequestCreate(BaseModel):
    item_name: str
    quantity: int = 1
    urgency: str = "normal"
    notes: Optional[str] = None
    created_by: str


class RequestStatusUpdate(BaseModel):
    status: str
    updated_by: str
    note: Optional[str] = None


class ItemRequestStatusUpdate(BaseModel):
    """Extended update for item requests with optional ETA and warehouse notes."""
    status: str
    updated_by: str
    note: Optional[str] = None
    eta_minutes: Optional[int] = None
    warehouse_notes: Optional[str] = None


class BackupAgentAssignment(BaseModel):
    agent_id: str
    assigned_by: str
    role: str = "backup"
    note: Optional[str] = None


class CustomerNotificationCreate(BaseModel):
    notification_type: str
    title: str
    message: str
    severity: str = "info"
    related_request_id: Optional[str] = None

class UserNoteCreate(BaseModel):
    note: str

class UserNoteUpdate(BaseModel):
    note: str

class SmsPreferenceUpdate(BaseModel):
    sms_enabled: bool
    phone: Optional[str] = None


@router.post("/", response_model=dict)
async def create_incident(
    tenant_id: str = Form(...),
    user_id: str = Form(...),
    description: str = Form(...),
    location: Optional[str] = Form(None),
    user_geo_location: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Create new incident report
    User submits text description + optional media
    """
    try:
        # Generate incident ID
        incident_id = str(uuid.uuid4())
        
        # Process uploaded files
        media_types = []
        if files:
            for file in files:
                # Save file and extract type
                media_types.append(file.content_type.split('/')[0])
        
        # Classify incident
        classification = await classifier.classify(
            description=description,
            media_types=media_types
        )
        
        parsed_geo = None
        if user_geo_location:
            try:
                parsed_geo = json.loads(user_geo_location)
            except json.JSONDecodeError:
                parsed_geo = None

        return {
            "incident_id": incident_id,
            "use_case": classification["use_case"],
            "confidence": classification["confidence"],
            "status": "classified",
            "location": location,
            "user_geo_location": parsed_geo,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual-report", response_model=dict)
async def submit_manual_report(
    tenant_id: str = Form(...),
    user_id: str = Form(...),
    description: str = Form(...),
    incident_type: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    user_name: Optional[str] = Form(None),
    user_phone: Optional[str] = Form(None),
    user_address: Optional[str] = Form(None),
    severity: Optional[str] = Form("medium"),
    user_geo_location: Optional[str] = Form(None),
    existing_incident_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """
    Submit a manual incident report for cases with no automated workflow.
    Creates a full incident record and marks it for company review.
    If existing_incident_id is provided, updates that incident instead.
    """
    try:
        parsed_geo = None
        if user_geo_location:
            try:
                parsed_geo = json.loads(user_geo_location)
            except json.JSONDecodeError:
                parsed_geo = None

        incident_service = orchestrator.incident_service

        # If there's an existing incident (from the chat flow), update it
        if existing_incident_id:
            existing = incident_service.get_incident(existing_incident_id)
            if existing:
                incident_service.update_incident(
                    existing_incident_id,
                    description=description,
                    incident_type=incident_type or existing.incident_type,
                    location=location,
                    user_name=user_name,
                    user_phone=user_phone,
                    user_address=user_address,
                    geo_location=parsed_geo,
                    user_geo_location=parsed_geo,
                    status=IncidentStatus.PENDING_COMPANY_ACTION,
                    structured_data={
                        "manual_report": True,
                        "severity": severity,
                        "reported_via": "manual_form",
                    },
                )
                return {
                    "incident_id": existing_incident_id,
                    "status": "submitted",
                    "message": "Manual report updated and submitted for review.",
                }

        # Classify the incident if no type provided
        classified_use_case = incident_type
        if not classified_use_case and description:
            try:
                classification = await classifier.classify(description=description, media_types=[])
                classified_use_case = classification.get("use_case")
            except Exception as cls_err:
                logger.warning(f"Classification failed for manual report: {cls_err}")

        # KB validation - check for matching knowledge base entries
        kb_validation = None
        kb_match_entry = None
        try:
            kb_service = orchestrator.kb_service
            incident_data = {
                "description": description,
                "severity": severity,
                "location": location,
                "manual_report": True,
            }
            use_case_for_kb = classified_use_case or incident_type or ""
            kb_result = kb_service.verify_incident(incident_data, use_case_for_kb)
            kb_validation = kb_result

            # If there's a strong match, fetch the full KB entry for context
            if kb_result.get("best_match_id"):
                best_id = kb_result["best_match_id"]
                match_type = kb_result.get("best_match_type", "unknown")
                kb_list = kb_service.true_incidents_kb if match_type == "true" else kb_service.false_incidents_kb
                kb_match_entry = next((e for e in kb_list if e.get("kb_id") == best_id), None)
        except Exception as kb_err:
            logger.warning(f"KB validation failed for manual report: {kb_err}")

        # Create new incident
        incident = incident_service.create_incident(
            tenant_id=tenant_id,
            user_id=user_id,
            description=description,
            incident_type=classified_use_case or incident_type,
            user_name=user_name,
            user_phone=user_phone,
            user_address=user_address,
            location=location,
            geo_location=parsed_geo,
            user_geo_location=parsed_geo,
            structured_data={
                "manual_report": True,
                "severity": severity,
                "reported_via": "manual_form",
            },
        )

        # Store KB validation results on the incident
        if kb_validation:
            incident_service.update_incident(
                incident.incident_id,
                kb_similarity_score=kb_validation.get("confidence", 0),
                kb_match_type=kb_validation.get("best_match_type", "unknown"),
                kb_validation_details=kb_validation,
            )

        incident_service.update_incident(
            incident.incident_id,
            status=IncidentStatus.PENDING_COMPANY_ACTION,
        )

        # Notify company
        incident_service.push_notification_to_role(
            "company",
            "Manual Report Submitted",
            f"Manual incident report {incident.incident_id} submitted for '{classified_use_case or incident_type or 'unspecified'}'. Review required.",
            notif_type="warning",
            incident_id=incident.incident_id,
            link="/company",
            tenant_id=tenant_id,
        )

        # Build KB match info for response
        kb_info = None
        if kb_match_entry and kb_validation:
            match_type = kb_validation.get("best_match_type", "unknown")
            if match_type == "true":
                kb_info = {
                    "match_type": "true",
                    "kb_id": kb_match_entry.get("kb_id"),
                    "use_case": kb_match_entry.get("use_case"),
                    "description": kb_match_entry.get("description"),
                    "outcome": kb_match_entry.get("outcome"),
                    "root_cause": kb_match_entry.get("root_cause"),
                    "actions_taken": kb_match_entry.get("actions_taken"),
                    "resolution_summary": kb_match_entry.get("resolution_summary"),
                    "tags": kb_match_entry.get("tags", []),
                    "similarity_score": kb_validation.get("true_kb_match", 0),
                }
            elif match_type == "false":
                kb_info = {
                    "match_type": "false",
                    "kb_id": kb_match_entry.get("kb_id"),
                    "reported_as": kb_match_entry.get("reported_as"),
                    "actual_issue": kb_match_entry.get("actual_issue"),
                    "false_positive_reason": kb_match_entry.get("false_positive_reason"),
                    "resolution": kb_match_entry.get("resolution"),
                    "tags": kb_match_entry.get("tags", []),
                    "similarity_score": kb_validation.get("false_kb_match", 0),
                }

        return {
            "incident_id": incident.incident_id,
            "status": "submitted",
            "classified_use_case": classified_use_case,
            "message": "Manual report submitted successfully. Our team will review it shortly.",
            "kb_validation": kb_info,
        }

    except Exception as e:
        logger.error(f"Manual report error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/available")
async def get_available_agents(
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get all available field agents for assignment"""
    agents = orchestrator.incident_service.get_all_agents()
    return {
        "agents": [a.dict() for a in agents if a.is_available]
    }


@router.get("/agents/all")
async def get_all_agents(
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get all field agents (for display/tracking purposes)"""
    agents = orchestrator.incident_service.get_all_agents()
    return {
        "agents": [a.dict() for a in agents]
    }


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get incident details with timeline and SLA information"""
    try:
        incident = orchestrator.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        data = incident.dict()

        # ── Fallback: recover chat history from workflow_snapshot if needed
        if not data.get("conversation_history") and data.get("workflow_snapshot"):
            snap_history = data["workflow_snapshot"].get("conversation_history")
            if snap_history:
                data["conversation_history"] = snap_history

        # ── Build granular timeline ──────────────────────────────────────
        timeline = []
        agent_status = incident.agent_status
        agent_status_order = ["ASSIGNED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS", "COMPLETED"]

        def _agent_past(target):
            """True if agent has moved PAST this status."""
            if not agent_status or agent_status not in agent_status_order:
                return False
            if target not in agent_status_order:
                return False
            return agent_status_order.index(agent_status) > agent_status_order.index(target)

        def _agent_at(target):
            """True if agent is currently at this status."""
            return agent_status == target

        def _agent_reached(target):
            """True if agent has reached or passed this status."""
            return _agent_past(target) or _agent_at(target)

        def _find_history_ts(status_key):
            """Find timestamp for a status in the history."""
            if not incident.status_history:
                return None
            for entry in incident.status_history:
                if entry.get("status") == status_key:
                    return entry.get("timestamp")
            return None

        needs_dispatch = incident.outcome and incident.outcome.value in ("emergency_dispatch", "schedule_engineer")
        is_dispatched = incident.assigned_agent_id is not None
        is_resolved = incident.status.value in ("resolved", "completed", "closed")
        is_validated = incident.outcome is not None or incident.status.value not in (
            "new", "submitted", "classifying", "in_progress", "paused", "waiting_input", "analyzing"
        )

        # Get agent name for messages
        agent_name = "Engineer"
        if is_dispatched:
            _agent_obj = orchestrator.incident_service.get_agent(incident.assigned_agent_id)
            if _agent_obj:
                agent_name = _agent_obj.full_name

        # 1. Incident Received
        timeline.append({
            "step": "received",
            "label": "Incident Received",
            "category": "system",
            "timestamp": incident.created_at.isoformat() if incident.created_at else None,
            "message": "Your incident report has been received and logged in our system.",
            "completed": True,
        })

        # 2. Validation Completed
        timeline.append({
            "step": "validated",
            "label": "Validation Completed",
            "category": "system",
            "timestamp": incident.completed_at.isoformat() if incident.completed_at and is_validated else None,
            "message": (
                f"Assessment complete. Outcome: {incident.outcome.value.replace('_', ' ').title()}."
                if is_validated and incident.outcome
                else "Your report is being assessed by our AI system."
            ),
            "completed": is_validated,
            "in_progress": not is_validated and incident.status.value in ("classifying", "analyzing", "in_progress"),
        })

        # Steps 3–7: only for dispatch/engineer outcomes
        if needs_dispatch or is_dispatched:
            # 3. Engineer Assigned
            timeline.append({
                "step": "assigned",
                "label": "Engineer Assigned",
                "category": "engineer",
                "timestamp": incident.assigned_at.isoformat() if incident.assigned_at else None,
                "message": (
                    f"{agent_name} has been assigned to your case."
                    if is_dispatched
                    else "Finding the best available engineer for your area."
                ),
                "completed": is_dispatched,
                "in_progress": needs_dispatch and not is_dispatched,
            })

            if is_dispatched:
                # 4. Engineer En Route
                timeline.append({
                    "step": "en_route",
                    "label": "Engineer En Route",
                    "category": "engineer",
                    "timestamp": _find_history_ts("en_route"),
                    "message": (
                        f"{agent_name} is travelling to your location."
                        if _agent_reached("EN_ROUTE")
                        else "Waiting for engineer to depart."
                    ),
                    "completed": _agent_past("EN_ROUTE"),
                    "in_progress": _agent_at("EN_ROUTE"),
                })

                # 5. Arrived On Site
                timeline.append({
                    "step": "on_site",
                    "label": "Arrived On Site",
                    "category": "engineer",
                    "timestamp": _find_history_ts("on_site"),
                    "message": (
                        f"{agent_name} has arrived at the location."
                        if _agent_reached("ON_SITE")
                        else "Engineer has not yet arrived."
                    ),
                    "completed": _agent_past("ON_SITE"),
                    "in_progress": _agent_at("ON_SITE"),
                })

                # 6. Work In Progress
                timeline.append({
                    "step": "work_started",
                    "label": "Work In Progress",
                    "category": "engineer",
                    "timestamp": _find_history_ts("in_progress"),
                    "message": (
                        f"{agent_name} is working on resolving the issue."
                        if _agent_reached("IN_PROGRESS")
                        else "Awaiting work commencement."
                    ),
                    "completed": _agent_past("IN_PROGRESS"),
                    "in_progress": _agent_at("IN_PROGRESS"),
                })

                # 7. Work Completed
                timeline.append({
                    "step": "work_completed",
                    "label": "Work Completed",
                    "category": "completed",
                    "timestamp": _find_history_ts("completed"),
                    "message": (
                        f"{agent_name} has completed the work successfully."
                        if _agent_reached("COMPLETED")
                        else "Work not yet completed."
                    ),
                    "completed": _agent_reached("COMPLETED"),
                })

        # Final step: Case Closed
        if incident.outcome and incident.outcome.value == "close_with_guidance":
            close_label = "Guidance Provided"
        elif incident.outcome and incident.outcome.value == "false_report":
            close_label = "Case Reviewed"
        elif incident.outcome and incident.outcome.value == "monitor":
            close_label = "Monitoring Active"
        else:
            close_label = "Case Closed"

        timeline.append({
            "step": "closed",
            "label": close_label,
            "category": "completed",
            "timestamp": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "message": (
                incident.resolution_notes
                or ("Incident resolved and case closed." if is_resolved else "Pending resolution.")
            ),
            "completed": is_resolved,
        })

        # Progress calculation
        completed_count = sum(1 for s in timeline if s.get("completed"))
        total_count = len(timeline)
        progress = round((completed_count / total_count) * 100) if total_count > 0 else 0

        data["timeline"] = timeline
        data["progress"] = progress

        # SLA info
        data["sla"] = {
            "sla_hours": incident.sla_hours,
            "estimated_resolution_at": incident.estimated_resolution_at.isoformat() if incident.estimated_resolution_at else None,
            "location_type": IncidentService._classify_location_type(incident.location) if incident.location else "suburban",
        }

        # Hydrate assigned agent details
        if incident.assigned_agent_id:
            agent = orchestrator.incident_service.get_agent(incident.assigned_agent_id)
            if agent:
                data["assigned_agent"] = agent.dict()
            else:
                data["assigned_agent"] = None

            agent_status_labels = {
                "ASSIGNED": "Assigned",
                "EN_ROUTE": "On the Way",
                "ON_SITE": "On Site",
                "IN_PROGRESS": "Working",
                "COMPLETED": "Completed",
            }
            data["agent_status_label"] = agent_status_labels.get(
                incident.agent_status, incident.agent_status
            )
            data["estimated_arrival_at"] = (
                incident.estimated_arrival_at.isoformat()
                if incident.estimated_arrival_at else None
            )
        else:
            data["assigned_agent"] = None
            data["agent_status_label"] = None
            data["estimated_arrival_at"] = None

        # Customer notifications
        data["customer_notifications"] = incident.customer_notifications or []

        # Backup agents with hydrated details
        backup_agents_data = []
        for ba in (incident.backup_agents or []):
            ba_copy = dict(ba)
            ba_agent = orchestrator.incident_service.get_agent(ba.get("agent_id"))
            if ba_agent:
                ba_copy["agent_details"] = ba_agent.dict()
            backup_agents_data.append(ba_copy)
        data["backup_agents"] = backup_agents_data

        # Auto-check SLA notifications
        orchestrator.incident_service.check_and_create_sla_notifications(incident.incident_id)

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/agent-location")
async def update_agent_location(
    incident_id: str,
    payload: AgentLocationUpdateRequest,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Update latest field-agent location and append a location history point."""
    try:
        incident = orchestrator.incident_service.update_agent_location(
            incident_id=incident_id,
            lat=payload.lat,
            lng=payload.lng,
            source=payload.source,
            accuracy=payload.accuracy,
            updated_by=payload.updated_by,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {
            "incident_id": incident_id,
            "agent_live_location": incident.agent_live_location,
            "history_points": len(incident.agent_location_history or []),
            "updated_at": incident.updated_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/milestones")
async def add_milestone(
    incident_id: str,
    payload: FieldMilestoneRequest,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Append a rich field-operation milestone for an incident."""
    try:
        incident = orchestrator.incident_service.add_field_milestone(
            incident_id=incident_id,
            milestone=payload.milestone,
            created_by=payload.created_by,
            notes=payload.notes,
            metadata=payload.metadata,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {
            "incident_id": incident_id,
            "agent_status": incident.agent_status,
            "field_activity": incident.field_activity or [],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/assistance-requests")
async def create_assistance_request(
    incident_id: str,
    payload: AssistanceRequestCreate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Create a structured additional-assistance request from field agent."""
    try:
        request = orchestrator.incident_service.create_assistance_request(
            incident_id=incident_id,
            created_by=payload.created_by,
            request_type=payload.request_type,
            priority=payload.priority,
            reason=payload.reason,
            details=payload.details,
        )
        if not request:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"incident_id": incident_id, "request": request}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{incident_id}/assistance-requests/{request_id}")
async def update_assistance_request(
    incident_id: str,
    request_id: str,
    payload: RequestStatusUpdate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Update assistance request status from operations/admin side."""
    try:
        request = orchestrator.incident_service.update_assistance_request(
            incident_id=incident_id,
            request_id=request_id,
            status=payload.status,
            updated_by=payload.updated_by,
            note=payload.note,
        )
        if not request:
            raise HTTPException(status_code=404, detail="Incident or request not found")
        return {"incident_id": incident_id, "request": request}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/item-requests")
async def create_item_request(
    incident_id: str,
    payload: ItemRequestCreate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Create item/equipment request for active field work."""
    try:
        request = orchestrator.incident_service.create_item_request(
            incident_id=incident_id,
            created_by=payload.created_by,
            item_name=payload.item_name,
            quantity=payload.quantity,
            urgency=payload.urgency,
            notes=payload.notes,
        )
        if not request:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"incident_id": incident_id, "request": request}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{incident_id}/item-requests/{request_id}")
async def update_item_request(
    incident_id: str,
    request_id: str,
    payload: ItemRequestStatusUpdate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Update item request status (approve/dispatch/deliver/use)."""
    try:
        request = orchestrator.incident_service.update_item_request(
            incident_id=incident_id,
            request_id=request_id,
            status=payload.status,
            updated_by=payload.updated_by,
            note=payload.note,
            eta_minutes=payload.eta_minutes,
            warehouse_notes=payload.warehouse_notes,
        )
        if not request:
            raise HTTPException(status_code=404, detail="Incident or request not found")
        return {"incident_id": incident_id, "request": request}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/assistance-requests/{request_id}/assign-backup")
async def assign_backup_agent(
    incident_id: str,
    request_id: str,
    payload: BackupAgentAssignment,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Assign a backup engineer to an assistance request."""
    try:
        result = orchestrator.incident_service.assign_backup_agent(
            incident_id=incident_id,
            request_id=request_id,
            agent_id=payload.agent_id,
            assigned_by=payload.assigned_by,
            role=payload.role,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"incident_id": incident_id, "backup_assignment": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/notifications")
async def create_customer_notification(
    incident_id: str,
    payload: CustomerNotificationCreate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Add a customer-facing notification to an incident."""
    try:
        incident = orchestrator.incident_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        notif = orchestrator.incident_service._add_customer_notification(
            incident=incident,
            notification_type=payload.notification_type,
            title=payload.title,
            message=payload.message,
            severity=payload.severity,
            related_request_id=payload.related_request_id,
        )
        return {"incident_id": incident_id, "notification": notif}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{incident_id}/notifications")
async def get_customer_notifications(
    incident_id: str,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get all customer notifications for an incident."""
    try:
        incident = orchestrator.incident_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        notifications = incident.customer_notifications or []
        return {
            "incident_id": incident_id,
            "notifications": sorted(notifications, key=lambda n: n.get("created_at", ""), reverse=True),
            "total": len(notifications),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/user-notes")
async def add_user_note(
    incident_id: str,
    payload: UserNoteCreate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Add a user note/additional detail to an incident."""
    try:
        incident = orchestrator.incident_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        note_entry = {
            "note_id": str(uuid.uuid4())[:8],
            "note": payload.note,
            "created_at": datetime.utcnow().isoformat(),
        }

        if not incident.structured_data:
            incident.structured_data = {}
        user_notes = incident.structured_data.get("_user_notes", [])
        user_notes.append(note_entry)
        incident.structured_data["_user_notes"] = user_notes
        incident.updated_at = datetime.utcnow()

        return {"incident_id": incident_id, "note": note_entry}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{incident_id}/user-notes/{note_id}")
async def update_user_note(
    incident_id: str,
    note_id: str,
    payload: UserNoteUpdate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Update an existing user note."""
    try:
        incident = orchestrator.incident_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        user_notes = (incident.structured_data or {}).get("_user_notes", [])
        for n in user_notes:
            if n.get("note_id") == note_id:
                n["note"] = payload.note
                n["updated_at"] = datetime.utcnow().isoformat()
                incident.structured_data["_user_notes"] = user_notes
                incident.updated_at = datetime.utcnow()
                return {"incident_id": incident_id, "note": n}

        raise HTTPException(status_code=404, detail="Note not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{incident_id}/user-notes/{note_id}")
async def delete_user_note(
    incident_id: str,
    note_id: str,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Delete a user note."""
    try:
        incident = orchestrator.incident_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        user_notes = (incident.structured_data or {}).get("_user_notes", [])
        original_len = len(user_notes)
        user_notes = [n for n in user_notes if n.get("note_id") != note_id]

        if len(user_notes) == original_len:
            raise HTTPException(status_code=404, detail="Note not found")

        incident.structured_data["_user_notes"] = user_notes
        incident.updated_at = datetime.utcnow()
        return {"incident_id": incident_id, "deleted_note_id": note_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{incident_id}/sms-preference")
async def update_sms_preference(
    incident_id: str,
    payload: SmsPreferenceUpdate,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Update SMS notification preference for an incident."""
    try:
        incident = orchestrator.incident_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        if not incident.structured_data:
            incident.structured_data = {}
        incident.structured_data["_sms_preference"] = {
            "enabled": payload.sms_enabled,
            "phone": payload.phone or incident.user_phone,
            "updated_at": datetime.utcnow().isoformat(),
        }
        incident.updated_at = datetime.utcnow()

        return {
            "incident_id": incident_id,
            "sms_enabled": payload.sms_enabled,
            "phone": payload.phone or incident.user_phone,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_incidents(
    user_id: str,
    tenant_id: Optional[str] = None,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get all incidents for a user (My Reports)"""
    try:
        incidents = orchestrator.get_user_incidents(user_id, tenant_id)
        return {
            "user_id": user_id,
            "total": len(incidents),
            "incidents": [inc.dict() for inc in incidents]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{tenant_id}/ops-requests")
async def get_company_ops_requests(
    tenant_id: str,
    kind: str = "all",
    status: Optional[str] = None,
    include_closed: bool = False,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get flattened open assistance/item requests for company operations queue."""
    try:
        role = current_user.get("role")
        if role not in ("company", "admin", "super_user"):
            raise HTTPException(status_code=403, detail="Company access required")
        if role == "company" and current_user.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Tenant access denied")

        connector_scope = []
        if role == "company":
            connector_scope = current_user.get("connector_scope", [])

        status_filter = [s.strip().upper() for s in status.split(",")] if status else None
        data = orchestrator.incident_service.get_company_ops_requests(
            tenant_id=tenant_id,
            kind=kind,
            status_filter=status_filter,
            include_closed=include_closed,
            connector_scope=connector_scope,
        )
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{tenant_id}")
async def get_company_incidents(
    tenant_id: str,
    status: Optional[str] = None,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get all incidents for a company (Admin Dashboard) — scoped by admin group."""
    try:
        role = current_user.get("role")
        if role not in ("company", "admin", "super_user"):
            raise HTTPException(status_code=403, detail="Company access required")
        # Company users can only access their own tenant
        if role == "company" and current_user.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Tenant access denied")

        # Resolve connector scope: super_user/admin = [] (all), company = from JWT
        connector_scope = []
        if role == "company":
            connector_scope = current_user.get("connector_scope", [])

        # Parse status filter
        status_filter = None
        if status:
            status_filter = [IncidentStatus(s.strip()) for s in status.split(",")]

        incidents = orchestrator.get_company_incidents(tenant_id, status_filter, connector_scope)

        return {
            "tenant_id": tenant_id,
            "total": len(incidents),
            "incidents": [inc.dict() for inc in incidents],
            "connector_scope": connector_scope,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{tenant_id}/stats")
async def get_company_stats(
    tenant_id: str,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get incident statistics for a company — scoped by admin group."""
    try:
        role = current_user.get("role")
        if role not in ("company", "admin", "super_user"):
            raise HTTPException(status_code=403, detail="Company access required")
        if role == "company" and current_user.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Tenant access denied")

        connector_scope = []
        if role == "company":
            connector_scope = current_user.get("connector_scope", [])

        stats = orchestrator.get_incident_stats(tenant_id, connector_scope)
        stats["connector_scope"] = connector_scope
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/assign")
async def assign_agent(
    incident_id: str,
    agent_id: str = Form(...),
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Assign field agent to incident"""
    try:
        incident = orchestrator.assign_agent_to_incident(incident_id, agent_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        return {
            "incident_id": incident_id,
            "agent_id": agent_id,
            "status": incident.status.value,
            "agent_status": incident.agent_status,
            "assigned_at": incident.assigned_at.isoformat() if incident.assigned_at else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    resolved_by: str = Form(...),
    resolution_notes: Optional[str] = Form(None),
    items_used: Optional[str] = Form(None),  # Comma-separated list
    root_cause: Optional[str] = Form(None),
    actions_taken: Optional[str] = Form(None),  # Comma-separated list
    verification_evidence: Optional[str] = Form(None),
    verification_evidence_note: Optional[str] = Form(None),
    verification_result: Optional[str] = Form(None),
    safety_checks_completed: Optional[bool] = Form(None),
    handoff_confirmed: Optional[bool] = Form(None),
    resolution_checklist_json: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Mark incident as resolved by field agent"""
    try:
        # Parse items_used from comma-separated string
        items_list = None
        if items_used:
            items_list = [item.strip() for item in items_used.split(",") if item.strip()]

        checklist: Dict[str, Any] = {}
        if resolution_checklist_json:
            try:
                checklist = json.loads(resolution_checklist_json)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid resolution_checklist_json payload")
        else:
            checklist = {
                "root_cause": root_cause,
                "actions_taken": [item.strip() for item in (actions_taken or "").split(",") if item.strip()],
                "verification_evidence": verification_evidence,
                "verification_evidence_note": verification_evidence_note,
                "verification_result": verification_result,
                "safety_checks_completed": safety_checks_completed,
                "handoff_confirmed": handoff_confirmed,
            }

        # Save uploaded resolution media (proof of fix)
        import os
        from app.core.config import settings
        resolution_media_list = []
        if files:
            upload_dir = os.path.join(settings.UPLOAD_DIR, "resolution", incident_id)
            os.makedirs(upload_dir, exist_ok=True)
            for file in files:
                file_id = f"RMEDIA_{uuid.uuid4().hex[:10].upper()}"
                safe_name = f"{file_id}_{file.filename}"
                file_path = os.path.join(upload_dir, safe_name)
                content = await file.read()
                with open(file_path, "wb") as f:
                    f.write(content)
                resolution_media_list.append({
                    "media_id": file_id,
                    "filename": file.filename,
                    "file_path": file_path,
                    "content_type": file.content_type,
                    "size_bytes": len(content),
                    "uploaded_at": datetime.utcnow().isoformat(),
                })

        incident = orchestrator.mark_incident_resolved(
            incident_id,
            resolved_by,
            resolution_notes,
            items_list,
            checklist,
            resolution_media=resolution_media_list if resolution_media_list else None,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {
            "incident_id": incident_id,
            "status": incident.status.value,
            "agent_status": incident.agent_status,
            "resolved_by": resolved_by,
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "items_used": incident.items_used,
            "resolution_checklist": incident.resolution_checklist,
            "resolution_media": incident.resolution_media,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{incident_id}/media/{media_id}")
async def get_incident_media(
    incident_id: str,
    media_id: str,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Serve incident media file (user-uploaded images from chatbot)"""
    from fastapi.responses import FileResponse
    incident = orchestrator.get_incident(incident_id)
    if not incident or not incident.media:
        raise HTTPException(status_code=404, detail="Not found")
    media = next((m for m in incident.media if m.media_id == media_id), None)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    content_type = (media.metadata or {}).get("content_type", "image/jpeg")
    return FileResponse(media.file_path, media_type=content_type)


@router.get("/{incident_id}/resolution-media/{media_id}")
async def get_resolution_media(
    incident_id: str,
    media_id: str,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Serve resolution media file (proof of fix images/documents)"""
    from fastapi.responses import FileResponse
    incident = orchestrator.get_incident(incident_id)
    if not incident or not incident.resolution_media:
        raise HTTPException(status_code=404, detail="Not found")
    media = next((m for m in incident.resolution_media if m["media_id"] == media_id), None)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return FileResponse(media["file_path"], media_type=media["content_type"])


@router.post("/{incident_id}/approve-resolution")
async def approve_resolution(
    incident_id: str,
    approved_by: str = Form(...),
    approval_notes: Optional[str] = Form(None),
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Company approves agent resolution, marking incident as COMPLETED."""
    try:
        incident = orchestrator.company_approve_resolution(
            incident_id, approved_by, approval_notes
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {
            "incident_id": incident_id,
            "status": incident.status.value,
            "completed_at": incident.completed_at.isoformat() if incident.completed_at else None,
            "approved_by": approved_by,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/validate")
async def validate_incident(
    incident_id: str,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Run KB validation on a backfilled/external incident.

    Only available for incidents in 'new' or 'in_progress' status.
    Returns KB match results so the admin can decide if the incident is genuine.
    """
    incident_service = orchestrator.incident_service
    incident = incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status.value not in ("new", "in_progress"):
        raise HTTPException(
            status_code=400,
            detail="Only new or in-progress incidents can be validated",
        )

    kb_service = orchestrator.kb_service
    incident_data = {
        "description": incident.description or "",
        "severity": "medium",
        "location": incident.location,
        "incident_type": incident.incident_type,
    }
    use_case = incident.incident_type or incident.classified_use_case or ""
    kb_result = kb_service.verify_incident(incident_data, use_case)

    incident_service.update_incident(
        incident_id,
        kb_similarity_score=kb_result.get("confidence", 0),
        kb_match_type=kb_result.get("best_match_type", "unknown"),
        kb_validation_details=kb_result,
    )

    return {
        "incident_id": incident_id,
        "validation": kb_result,
        "status": incident.status.value,
    }


class MarkFalseRequest(BaseModel):
    notes: Optional[str] = None


@router.post("/{incident_id}/mark-false")
async def mark_incident_false(
    incident_id: str,
    body: MarkFalseRequest = Body(MarkFalseRequest()),
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Mark an incident as a false report. Syncs status back to external system."""
    incident_service = orchestrator.incident_service
    incident = incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    notes = body.notes or "Marked as false report by admin after KB validation"

    incident.status = IncidentStatus.FALSE_REPORT
    incident.outcome = IncidentOutcome.FALSE_REPORT
    incident.resolution_notes = notes
    incident.updated_at = datetime.utcnow()

    incident_service._add_status_history(
        incident, "false_report", "Incident marked as false report by admin"
    )

    # Trigger outbound sync to external system (SAP / ServiceNow)
    synced = False
    if incident_service._sync_service and incident.external_ref:
        try:
            import asyncio
            asyncio.ensure_future(
                incident_service._sync_service.on_incident_updated(
                    incident, ["status"]
                )
            )
            synced = True
        except Exception as e:
            logger.error("Outbound sync failed for %s: %s", incident_id, e)

    return {
        "incident_id": incident_id,
        "status": "false_report",
        "synced": synced,
    }


@router.post("/{incident_id}/confirm-valid")
async def confirm_incident_valid(
    incident_id: str,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Admin override: confirm an external incident as valid after KB review.

    Sets kb_match_type to 'admin_confirmed' and moves the incident to
    pending_company_action so it can be assigned to an agent.
    """
    incident_service = orchestrator.incident_service
    incident = incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status.value not in ("new", "in_progress"):
        raise HTTPException(
            status_code=400,
            detail="Only new or in-progress incidents can be confirmed",
        )

    incident_service.update_incident(
        incident_id,
        kb_match_type="admin_confirmed",
    )

    # Move to pending_company_action so Assign Agent flow works
    incident.status = IncidentStatus.PENDING_COMPANY_ACTION
    incident.updated_at = datetime.utcnow()
    incident_service._add_status_history(
        incident,
        "pending_company_action",
        "Incident confirmed as valid by admin after KB review",
    )

    return {
        "incident_id": incident_id,
        "status": "pending_company_action",
        "kb_match_type": "admin_confirmed",
    }


@router.get("/agent/{agent_id}/incidents")
async def get_agent_incidents(
    agent_id: str,
    status: Optional[str] = None,
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get all incidents assigned to a field agent"""
    try:
        # Parse status filter
        status_filter = None
        if status:
            status_filter = [s.strip() for s in status.split(",")]
        
        incidents = orchestrator.incident_service.get_agent_incidents(agent_id, status_filter)
        
        return {
            "agent_id": agent_id,
            "total": len(incidents),
            "incidents": [inc.dict() for inc in incidents]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{incident_id}/agent-status")
async def update_agent_status(
    incident_id: str,
    agent_status: str = Form(...),
    orchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Update field agent status for an incident"""
    try:
        # Validate agent_status
        valid_statuses = ["ASSIGNED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS", "COMPLETED"]
        if agent_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agent_status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        incident = orchestrator.incident_service.update_agent_status(incident_id, agent_status)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        return {
            "incident_id": incident_id,
            "agent_status": incident.agent_status,
            "updated_at": incident.updated_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── In-App Notification Endpoints ───────────────────────────────────────

@router.get("/notifications/{user_id}")
async def get_user_notifications(
    user_id: str,
    unread_only: bool = False,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Get all notifications for a user"""
    try:
        notifs = orchestrator.incident_service.get_notifications(user_id, unread_only)
        unread = orchestrator.incident_service.get_unread_count(user_id)
        return {"user_id": user_id, "unread_count": unread, "notifications": notifs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/{user_id}/mark-read/{notification_id}")
async def mark_notification_read(
    user_id: str,
    notification_id: str,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Mark a single notification as read"""
    try:
        success = orchestrator.incident_service.mark_notification_read(user_id, notification_id)
        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/{user_id}/mark-all-read")
async def mark_all_notifications_read(
    user_id: str,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Mark all notifications as read for a user"""
    try:
        count = orchestrator.incident_service.mark_all_notifications_read(user_id)
        return {"status": "ok", "marked_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
