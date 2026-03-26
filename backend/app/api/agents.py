"""Agent interaction API endpoints"""
import base64
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, WebSocket, WebSocketDisconnect

from app.services.agent_orchestrator import AgentOrchestrator
from app.services.workflow_engine import WorkflowEngine
from app.models.workflow import Workflow
from app.services.auth_service import auth_service
from app.core.config import settings
from app.models.user import UserRole

router = APIRouter()
logger = logging.getLogger(__name__)

# Global instances
agent_orchestrator = AgentOrchestrator()
workflow_engine = WorkflowEngine()

# Active WebSocket connections
active_connections: Dict[str, WebSocket] = {}
transport_session_bindings: Dict[str, str] = {}


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, token: Optional[str] = Query(None)):
    """
    WebSocket endpoint for real-time agent interaction.
    Requires JWT token as ?token= query parameter.
    """
    # Validate auth token. Unauthenticated websockets are allowed only when
    # explicitly enabled for local development.
    auth_payload = None
    if token:
        auth_payload = auth_service.decode_token(token)
        if not auth_payload or auth_payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid or expired token")
            return
    elif not settings.ALLOW_UNAUTHENTICATED_WEBSOCKET:
        logger.warning(f"WebSocket rejected (no token): session_id={session_id}")
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    await websocket.accept()
    active_connections[session_id] = websocket
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            message_type = message.get("type")
            
            if message_type == "start":
                # Start new agent session
                await websocket.send_json({"type": "typing", "typing": True})
                response = await handle_start_session(message, auth_payload)
                if response.get("type") == "agent_message" and response.get("session_id"):
                    transport_session_bindings[session_id] = response["session_id"]
                await websocket.send_json({"type": "typing", "typing": False})
                await websocket.send_json(response)

            elif message_type == "resume_session":
                await websocket.send_json({"type": "typing", "typing": True})
                response = await handle_resume_session(message, auth_payload)
                if response.get("type") == "agent_message" and response.get("session_id"):
                    transport_session_bindings[session_id] = response["session_id"]
                await websocket.send_json({"type": "typing", "typing": False})
                await websocket.send_json(response)

            elif message_type == "user_input":
                # Send typing indicator immediately, then process
                await websocket.send_json({"type": "typing", "typing": True})
                response = await handle_user_input(message)
                await websocket.send_json({"type": "typing", "typing": False})
                await websocket.send_json(response)

            elif message_type == "upload_complete":
                # Handle file upload completion
                await websocket.send_json({"type": "typing", "typing": True})
                response = await handle_upload_complete(message)
                await websocket.send_json({"type": "typing", "typing": False})
                await websocket.send_json(response)

            elif message_type == "get_paused":
                # Return the user's paused/resumable incidents
                response = await handle_get_paused(message)
                await websocket.send_json(response)

            elif message_type == "resume":
                # Resume a paused incident
                response = await handle_resume_incident(message)
                await websocket.send_json(response)

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Unknown message type"
                })

    except WebSocketDisconnect:
        agent_session_id = transport_session_bindings.pop(session_id, session_id)
        logger.info(f"WebSocket disconnected: transport={session_id} agent={agent_session_id}")
        # Persist any in-progress workflow so the user can resume later
        agent_orchestrator.handle_disconnect(agent_session_id)
        active_connections.pop(session_id, None)

    except Exception as e:
        agent_session_id = transport_session_bindings.pop(session_id, session_id)
        logger.error(f"WebSocket error: transport={session_id} agent={agent_session_id} error={str(e)}", exc_info=True)
        agent_orchestrator.handle_disconnect(agent_session_id)
        active_connections.pop(session_id, None)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            logger.warning(f"Unable to send websocket error payload for transport={session_id}")


async def handle_start_session(message: Dict[str, Any], auth_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Handle session start request"""
    try:
        logger.info(f"Starting session with message: {message}")
        incident_id = message.get("incident_id")
        tenant_id = message.get("tenant_id")
        user_id = message.get("user_id")
        use_case = message.get("use_case")
        initial_data = message.get("initial_data", {})

        if auth_payload:
            role = auth_payload.get("role")
            token_tenant = auth_payload.get("tenant_id")
            token_user_id = auth_payload.get("user_id")
            is_super = role in (UserRole.SUPER_USER.value, UserRole.ADMIN.value)

            if not is_super:
                if token_tenant and tenant_id and tenant_id != token_tenant:
                    raise HTTPException(status_code=403, detail="Cross-tenant session start denied")
                # Company admins can report on behalf of a customer (different user_id)
                is_company = role == UserRole.COMPANY.value
                if not is_company:
                    if token_user_id and user_id and user_id != token_user_id:
                        raise HTTPException(status_code=403, detail="User mismatch in session start")

            # Default missing values from token context
            if not tenant_id:
                tenant_id = token_tenant
            if not user_id:
                user_id = token_user_id

        # Pass use_case into initial_data so orchestrator can use it directly
        if use_case:
            initial_data["use_case"] = use_case

        logger.info(f"Loading workflow for tenant: {tenant_id}, use_case: {use_case}")
        # Load workflow for use case
        workflow = await load_workflow(tenant_id, use_case)
        
        logger.info(f"Starting agent session for incident: {incident_id}")
        # Start agent session
        result = await agent_orchestrator.start_session(
            incident_id=incident_id,
            workflow=workflow,
            tenant_id=tenant_id,
            user_id=user_id,
            initial_data=initial_data
        )
        
        logger.info(f"Session started successfully: {result['session_id']}")
        return {
            "type": "agent_message",
            "session_id": result["session_id"],
            "message": result["message"],
            "action": result["action"],
            "data": result["data"]
        }
    
    except Exception as e:
        logger.error(f"Start session error: {str(e)}", exc_info=True)
        return {
            "type": "error",
            "message": str(e)
        }


async def handle_resume_session(message: Dict[str, Any], auth_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reconnect to an existing incident by auto-resuming paused workflow state when available."""
    try:
        logger.info(f"Resuming session with message: {message}")
        incident_id = message.get("incident_id")
        tenant_id = message.get("tenant_id")
        user_id = message.get("user_id")
        use_case = message.get("use_case")
        initial_data = message.get("initial_data", {})

        if auth_payload:
            role = auth_payload.get("role")
            token_tenant = auth_payload.get("tenant_id")
            token_user_id = auth_payload.get("user_id")
            is_super = role in (UserRole.SUPER_USER.value, UserRole.ADMIN.value)

            if not is_super:
                if token_tenant and tenant_id and tenant_id != token_tenant:
                    raise HTTPException(status_code=403, detail="Cross-tenant session resume denied")
                is_company = role == UserRole.COMPANY.value
                if not is_company and token_user_id and user_id and user_id != token_user_id:
                    raise HTTPException(status_code=403, detail="User mismatch in session resume")

            if not tenant_id:
                tenant_id = token_tenant
            if not user_id:
                user_id = token_user_id

        if use_case:
            initial_data["use_case"] = use_case

        workflow = await load_workflow(tenant_id, use_case)
        result = await agent_orchestrator.reconnect_session(
            incident_id=incident_id,
            workflow=workflow,
            tenant_id=tenant_id,
            user_id=user_id,
            initial_data=initial_data,
        )
        return {
            "type": "agent_message",
            "session_id": result["session_id"],
            "message": result["message"],
            "action": result["action"],
            "data": result.get("data", {}),
            "completed": result.get("completed", False),
        }
    except Exception as e:
        logger.error(f"Resume session error: {str(e)}", exc_info=True)
        return {
            "type": "error",
            "message": str(e)
        }


async def handle_user_input(message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle user input"""
    try:
        logger.info(f"Processing user input: {message}")
        session_id = message.get("session_id")
        user_input = message.get("input")
        
        logger.info(f"Calling agent orchestrator for session: {session_id}")
        # Process input through agent
        result = await agent_orchestrator.process_user_input(
            session_id=session_id,
            user_input=user_input
        )
        
        logger.info(f"Agent response: {result.get('message', '')[:100]}...")
        response = {
            "type": "agent_message",
            "session_id": result["session_id"],
            "message": result["message"],
            "action": result["action"],
            "data": result.get("data", {}),
            "completed": result.get("completed", False),
        }
        # Forward the voice transcript so the frontend can update the
        # "transcribing…" placeholder bubble with the actual text.
        if "user_transcript" in result:
            response["user_transcript"] = result["user_transcript"]
        return response

    except Exception as e:
        logger.error(f"User input error: {str(e)}", exc_info=True)
        return {
            "type": "error",
            "message": str(e)
        }


async def handle_upload_complete(message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle file upload completion"""
    try:
        session_id = message.get("session_id")
        file_path = message.get("file_path")
        file_type = message.get("file_type")
        
        # Process as user input
        user_input = {
            "uploaded_file": file_path,
            "file_type": file_type
        }
        
        result = await agent_orchestrator.process_user_input(
            session_id=session_id,
            user_input=user_input
        )
        
        return {
            "type": "agent_message",
            "session_id": result["session_id"],
            "message": result["message"],
            "action": result["action"],
            "data": result.get("data", {}),
            "completed": result.get("completed", False)
        }
    
    except Exception as e:
        logger.error(f"Upload complete error: {str(e)}")
        return {
            "type": "error",
            "message": str(e)
        }


async def handle_get_paused(message: Dict[str, Any]) -> Dict[str, Any]:
    """Return the user's paused/resumable incidents."""
    try:
        user_id = message.get("user_id")
        tenant_id = message.get("tenant_id")
        paused = agent_orchestrator.get_paused_incidents(user_id, tenant_id)
        return {
            "type": "paused_incidents",
            "incidents": [
                {
                    "incident_id": inc.incident_id,
                    "use_case": inc.classified_use_case or inc.incident_type or "",
                    "description": inc.description,
                    "paused_at": (inc.workflow_snapshot or {}).get("paused_at", ""),
                }
                for inc in paused
            ],
        }
    except Exception as e:
        logger.error(f"Get paused error: {e}", exc_info=True)
        return {"type": "error", "message": str(e)}


async def handle_resume_incident(message: Dict[str, Any]) -> Dict[str, Any]:
    """Resume a paused incident in the current session."""
    try:
        session_id = message.get("session_id")
        incident_id = message.get("incident_id")
        result = await agent_orchestrator.resume_incident(session_id, incident_id)
        return {
            "type": "agent_message",
            "session_id": result["session_id"],
            "message": result["message"],
            "action": result.get("action", "question"),
            "data": result.get("data", {}),
            "completed": False,
        }
    except Exception as e:
        logger.error(f"Resume incident error: {e}", exc_info=True)
        return {"type": "error", "message": str(e)}


async def load_workflow(tenant_id: str, use_case: str) -> Workflow:
    """Load workflow definition for tenant and use case"""
    # Placeholder - implement database query
    # For now, return a mock workflow
    from datetime import datetime  # noqa: local re-import for standalone helper
    from app.models.workflow import (
        Workflow, WorkflowMetadata, WorkflowNode, NodeType,
        RiskFactor, SafetyOverride, DecisionThresholds
    )
    
    return Workflow(
        workflow_id="wf_gas_smell_001",
        tenant_id=tenant_id,
        use_case=use_case,
        version="1.0.0",
        metadata=WorkflowMetadata(
            name="Gas Smell Investigation",
            description="Interactive workflow for gas smell incidents",
            created_by="system",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        nodes=[
            WorkflowNode(
                node_id="start",
                node_type=NodeType.QUESTION,
                config={
                    "question_text": "Do you smell gas right now?",
                    "question_type": "yes_no",
                    "options": ["Yes", "No"],
                    "context_hint": "This helps us assess immediate danger"
                },
                next=["smell_condition"]
            ),
            WorkflowNode(
                node_id="smell_condition",
                node_type=NodeType.CONDITION,
                config={
                    "expression": "{{start}} == 'Yes'",
                    "branches": {
                        "true": "smell_intensity",
                        "false": "final_decision"
                    }
                },
                next=[]
            ),
            WorkflowNode(
                node_id="smell_intensity",
                node_type=NodeType.QUESTION,
                config={
                    "question_text": "How strong is the smell?",
                    "question_type": "multiple_choice",
                    "options": ["Faint", "Moderate", "Strong", "Overwhelming"]
                },
                next=["calculate_risk"]
            ),
            WorkflowNode(
                node_id="calculate_risk",
                node_type=NodeType.CALCULATE,
                config={
                    "calculation_type": "risk_score",
                    "formula": "smell_score * 0.8",
                    "inputs": {
                        "smell_score": "{{smell_intensity}}"
                    },
                    "output_variable": "final_risk_score"
                },
                next=["final_decision"]
            ),
            WorkflowNode(
                node_id="final_decision",
                node_type=NodeType.DECISION,
                config={
                    "decision_variable": "final_risk_score",
                    "branches": {
                        "emergency": {
                            "condition": "{{final_risk_score}} >= 0.8",
                            "next": "emergency_dispatch"
                        },
                        "schedule": {
                            "condition": "{{final_risk_score}} >= 0.5",
                            "next": "schedule_engineer"
                        },
                        "close": {
                            "condition": "{{final_risk_score}} < 0.5",
                            "next": "close_with_guidance"
                        }
                    }
                },
                next=[]
            )
        ],
        start_node="start",
        risk_factors=[
            RiskFactor(
                factor_id="smell_intensity",
                name="Gas Smell Intensity",
                weight=0.8,
                source_node="smell_intensity"
            )
        ],
        safety_overrides=[
            SafetyOverride(
                condition="smell_intensity == 'Overwhelming'",
                trigger_node="smell_intensity",
                action="emergency_dispatch"
            )
        ],
        decision_thresholds=DecisionThresholds()
    )


@router.websocket("/ws/voice/{session_id}")
async def voice_websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for live voice chat
    Handles continuous audio streaming with VAD and TTS responses
    """
    await websocket.accept()
    active_connections[f"voice_{session_id}"] = websocket
    
    try:
        from app.services.vad_service import VADService
        from app.services.tts_service import TTSService
        
        vad_service = VADService()
        tts_service = TTSService()
        
        # Track speech segments for VAD
        speech_segments = []
        audio_buffer = []
        
        while True:
            # Receive audio chunk from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            message_type = message.get("type")
            
            if message_type == "audio_chunk":
                # Process audio chunk with VAD
                audio_data = message.get("audio_data")  # base64 encoded
                
                # Decode audio
                audio_bytes = base64.b64decode(audio_data)
                
                # Run VAD
                vad_result = vad_service.detect_voice_activity(audio_bytes)
                
                # Store segment
                speech_segments.append({
                    "has_speech": vad_result["has_speech"],
                    "is_silence": vad_result["is_silence"],
                    "timestamp": message.get("timestamp", 0),
                    "duration": message.get("duration", 0.1)
                })
                
                # Accumulate audio if speech detected
                if vad_result["has_speech"]:
                    audio_buffer.append(audio_bytes)
                
                # Check if we should process accumulated audio
                current_time = message.get("timestamp", 0)
                if vad_service.should_process_audio(speech_segments, current_time):
                    # Combine audio buffer
                    combined_audio = b''.join(audio_buffer)
                    audio_base64 = base64.b64encode(combined_audio).decode('utf-8')
                    
                    # Process through agent orchestrator
                    response = await handle_user_input({
                        "session_id": session_id,
                        "input": {
                            "audio": audio_base64,
                            "format": "webm",
                            "type": "audio"
                        }
                    })
                    
                    # Generate TTS response
                    if response.get("message"):
                        tts_result = await tts_service.text_to_speech(
                            text=response["message"],
                            voice="nova",
                            speed=1.0
                        )
                        
                        # Send TTS response back
                        await websocket.send_json({
                            "type": "voice_response",
                            "message": response["message"],
                            "tts_data": tts_result.get("audio_data"),
                            "tts_format": tts_result.get("format", "mp3"),
                            "use_browser_tts": tts_result.get("use_browser_tts", False),
                            "action": response.get("action"),
                            "data": response.get("data", {}),
                            "completed": response.get("completed", False)
                        })
                    
                    # Clear buffers
                    audio_buffer = []
                    speech_segments = []
            
            elif message_type == "stop_speaking":
                # User interrupted - stop current response
                await websocket.send_json({
                    "type": "stop_audio",
                    "message": "Audio stopped"
                })
            
            elif message_type == "start_listening":
                # Reset buffers
                audio_buffer = []
                speech_segments = []
                await websocket.send_json({
                    "type": "listening_started",
                    "message": "Ready to listen"
                })
    
    except WebSocketDisconnect:
        logger.info(f"Voice WebSocket disconnected: {session_id}")
        if f"voice_{session_id}" in active_connections:
            del active_connections[f"voice_{session_id}"]
    
    except Exception as e:
        logger.error(f"Voice WebSocket error: {str(e)}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


@router.get("/session/{session_id}/history")
async def get_conversation_history(session_id: str):
    """Get conversation history for a session"""
    try:
        history = agent_orchestrator.get_conversation_history(session_id)
        return {
            "session_id": session_id,
            "history": history
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
):
    """
    Transcription-only endpoint. Receives an audio file and returns
    the transcribed text without processing through the agent orchestrator.
    """
    try:
        from app.services.multimodal_processor import MultimodalProcessor
        processor = MultimodalProcessor()

        content = await file.read()
        audio_format = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "webm"
        b64_audio = base64.b64encode(content).decode("utf-8")

        result = await processor.process_input({
            "type": "audio",
            "content": b64_audio,
            "format": audio_format,
        })

        return {
            "text": result.get("text", ""),
            "confidence": result.get("confidence", 0.0),
        }
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail="Sorry, I couldn't understand the audio. Please try again.")
