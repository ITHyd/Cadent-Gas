"""Workflow-first agent orchestrator with topic-drift, switching & edge-case handling."""
import base64
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.incident import IncidentMedia, IncidentOutcome, IncidentStatus, MediaType
from app.models.session_mode import SessionMode
from app.models.workflow import Workflow
from app.constants.reference_ids import normalize_demo_reference_id
from app.services.classifier import IncidentClassifier
from app.services.incident_service import IncidentService
from app.services.intent_detector import detect_intent
from app.services.kb_service import KBService
from app.services.risk_calculator import RiskCalculator
from app.services.multimodal_processor import MultimodalProcessor
from app.services.workflow_engine import WorkflowEngine
from app.services.workflow_repository import workflow_repository

from app.core.config import settings
from app.core.mongodb import get_database
import os

logger = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────────────
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.50
MAX_PAUSED_WORKFLOWS = 3
MAX_SWITCHES_PER_WINDOW = 3
SWITCH_WINDOW_SECONDS = 300  # 5 minutes


class AgentOrchestrator:
    """Coordinates classification, workflow execution, and incident lifecycle."""

    def __init__(self):
        self.workflow_engine = WorkflowEngine()
        self.classifier = IncidentClassifier()
        self.multimodal_processor = MultimodalProcessor()
        self.kb_service = KBService()
        self.risk_calculator = RiskCalculator()
        self.incident_service = IncidentService()
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    def _create_session_record(
        self,
        incident_id: str,
        tenant_id: str,
        user_id: str,
        initial_data: Dict[str, Any],
    ) -> str:
        session_id = str(uuid.uuid4())
        reference_id = normalize_demo_reference_id(initial_data.get("reference_id"))
        structured_data = {}
        if reference_id:
            structured_data["reference_id"] = reference_id

        self.active_sessions[session_id] = {
            "session_id": session_id,
            "incident_id": incident_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_details": initial_data.get("user_details", {}),
            "reported_by_staff_id": initial_data.get("reported_by_staff_id"),
            "initial_data": initial_data,
            "execution_id": None,
            "workflow_id": None,
            "workflow_version": None,
            "use_case": initial_data.get("use_case") or None,
            "completed": False,
            "mode": SessionMode.IDLE,
            "paused_workflows": [],
            "pending_switch": None,
            "pending_reference_match": None,
            "last_question_data": None,
            "validation_notice_sent": False,
            "reference_id": reference_id,
            "awaiting_reference_id": not bool(reference_id),
            "switch_count": 0,
            "switch_timestamps": [],
            "consecutive_unclear_count": 0,
            "mode_history": [],
            "conversation_history": [],
            "structured_data": structured_data,
            "created_at": datetime.utcnow(),
        }
        return session_id

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  SESSION LIFECYCLE                                                  ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    async def start_session(
        self,
        incident_id: str,
        workflow: Workflow,
        tenant_id: str,
        user_id: str,
        initial_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a session. Workflow selection/execution starts from first user message."""
        _ = workflow  # Kept for compatibility with existing API callers.
        session_id = self._create_session_record(incident_id, tenant_id, user_id, initial_data)
        reference_id = self.active_sessions[session_id]["reference_id"]

        # Check if the user has paused incidents they can resume
        paused = self.incident_service.get_paused_incidents(user_id, tenant_id)
        if paused:
            names = []
            incident_ids = []
            for inc in paused:
                label = (inc.classified_use_case or inc.incident_type or "incident").replace("_", " ").title()
                names.append(label)
                incident_ids.append(inc.incident_id)

            message = (
                "Welcome back! You have unfinished reports:\n"
                + "\n".join(f"• {n}" for n in names)
                + "\n\nWould you like to continue one of these, or start a new report?"
            )
            self._add_to_history(session_id, "agent", {"message": message, "action": "offer_resume"})
            return {
                "session_id": session_id,
                "message": message,
                "action": "offer_resume",
                "data": {
                    "options": names + ["Start New Report"],
                    "paused_incident_ids": incident_ids,
                },
            }

        if reference_id:
            existing_incident = self.incident_service.get_incident_by_reference_id(
                reference_id,
                tenant_id=tenant_id,
                exclude_incident_id=incident_id,
            )
            if existing_incident:
                return self._build_reference_exists_response(
                    session_id,
                    reference_id,
                    existing_incident.incident_id,
                )

            message = "Reference ID recorded. Please describe your gas incident so I can start the workflow."
            action = "awaiting_incident_report"
            data = {"reference_id": reference_id}
        else:
            message = "Please enter the REF ID before we begin."
            action = "reference_id_prompt"
            data = {
                "refIdPrompt": True,
                "reference_id_prompt": True,
            }

        self._add_to_history(
            session_id,
            "agent",
            {"message": message, "action": action, "data": data},
        )

        return {
            "session_id": session_id,
            "message": message,
            "action": action,
            "data": data,
        }

    async def reconnect_session(
        self,
        incident_id: str,
        workflow: Workflow,
        tenant_id: str,
        user_id: str,
        initial_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a fresh session and auto-resume a paused incident when possible."""
        _ = workflow  # Maintains parity with current call sites.

        session_id = self._create_session_record(incident_id, tenant_id, user_id, initial_data)
        incident = self.incident_service.get_incident(incident_id) if incident_id else None

        if incident and incident.workflow_snapshot:
            logger.info(f"[{session_id}] Reconnecting paused incident {incident_id}")
            return await self.resume_incident(session_id, incident_id)

        logger.info(f"[{session_id}] No paused snapshot for incident {incident_id}; starting fresh session")
        self.active_sessions.pop(session_id, None)
        return await self.start_session(
            incident_id=incident_id,
            workflow=workflow,
            tenant_id=tenant_id,
            user_id=user_id,
            initial_data=initial_data,
        )

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  MAIN DECISION TREE                                                 ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    async def process_user_input(
        self,
        session_id: str,
        user_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Route user input through the session-mode decision tree."""
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.get("completed"):
            # Check for resume offer after completion
            return await self._check_and_offer_resume(session_id, user_input)

        processed_input = await self._process_multimodal_input(user_input)
        user_message = processed_input["text"]
        input_type = processed_input.get("original_type", "text")

        logger.info(
            f"[{session_id}] Processed input: type={input_type}, "
            f"text='{user_message}', confidence={processed_input.get('confidence', 'N/A')}"
        )

        # ── Guard: if media processing failed, tell the user ────────────
        if input_type in ("audio", "video", "image") and (
            not user_message
            or user_message.startswith("[")
            or processed_input.get("confidence", 1.0) == 0.0
        ):
            # Extract the actual error reason from metadata
            error_reason = processed_input.get("metadata", {}).get("error", "")

            if input_type == "image":
                fail_msg = (
                    "I couldn't analyze the image. "
                    "You can try uploading again, type your response, or select **Skip** to continue."
                )
            else:
                fail_msg = (
                    "Sorry, I couldn't catch that. "
                    "Could you please try speaking again, or type your response instead? "
                    "You can also select **Skip** to continue."
                )

            session = self.active_sessions.get(session_id)
            if session:
                last_q = session.get("last_question_data")
                if last_q:
                    fail_msg += f"\n\n{last_q.get('message', '')}"
                    data = dict(last_q.get("data", {}))
                    # Ensure Skip is available so user can move past the error
                    options = data.get("options", [])
                    if "Skip" not in options:
                        options = list(options) + ["Skip"]
                        data["options"] = options
                    self._add_to_history(session_id, "agent", {"message": fail_msg, "action": "reprompt"})
                    return {
                        "session_id": session_id,
                        "message": fail_msg,
                        "action": "question",
                        "data": data,
                        "completed": False,
                    }
            self._add_to_history(session_id, "agent", {"message": fail_msg, "action": "reprompt"})
            return {
                "session_id": session_id,
                "message": fail_msg,
                "action": "awaiting_input",
                "data": {"options": ["Skip"]},
                "completed": False,
            }

        # Store transcript so all response paths can include it
        if input_type in ("audio", "video"):
            session["_last_transcript"] = user_message

        # Persist uploaded images to disk and attach to the incident
        if input_type == "image" and processed_input.get("confidence", 0) > 0:
            self._save_media_to_incident(session, user_input, processed_input)

        self._add_to_history(
            session_id, "user",
            {"message": user_message, "input_type": input_type},
        )

        # ── Classify every incoming message for intent detection ─────────
        reference_capture_response = await self._maybe_capture_reference_id(
            session_id=session_id,
            user_message=user_message,
        )
        if reference_capture_response is not None:
            transcript = session.pop("_last_transcript", None)
            if transcript:
                reference_capture_response["user_transcript"] = transcript
            return reference_capture_response

        classification = await self.classifier.classify(user_message)
        session["last_classification"] = classification
        logger.info(f"Message classification: {classification}")

        mode = self._get_mode(session)

        # ── 1. IDLE — no workflow running yet ─────────────────────────────
        if mode == SessionMode.IDLE:
            return await self._handle_idle_mode(session_id, user_message, classification, processed_input)

        # ── 2. CONFIRM_SWITCH — awaiting yes/no ──────────────────────────
        if mode == SessionMode.CONFIRM_SWITCH:
            return await self._handle_confirm_switch_response(session_id, user_message, classification, processed_input)

        # ── 3. SMALL_TALK — user was off-topic last turn ─────────────────
        if mode == SessionMode.SMALL_TALK:
            return await self._handle_small_talk_continuation(session_id, user_message, classification, processed_input)

        # ── 4. IN_WORKFLOW — the core path ────────────────────────────────
        return await self._handle_in_workflow(session_id, user_message, classification, processed_input)

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  MODE HANDLERS                                                      ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    async def _handle_idle_mode(
        self, session_id: str, user_message: str,
        classification: Dict[str, Any], processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """First real message: classify use-case, load workflow, start execution."""
        session = self.active_sessions[session_id]

        # ── Check if the user is responding to a resume offer ───────────
        last_hist = session.get("conversation_history", [])
        offered_resume = any(
            item.get("content", {}).get("action") == "offer_resume"
            for item in last_hist if item.get("role") == "agent"
        )
        if offered_resume:
            lower = user_message.strip().lower()
            # "Start new report" → skip resume
            if "new" in lower or "start" in lower:
                logger.info(f"[{session_id}] User chose to start new report")
            else:
                # Try to match user input to a paused incident
                paused = self.incident_service.get_paused_incidents(
                    session["user_id"], session["tenant_id"],
                )
                for inc in paused:
                    label = (inc.classified_use_case or inc.incident_type or "").replace("_", " ").lower()
                    if label and label in lower:
                        logger.info(f"[{session_id}] Resuming paused incident {inc.incident_id}")
                        return await self.resume_incident(session_id, inc.incident_id)
                # If only one paused and user didn't explicitly say "new", resume it
                if len(paused) == 1 and "new" not in lower:
                    logger.info(f"[{session_id}] Auto-resuming single paused incident")
                    return await self.resume_incident(session_id, paused[0].incident_id)

        # If use_case was pre-selected (category button), skip classification
        if session.get("use_case"):
            classified_use_case = session["use_case"]
            logger.info(f"Using pre-selected use_case: {classified_use_case}")
        else:
            classified_use_case = str(classification.get("use_case", "")).strip()
            classification_confidence = classification.get("confidence", 0)
            logger.info(f"Classification result: use_case={classified_use_case}, "
                        f"confidence={classification_confidence:.2%}, "
                        f"reasoning={classification.get('reasoning', 'N/A')}")

            # Low-confidence classification — the user's message doesn't clearly
            # describe a gas incident (e.g. they just said their name or a greeting).
            # Ask them to describe the actual issue instead of guessing.
            if classification_confidence < 0.40:
                logger.info(f"[{session_id}] Classification confidence too low "
                            f"({classification_confidence:.0%}) — asking user to describe issue")
                clarify_msg = (
                    "Thanks! Could you please describe the gas-related issue "
                    "you're experiencing? For example:\n"
                    "• I smell gas in my kitchen\n"
                    "• My boiler isn't working\n"
                    "• I hear a hissing sound near the pipe\n\n"
                    "Or you can select a category above."
                )
                self._add_to_history(session_id, "agent", {"message": clarify_msg, "action": "awaiting_incident_report"})
                result = {
                    "session_id": session_id,
                    "message": clarify_msg,
                    "action": "awaiting_incident_report",
                    "data": {},
                    "completed": False,
                }
                # Attach voice transcript so frontend can update the
                # "transcribing…" placeholder bubble with the actual text.
                transcript = session.pop("_last_transcript", None)
                if transcript:
                    result["user_transcript"] = transcript
                return result

        try:
            return await self._start_new_workflow(session_id, classified_use_case, user_message, processed_input)
        except ValueError:
            logger.warning(f"[{session_id}] No workflow for use_case='{classified_use_case}'. Redirecting to manual report.")
            # Create the incident so it's persisted even without a workflow
            self._ensure_incident(session, description=user_message)
            incident_id = session.get("incident_id")
            # Mark it as pending manual review
            if incident_id:
                self.incident_service.update_incident(
                    incident_id,
                    status=IncidentStatus.PENDING_COMPANY_ACTION,
                    classified_use_case=classified_use_case,
                )
                self.incident_service.push_notification_to_role(
                    "company",
                    "Manual Report - Review Required",
                    f"Incident {incident_id} for '{classified_use_case}' has no automated workflow. Manual report submitted.",
                    notif_type="warning",
                    incident_id=incident_id,
                    link="/company",
                    tenant_id=session.get("tenant_id"),
                )
            result = {
                "session_id": session_id,
                "message": (
                    "We don't have an automated workflow for this type of issue yet. "
                    "Please fill out a detailed manual report so our team can review it and take action. "
                    "You will be redirected to the report form."
                ),
                "action": "no_workflow",
                "data": {
                    "incident_id": incident_id,
                    "classified_use_case": classified_use_case,
                    "redirect": "/report",
                },
                "completed": True,
            }
            transcript = session.pop("_last_transcript", None)
            if transcript:
                result["user_transcript"] = transcript
            return result

    async def _handle_in_workflow(
        self, session_id: str, user_message: str,
        classification: Dict[str, Any], processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """User is mid-workflow. Detect intent and route accordingly."""
        session = self.active_sessions[session_id]
        current_use_case = session.get("use_case")

        # ── Fast-path: when there is a pending workflow question, the user's
        #    input is almost certainly an answer — route to the workflow engine
        #    directly.  Emergency keywords are already caught *before* this
        #    method (line 131), so we only need to let through explicit
        #    new-incident cues before taking the fast-path.
        last_q = session.get("last_question_data")
        if last_q:
            # Check for explicit new-incident cues first (e.g. "I have another problem")
            from app.services.intent_detector import NEW_INCIDENT_CUES
            lower_msg = user_message.lower()
            has_new_incident_cue = any(cue in lower_msg for cue in NEW_INCIDENT_CUES)

            if not has_new_incident_cue:
                options = last_q.get("data", {}).get("options", [])
                input_type = processed_input.get("original_type", "text")
                # When the question expects media (image/audio/video) and the
                # user sent that media type, accept it as a valid answer even
                # though the analysed text won't match predefined options like
                # "Skip".  The options are only alternatives for users who
                # choose not to provide media.
                question_expects_media = last_q.get("data", {}).get("input_type") in ("image", "audio", "video")
                is_media_input = input_type in ("image", "audio", "video")

                if options and not (question_expects_media and is_media_input):
                    # Question with predefined options — match input to an option
                    matched_option = self._match_input_to_option(user_message, options)
                    if matched_option:
                        logger.info(
                            f"[{session_id}] Input '{user_message}' matched workflow option "
                            f"'{matched_option}' — continuing workflow"
                        )
                        session["consecutive_unclear_count"] = 0
                        return await self._continue_current_workflow(
                            session_id, matched_option, processed_input,
                        )
                    # Input didn't match any option — reprompt
                    logger.info(
                        f"[{session_id}] Input '{user_message}' didn't match options "
                        f"{options} — reprompting"
                    )
                    return self._reprompt_current_question(
                        session_id,
                        prefix="I didn't quite catch a valid response. Please select one of the options below. ",
                    )
                else:
                    # Free-text question (no options), or media input for a
                    # media-expecting question — accept the answer as-is
                    reason = "media upload accepted" if (question_expects_media and is_media_input) else "free-text question"
                    logger.info(
                        f"[{session_id}] {reason}: '{user_message[:80]}...' — "
                        f"continuing workflow"
                    )
                    session["consecutive_unclear_count"] = 0
                    return await self._continue_current_workflow(
                        session_id, user_message, processed_input,
                    )

        # ── No pending question — run full intent detection ─────────────
        intent = detect_intent(user_message, classification, current_use_case)
        intent_type = intent["intent"]
        confidence = intent["confidence"]

        logger.info(f"[{session_id}] Intent: {intent_type} (conf={confidence:.2f}) — {intent['detail']}")

        # ── Same topic → reset unclear count, continue workflow ───────────
        if intent_type == "same_topic":
            session["consecutive_unclear_count"] = 0
            return await self._continue_current_workflow(session_id, user_message, processed_input)

        # ── Multi-incident → handle first, note the rest ─────────────────
        if intent_type == "multi_incident":
            session["consecutive_unclear_count"] = 0
            return await self._handle_multi_incident_detected(
                session_id, user_message, intent, classification, processed_input,
            )

        # ── New incident detected ─────────────────────────────────────────
        if intent_type == "new_incident":
            session["consecutive_unclear_count"] = 0
            new_use_case = intent.get("new_use_case") or str(classification.get("use_case", "")).strip()

            # Stability check
            stability_msg = self._check_stability(session)
            if stability_msg:
                return self._handle_stability_exceeded(session_id, stability_msg)

            if confidence >= HIGH_CONFIDENCE:
                return await self._handle_high_confidence_switch(
                    session_id, user_message, new_use_case, confidence, processed_input,
                )
            if confidence >= MEDIUM_CONFIDENCE:
                return await self._handle_medium_confidence_switch(
                    session_id, user_message, new_use_case, confidence, intent["detail"],
                )

        # ── Unclear (0.3–0.5) → ask clarification or 3-strike default ────
        if intent_type == "unclear":
            session["consecutive_unclear_count"] = session.get("consecutive_unclear_count", 0) + 1
            if session["consecutive_unclear_count"] >= 3:
                logger.info(f"[{session_id}] 3 consecutive unclear messages — defaulting to current workflow")
                session["consecutive_unclear_count"] = 0
                return await self._continue_current_workflow(session_id, user_message, processed_input)
            return self._handle_unclear_input(session_id, user_message, classification)

        # ── Small talk / low confidence ───────────────────────────────────
        if intent_type == "small_talk" or confidence < MEDIUM_CONFIDENCE:
            session["consecutive_unclear_count"] = 0
            return await self._handle_low_confidence_input(session_id, user_message, classification)

        # Fallback: treat as same topic
        session["consecutive_unclear_count"] = 0
        return await self._continue_current_workflow(session_id, user_message, processed_input)

    async def _handle_high_confidence_switch(
        self, session_id: str, user_message: str,
        new_use_case: str, confidence: float, processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Auto-switch: pause current workflow and start new one."""
        session = self.active_sessions[session_id]
        old_use_case = session.get("use_case", "unknown")

        logger.info(f"[{session_id}] High-confidence switch: {old_use_case} -> {new_use_case} (conf={confidence:.2f})")

        self._pause_current_workflow(session)
        self._record_switch(session)

        return await self._start_new_workflow(session_id, new_use_case, user_message, processed_input)

    async def _handle_medium_confidence_switch(
        self, session_id: str, user_message: str,
        new_use_case: str, confidence: float, detail: str,
    ) -> Dict[str, Any]:
        """Ask the user to confirm before switching."""
        session = self.active_sessions[session_id]
        old_use_case = session.get("use_case", "unknown")
        display_new = new_use_case.replace("_", " ").title()
        display_old = old_use_case.replace("_", " ").title()

        session["pending_switch"] = {
            "use_case": new_use_case,
            "confidence": confidence,
            "detail": detail,
            "original_message": user_message,
        }
        self._transition_mode(session, SessionMode.CONFIRM_SWITCH, f"medium-confidence switch to {new_use_case} {confidence:.2f}")

        confirm_msg = (
            f"It sounds like you might be describing a different issue "
            f"({display_new}) while we're working on {display_old}.\n\n"
            f"Would you like to:\n"
            f"• Switch to {display_new} (your current progress will be saved)\n"
            f"• Continue with {display_old}"
        )
        self._add_to_history(session_id, "agent", {"message": confirm_msg, "action": "confirm_switch"})

        result = {
            "session_id": session_id,
            "message": confirm_msg,
            "action": "confirm_switch",
            "data": {
                "options": [f"Switch to {display_new}", f"Continue with {display_old}"],
                "pending_use_case": new_use_case,
            },
            "completed": False,
        }
        transcript = session.pop("_last_transcript", None)
        if transcript:
            result["user_transcript"] = transcript
        return result

    async def _handle_confirm_switch_response(
        self, session_id: str, user_message: str,
        classification: Dict[str, Any], processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process the user's yes/no answer to a switch confirmation."""
        session = self.active_sessions[session_id]
        pending = session.get("pending_switch")

        lower = user_message.strip().lower()
        wants_switch = any(kw in lower for kw in [
            "switch", "yes", "new", "different", "change", "other",
        ])
        wants_continue = any(kw in lower for kw in [
            "continue", "no", "stay", "current", "keep",
        ])

        # Clear pending state
        session["pending_switch"] = None

        if wants_switch and pending:
            self._pause_current_workflow(session)
            self._record_switch(session)
            self._transition_mode(session, SessionMode.IDLE, "user confirmed switch")
            session["use_case"] = None
            original_msg = pending.get("original_message", user_message)
            return await self._start_new_workflow(
                session_id, pending["use_case"], original_msg, processed_input,
            )

        # Default: continue current workflow
        self._transition_mode(session, SessionMode.IN_WORKFLOW, "user chose to continue")
        return self._reprompt_current_question(session_id, prefix="No problem, let's continue. ")

    async def _handle_low_confidence_input(
        self, session_id: str, user_message: str, classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle off-topic / small-talk while in a workflow."""
        session = self.active_sessions[session_id]
        self._transition_mode(session, SessionMode.SMALL_TALK, "low confidence / off-topic input")

        response_msg = self._generate_small_talk_response(user_message)

        self._add_to_history(session_id, "agent", {"message": response_msg, "action": "small_talk"})

        result = {
            "session_id": session_id,
            "message": response_msg,
            "action": "small_talk",
            "data": {},
            "completed": False,
        }
        transcript = session.pop("_last_transcript", None)
        if transcript:
            result["user_transcript"] = transcript
        return result

    def _handle_unclear_input(
        self, session_id: str, user_message: str, classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle ambiguous input (0.3-0.5 confidence) — ask for clarification."""
        session = self.active_sessions[session_id]
        unclear_count = session.get("consecutive_unclear_count", 1)

        clarify_msg = (
            "I'm not quite sure what you mean. "
            "Could you rephrase that, or would you like to continue answering "
            "the current question?"
        )
        if unclear_count >= 2:
            clarify_msg = (
                "I'm still having trouble understanding. "
                "Let me re-ask the current question — you can answer that, "
                "or type your concern more specifically."
            )

        # Append the last question for context
        last_q = session.get("last_question_data")
        data = {}
        if last_q:
            clarify_msg += f"\n\n{last_q.get('message', '')}"
            data = last_q.get("data", {})

        self._add_to_history(session_id, "agent", {"message": clarify_msg, "action": "clarification"})
        result = {
            "session_id": session_id,
            "message": clarify_msg,
            "action": "question",
            "data": data,
            "completed": False,
        }
        transcript = session.pop("_last_transcript", None)
        if transcript:
            result["user_transcript"] = transcript
        return result

    async def _handle_small_talk_continuation(
        self, session_id: str, user_message: str,
        classification: Dict[str, Any], processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """User was in small-talk mode. Check if they're back on topic."""
        session = self.active_sessions[session_id]
        confidence = classification.get("confidence", 0)

        # If back on topic, resume workflow
        if confidence >= MEDIUM_CONFIDENCE:
            self._transition_mode(session, SessionMode.IN_WORKFLOW, "user returned to topic from small talk")

            if session.get("execution_id"):
                return await self._continue_current_workflow(session_id, user_message, processed_input)
            else:
                self._transition_mode(session, SessionMode.IDLE, "no active execution after small talk")
                return await self._handle_idle_mode(session_id, user_message, classification, processed_input)

        # Still off-topic: gently redirect
        self._transition_mode(session, SessionMode.IN_WORKFLOW, "redirecting from continued small talk")
        return self._reprompt_current_question(
            session_id,
            prefix="I appreciate the chat! Let's get back to your incident though. ",
        )

    async def _handle_multi_incident_detected(
        self, session_id: str, user_message: str,
        intent: Dict[str, Any], classification: Dict[str, Any],
        processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """User described multiple incidents in one message."""
        incidents = intent.get("incidents", [])
        session = self.active_sessions[session_id]

        logger.info(f"Multi-incident detected: {len(incidents)} incidents")

        # Acknowledge and handle the first one
        ack_msg = (
            f"I noticed you mentioned {len(incidents)} separate issues. "
            f"Let me help you with each one.\n\n"
            f"Let's start with the first one: \"{incidents[0]}\""
        )

        # Store remaining incidents for later
        session["queued_incidents"] = incidents[1:]

        self._add_to_history(session_id, "agent", {"message": ack_msg, "action": "multi_incident_ack"})

        # Classify and start workflow for the first incident
        first_classification = await self.classifier.classify(incidents[0])
        first_use_case = str(first_classification.get("use_case", "")).strip()

        try:
            result = await self._start_new_workflow(session_id, first_use_case, incidents[0], processed_input)
            # Prepend the acknowledgement
            result["message"] = ack_msg + "\n\n" + result["message"]
            return result
        except ValueError:
            return {
                "session_id": session_id,
                "message": ack_msg + "\n\nUnfortunately, I couldn't find a matching workflow. Could you describe the first issue in more detail?",
                "action": "question",
                "data": {},
                "completed": False,
            }

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  WORKFLOW OPERATIONS                                                ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _build_reference_exists_response(
        self,
        session_id: str,
        reference_id: str,
        existing_incident_id: str,
    ) -> Dict[str, Any]:
        session = self.active_sessions[session_id]
        session["pending_reference_match"] = {
            "reference_id": reference_id,
            "incident_id": existing_incident_id,
        }

        message = (
            f"Existing incident found for Reference ID {reference_id}.\n"
            f"Incident ID: {existing_incident_id}\n\n"
            "Would you like to open the existing incident or re-enter another REF ID?"
        )
        data = {
            "reference_id_exists": True,
            "reference_id": reference_id,
            "incident_id": existing_incident_id,
            "redirect": f"/my-reports/{existing_incident_id}",
            "options": ["Open Existing Incident", "Re-enter REF ID"],
        }
        self._add_to_history(
            session_id,
            "agent",
            {"message": message, "action": "reference_id_exists", "data": data},
        )
        return {
            "session_id": session_id,
            "message": message,
            "action": "reference_id_exists",
            "data": data,
            "completed": False,
        }

    def _prompt_for_reference_id(
        self,
        session_id: str,
        message: str = "Please enter the REF ID before we begin.",
    ) -> Dict[str, Any]:
        session = self.active_sessions[session_id]
        session["awaiting_reference_id"] = True
        session["pending_reference_match"] = None
        session["reference_id"] = None
        session.setdefault("initial_data", {}).pop("reference_id", None)
        session.get("structured_data", {}).pop("reference_id", None)

        data = {
            "refIdPrompt": True,
            "reference_id_prompt": True,
        }
        self._add_to_history(
            session_id,
            "agent",
            {"message": message, "action": "reference_id_prompt", "data": data},
        )
        return {
            "session_id": session_id,
            "message": message,
            "action": "reference_id_prompt",
            "data": data,
            "completed": False,
        }

    def _handle_reference_match_choice(
        self,
        session_id: str,
        user_message: str,
    ) -> Dict[str, Any]:
        session = self.active_sessions[session_id]
        pending = session.get("pending_reference_match") or {}
        lower = user_message.strip().lower()

        wants_open = "open" in lower or "existing" in lower or "use" in lower
        wants_reenter = "re-enter" in lower or "reenter" in lower or "another" in lower

        if wants_open and pending.get("incident_id"):
            incident_id = pending["incident_id"]
            reference_id = pending["reference_id"]
            current_incident_id = session.get("incident_id")
            current_incident = (
                self.incident_service.get_incident(current_incident_id)
                if current_incident_id
                else None
            )
            if (
                current_incident
                and current_incident.incident_id != incident_id
                and not current_incident.reference_id
            ):
                self.incident_service.delete_incident(current_incident.incident_id)

            session["pending_reference_match"] = None
            session["completed"] = True
            message = (
                f"Opening existing incident {incident_id} for Reference ID {reference_id}."
            )
            data = {
                "incident_id": incident_id,
                "reference_id": reference_id,
                "redirect": f"/my-reports/{incident_id}",
            }
            self._add_to_history(
                session_id,
                "agent",
                {"message": message, "action": "open_existing_incident", "data": data},
            )
            return {
                "session_id": session_id,
                "message": message,
                "action": "open_existing_incident",
                "data": data,
                "completed": True,
            }

        if wants_reenter:
            return self._prompt_for_reference_id(
                session_id,
                message="Please enter another REF ID to continue.",
            )

        return self._build_reference_exists_response(
            session_id,
            pending.get("reference_id", ""),
            pending.get("incident_id", ""),
        )

    async def _maybe_capture_reference_id(
        self,
        session_id: str,
        user_message: str,
    ) -> Optional[Dict[str, Any]]:
        """Capture the reference ID before the normal chat flow begins."""
        session = self.active_sessions[session_id]
        if session.get("pending_reference_match"):
            return self._handle_reference_match_choice(session_id, user_message)

        if not session.get("awaiting_reference_id"):
            return None

        reference_id = normalize_demo_reference_id(user_message)
        if reference_id is None:
            return self._prompt_for_reference_id(
                session_id,
                message="Please enter a valid REF ID to continue.",
            )

        existing_incident = self.incident_service.get_incident_by_reference_id(
            reference_id,
            tenant_id=session.get("tenant_id"),
            exclude_incident_id=session.get("incident_id"),
        )
        if existing_incident:
            return self._build_reference_exists_response(
                session_id,
                reference_id,
                existing_incident.incident_id,
            )

        session["reference_id"] = reference_id
        session["awaiting_reference_id"] = False
        session["structured_data"]["reference_id"] = reference_id
        session.setdefault("initial_data", {})["reference_id"] = reference_id

        incident_id = session.get("incident_id")
        if incident_id and self.incident_service.get_incident(incident_id):
            self.incident_service.update_incident(
                incident_id,
                reference_id=reference_id,
                structured_data=session.get("structured_data", {}),
            )

        initial_description = (
            session.get("initial_data", {}).get("description")
            or session.get("initial_data", {}).get("incident_description")
        )
        use_case = session.get("use_case")
        if use_case and initial_description:
            result = await self._start_new_workflow(
                session_id=session_id,
                use_case=use_case,
                user_message=initial_description,
                processed_input={
                    "text": initial_description,
                    "original_type": "text",
                    "confidence": 1.0,
                    "metadata": {},
                },
            )
            result["message"] = (
                f"Reference ID {reference_id} recorded.\n\n{result['message']}"
            )
            return result

        message = (
            f"Reference ID {reference_id} recorded. "
            "Please describe your gas incident so I can start the workflow."
        )
        data = {
            "reference_id": reference_id,
            "awaiting_incident_report": True,
        }
        self._add_to_history(
            session_id,
            "agent",
            {"message": message, "action": "awaiting_incident_report", "data": data},
        )
        return {
            "session_id": session_id,
            "message": message,
            "action": "awaiting_incident_report",
            "data": data,
            "completed": False,
        }

    async def _start_new_workflow(
        self, session_id: str, use_case: str,
        user_message: str, processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Load a workflow by use_case, start execution, return the first question."""
        session = self.active_sessions[session_id]

        logger.info(f"Looking up workflow for tenant '{session['tenant_id']}' and use_case '{use_case}'")
        workflow_def = await self._get_latest_workflow(session["tenant_id"], use_case)

        if workflow_def is None:
            error_msg = f"No workflow configured for use_case: '{use_case}' (tenant: '{session['tenant_id']}')"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Workflow found: {workflow_def.workflow_id} v{workflow_def.version}")

        state = await self.workflow_engine.start_execution(
            workflow_def.workflow_id,
            session["tenant_id"],
        )
        session["execution_id"] = state.execution_id
        session["workflow_id"] = workflow_def.workflow_id
        session["workflow_version"] = workflow_def.version
        session["use_case"] = workflow_def.use_case
        self._transition_mode(session, SessionMode.IN_WORKFLOW, f"started workflow {workflow_def.workflow_id}")

        logger.info(f"[{session_id}] Workflow execution started: {state.execution_id}")

        self._ensure_incident(session, description=user_message)

        engine_response = await self.workflow_engine.continue_execution(state.execution_id, None)
        return await self._handle_engine_response(
            session_id=session_id,
            engine_response=engine_response,
            input_type=processed_input.get("original_type", "text"),
        )

    async def _continue_current_workflow(
        self, session_id: str, user_message: str, processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Pass user input to the current workflow execution."""
        session = self.active_sessions[session_id]

        # Validate answer against current question options (if any)
        last_q = session.get("last_question_data")
        if last_q:
            options = last_q.get("data", {}).get("options", [])
            input_type = processed_input.get("original_type", "text")
            question_expects_media = last_q.get("data", {}).get("input_type") in ("image", "audio", "video")
            is_media_input = input_type in ("image", "audio", "video")

            if options and not (question_expects_media and is_media_input):
                matched = self._match_input_to_option(user_message, options)
                if matched:
                    # Use the canonical option string for the engine
                    user_message = matched
                else:
                    # User's text doesn't match any option — reprompt
                    logger.info(
                        f"[{session_id}] Answer '{user_message}' not in options {options} — reprompting"
                    )
                    return self._reprompt_current_question(
                        session_id,
                        prefix="I didn't quite catch a valid response. Please select one of the options below. ",
                    )

        engine_response = await self.workflow_engine.continue_execution(
            session["execution_id"],
            user_message,
        )
        result = await self._handle_engine_response(
            session_id=session_id,
            engine_response=engine_response,
            input_type=processed_input.get("original_type", "text"),
        )

        # When the user uploaded an image, prepend a brief analysis summary
        # so they know what was detected before seeing the next question.
        if processed_input.get("original_type") == "image":
            summary = self._build_image_analysis_summary(processed_input)
            if summary:
                result["message"] = summary + "\n\n" + result["message"]
                result.setdefault("data", {})["image_analysis"] = (
                    processed_input.get("metadata", {}).get("image_analysis", {})
                )

        return result

    @staticmethod
    def _build_image_analysis_summary(processed_input: Dict[str, Any]) -> str:
        """Build a brief human-readable summary of image analysis results."""
        metadata = processed_input.get("metadata", {})
        analysis = metadata.get("image_analysis", {})
        if not analysis.get("success"):
            return ""

        parts = []
        description = analysis.get("description", "")
        if description:
            parts.append(description)

        hazards = analysis.get("hazards_detected", [])
        if hazards:
            parts.append(f"Hazards detected: {', '.join(hazards)}")

        severity = analysis.get("severity", "")
        if severity:
            parts.append(f"Severity: {severity.upper()}")

        meter_reading = analysis.get("meter_reading")
        if meter_reading and meter_reading.get("reading"):
            parts.append(
                f"Meter reading: {meter_reading['reading']} "
                f"({meter_reading.get('meter_type', 'unknown')} meter)"
            )

        if not parts:
            return ""

        return "**Image Analysis:** " + ". ".join(parts) + "."

    def _save_media_to_incident(
        self,
        session: Dict[str, Any],
        user_input: Dict[str, Any],
        processed_input: Dict[str, Any],
    ) -> None:
        """Save uploaded image to disk and append to the incident media list."""
        try:
            incident_id = session.get("incident_id")
            if not incident_id:
                return

            raw_b64 = user_input.get("image", "")
            if not raw_b64:
                return

            img_format = user_input.get("format", "jpeg")
            media_id = f"MEDIA_{uuid.uuid4().hex[:10].upper()}"
            ext = img_format if img_format in ("jpeg", "png", "webp", "gif") else "jpeg"
            filename = f"{media_id}.{ext}"

            upload_dir = os.path.join(settings.UPLOAD_DIR, "incidents", incident_id)
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)

            with open(file_path, "wb") as f:
                f.write(base64.b64decode(raw_b64))

            media_entry = IncidentMedia(
                media_id=media_id,
                media_type=MediaType.IMAGE,
                file_path=file_path,
                uploaded_at=datetime.utcnow(),
                metadata={
                    "filename": filename,
                    "content_type": f"image/{ext}",
                    "source": "chatbot",
                    "image_analysis": processed_input.get("metadata", {}).get("image_analysis", {}),
                },
            )

            incident = self.incident_service.get_incident(incident_id)
            if incident:
                incident.media.append(media_entry)
                logger.info(f"Saved incident media {media_id} for {incident_id}")
        except Exception as e:
            logger.error(f"Failed to save media to incident: {e}")

    @staticmethod
    def _match_input_to_option(user_message: str, options: list) -> Optional[str]:
        """Match user input (possibly from voice transcription) against question options.

        Returns the original option string if matched, or None.
        Handles: exact match, punctuation stripping, containment, yes/no variants,
        and word-boundary matching for multi-word options.
        """
        import re as _re

        # Strip punctuation and extra whitespace from voice transcription
        clean_input = _re.sub(r"[^\w\s]", "", user_message).strip().lower()
        logger.debug(f"Option matching: raw='{user_message}' cleaned='{clean_input}' options={options}")
        if not clean_input:
            return None

        option_map = {}  # normalized → original label
        for opt in options:
            # Handle scored option objects: {"label": "Faint", "score": 5}
            if isinstance(opt, dict) and "label" in opt:
                label = str(opt["label"])
            else:
                label = str(opt)
            clean_opt = _re.sub(r"[^\w\s]", "", label).strip().lower()
            option_map[clean_opt] = label

        # 1. Exact match (after cleaning)
        if clean_input in option_map:
            return option_map[clean_input]

        # 2. Yes/No normalization — voice often says "yes I have" / "no I haven't"
        yes_variants = {"yes", "yeah", "yep", "yup", "sure", "correct", "affirmative", "right"}
        no_variants = {"no", "nope", "nah", "negative", "not really", "i havent", "i didnt", "i dont"}
        first_word = clean_input.split()[0] if clean_input.split() else ""

        if "yes" in option_map and (clean_input in yes_variants or first_word in yes_variants):
            return option_map["yes"]
        if "no" in option_map and (clean_input in no_variants or first_word in no_variants):
            return option_map["no"]

        # 3. Input contains exactly one option word/phrase
        #    Use word boundaries for single-word options to avoid false matches
        contained = []
        for norm, orig in option_map.items():
            if " " in norm:
                # Multi-word option: substring match is fine
                if norm in clean_input:
                    contained.append(orig)
            else:
                # Single-word option: require word boundary
                if _re.search(r'\b' + _re.escape(norm) + r'\b', clean_input):
                    contained.append(orig)
        if len(contained) == 1:
            return contained[0]

        # 4. Check if any option word is the primary content word in the input
        #    (handles "I feel nausea" → "Nausea", "it's moderate" → "moderate")
        input_words = set(clean_input.split())
        # Remove common filler words
        fillers = {"i", "its", "the", "a", "an", "is", "am", "feel", "think",
                   "would", "say", "id", "like", "it", "im", "have", "had",
                   "theres", "there", "was", "been", "my", "me", "some", "got"}
        content_words = input_words - fillers
        if content_words:
            matches = [orig for norm, orig in option_map.items()
                       if norm in content_words or any(w in norm.split() for w in content_words)]
            if len(matches) == 1:
                return matches[0]

        logger.info(f"Option matching failed: cleaned='{clean_input}' options={list(option_map.keys())}")
        return None

    def _reprompt_current_question(self, session_id: str, prefix: str = "") -> Dict[str, Any]:
        """Re-send the last question with an optional prefix."""
        session = self.active_sessions[session_id]
        last_q = session.get("last_question_data")

        if last_q:
            msg = prefix + last_q.get("message", "Could you please answer the previous question?")
            data = last_q.get("data", {})
        else:
            msg = prefix + "Could you please answer the current question to continue?"
            data = {}

        self._add_to_history(session_id, "agent", {"message": msg, "action": "reprompt"})
        result = {
            "session_id": session_id,
            "message": msg,
            "action": "question",
            "data": data,
            "completed": False,
        }
        transcript = session.pop("_last_transcript", None)
        if transcript:
            result["user_transcript"] = transcript
        return result

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  PAUSE / RESUME                                                     ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _pause_current_workflow(self, session: Dict[str, Any]) -> None:
        """Snapshot and stash the current workflow so it can be resumed later."""
        execution_id = session.get("execution_id")
        if not execution_id:
            return

        snapshot = {
            "execution_id": execution_id,
            "workflow_id": session.get("workflow_id"),
            "workflow_version": session.get("workflow_version"),
            "use_case": session.get("use_case"),
            "last_question_data": session.get("last_question_data"),
            "paused_at": datetime.utcnow().isoformat(),
        }
        paused = session.get("paused_workflows", [])

        # Enforce max paused limit
        if len(paused) >= MAX_PAUSED_WORKFLOWS:
            oldest = paused.pop(0)
            self._cleanup_execution(oldest.get("execution_id"))
            logger.info(f"Evicted oldest paused workflow: {oldest.get('use_case')}")

        paused.append(snapshot)
        session["paused_workflows"] = paused

        # Clear current workflow fields (but don't destroy the engine state)
        session["execution_id"] = None
        session["workflow_id"] = None
        session["workflow_version"] = None
        session["use_case"] = None
        session["last_question_data"] = None

        sid = session.get("session_id", "?")
        logger.info(f"[{sid}] Paused workflow: {snapshot['use_case']} (exec={execution_id})")

    async def _resume_paused_workflow(
        self, session_id: str, use_case: str, processed_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Restore a paused workflow and continue from where it left off."""
        session = self.active_sessions[session_id]
        paused = session.get("paused_workflows", [])

        # Find the matching paused workflow
        target = None
        for i, snap in enumerate(paused):
            if snap.get("use_case") == use_case:
                target = paused.pop(i)
                break

        if not target:
            logger.warning(f"No paused workflow found for use_case: {use_case}")
            return await self._start_new_workflow(session_id, use_case, use_case, processed_input)

        # Restore session fields
        session["execution_id"] = target["execution_id"]
        session["workflow_id"] = target["workflow_id"]
        session["workflow_version"] = target["workflow_version"]
        session["use_case"] = target["use_case"]
        session["last_question_data"] = target.get("last_question_data")
        self._transition_mode(session, SessionMode.IN_WORKFLOW, f"resumed paused workflow {use_case}")

        logger.info(f"[{session_id}] Resumed paused workflow: {use_case} (exec={target['execution_id']})")

        return self._reprompt_current_question(
            session_id,
            prefix=f"Welcome back! Let's continue with your {use_case.replace('_', ' ')} report. ",
        )

    async def _check_and_offer_resume(
        self, session_id: str, user_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """After completion, parse user's choice about paused workflows."""
        session = self.active_sessions[session_id]
        paused = session.get("paused_workflows", [])
        queued = session.get("queued_incidents", [])

        # ── Extract user message text ──────────────────────────────────────
        if isinstance(user_input, str):
            user_text = user_input
        elif isinstance(user_input, dict):
            user_text = (
                user_input.get("text")
                or user_input.get("message")
                or user_input.get("input")
                or user_input.get("value")
                or ""
            )
        else:
            user_text = str(user_input)

        lower = user_text.strip().lower()

        # ── If user wants to be done / start fresh ─────────────────────────
        done_keywords = [
            "no", "done", "i'm done", "im done", "no thanks",
            "no, i'm done", "no i'm done", "nope", "that's all",
            "finish", "exit", "end", "nothing", "all done",
        ]
        start_new_keywords = [
            "start new", "new report", "new incident",
            "start over", "fresh", "begin new", "report new",
        ]

        wants_done = any(kw in lower for kw in done_keywords)
        wants_new = any(kw in lower for kw in start_new_keywords)

        if wants_done and not wants_new:
            # User is done — clear all paused workflows and complete session
            for snap in paused:
                self._cleanup_execution(snap.get("execution_id"))
            session["paused_workflows"] = []
            session["queued_incidents"] = []
            logger.info(f"[{session_id}] User declined resume — cleared {len(paused)} paused workflows")

            msg = "All done! Your incident has been completed. Feel free to start a new report anytime."
            self._add_to_history(session_id, "agent", {"message": msg, "action": "complete"})
            return {
                "session_id": session_id,
                "message": msg,
                "action": "complete",
                "data": {"incident_id": session.get("incident_id")},
                "completed": True,
            }

        if wants_new:
            # User wants a fresh start — clear everything and reset to IDLE
            for snap in paused:
                self._cleanup_execution(snap.get("execution_id"))
            session["paused_workflows"] = []
            session["queued_incidents"] = []
            session["completed"] = False
            session["execution_id"] = None
            session["workflow_id"] = None
            session["workflow_version"] = None
            session["use_case"] = None
            session["last_question_data"] = None
            session["validation_notice_sent"] = False
            self._transition_mode(session, SessionMode.IDLE, "user requested new report after completion")
            logger.info(f"[{session_id}] User wants to start new report — session reset to IDLE")

            msg = "Sure! Let's start a new incident report. Please describe your gas incident."
            self._add_to_history(session_id, "agent", {"message": msg, "action": "awaiting_incident_report"})
            return {
                "session_id": session_id,
                "message": msg,
                "action": "awaiting_incident_report",
                "data": {},
                "completed": False,
            }

        # ── Check if user selected a specific paused workflow to resume ────
        if paused:
            # Match against paused use case display names
            for snap in paused:
                display_name = snap["use_case"].replace("_", " ").title()
                raw_name = snap["use_case"].replace("_", " ")
                if display_name.lower() in lower or raw_name in lower or snap["use_case"] in lower:
                    # User chose this workflow — resume it
                    session["completed"] = False
                    logger.info(f"[{session_id}] User chose to resume: {snap['use_case']}")
                    processed_input = {"text": user_text, "original_type": "text", "confidence": 1.0, "metadata": {}}
                    return await self._resume_paused_workflow(session_id, snap["use_case"], processed_input)

        # ── If paused workflows exist but user didn't match any option ─────
        if paused:
            use_cases = [s["use_case"].replace("_", " ").title() for s in paused]
            options = use_cases + ["Start New Report", "No, I'm done"]
            msg = (
                "Your previous incident has been completed.\n\n"
                "You still have paused reports:\n"
                + "\n".join(f"• {uc}" for uc in use_cases)
                + "\n\nWould you like to resume any of these, start a new report, or are you done?"
            )
            self._add_to_history(session_id, "agent", {"message": msg, "action": "offer_resume"})
            return {
                "session_id": session_id,
                "message": msg,
                "action": "offer_resume",
                "data": {"options": options, "paused_use_cases": [s["use_case"] for s in paused]},
                "completed": False,
            }

        # ── Handle queued incidents ────────────────────────────────────────
        if queued:
            next_incident = queued.pop(0)
            session["queued_incidents"] = queued
            msg = f"Let's move on to your next issue: \"{next_incident}\""
            session["completed"] = False
            self._transition_mode(session, SessionMode.IDLE, "moving to next queued incident")
            self._add_to_history(session_id, "agent", {"message": msg, "action": "next_queued"})
            return {
                "session_id": session_id,
                "message": msg,
                "action": "next_queued",
                "data": {},
                "completed": False,
            }

        # ── No paused, no queued — session truly complete ──────────────────
        return {
            "session_id": session_id,
            "message": "This incident is already completed. You can start a new report if needed.",
            "action": "complete",
            "data": {"incident_id": session.get("incident_id")},
            "completed": True,
        }

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  STABILITY CONTROLS                                                 ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _record_switch(self, session: Dict[str, Any]) -> None:
        """Record a workflow switch for rate-limiting."""
        session["switch_count"] = session.get("switch_count", 0) + 1
        timestamps = session.get("switch_timestamps", [])
        timestamps.append(time.time())
        session["switch_timestamps"] = timestamps

    def _check_stability(self, session: Dict[str, Any]) -> Optional[str]:
        """Return an error message if switching too frequently, else None."""
        now = time.time()
        timestamps = session.get("switch_timestamps", [])

        # Prune old timestamps
        recent = [t for t in timestamps if now - t < SWITCH_WINDOW_SECONDS]
        session["switch_timestamps"] = recent

        if len(recent) >= MAX_SWITCHES_PER_WINDOW:
            sid = session.get("session_id", "?")
            logger.info(f"[{sid}] Stability: max switches exceeded ({len(recent)}/{SWITCH_WINDOW_SECONDS}s)")
            return (
                f"You've switched topics {len(recent)} times in the last few minutes. "
                "Let's focus on one issue at a time to make sure we resolve it properly."
            )
        return None

    def _handle_stability_exceeded(self, session_id: str, message: str) -> Dict[str, Any]:
        """Return a gentle redirect when switching too fast."""
        self._add_to_history(session_id, "agent", {"message": message, "action": "stability_warning"})
        return self._reprompt_current_question(session_id, prefix=message + "\n\n")

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  SMALL TALK                                                         ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _generate_small_talk_response(self, user_message: str) -> str:
        """Generate a brief, friendly response and nudge back to the workflow."""
        # Keyword-based response
        lower = user_message.strip().lower()

        if any(g in lower for g in ["hello", "hi", "hey"]):
            return "Hello! I'm here to help with your gas incident. Let's continue with the questions so we can assist you properly."
        if any(g in lower for g in ["thanks", "thank you", "thx"]):
            return "You're welcome! Let's keep going with the questions to resolve your issue."
        if any(g in lower for g in ["ok", "okay", "sure", "alright"]):
            return "Great! Let's continue."
        if any(g in lower for g in ["bye", "goodbye", "see you"]):
            return "If you'd like to finish reporting your incident first, I'm here to help. Otherwise, feel free to come back anytime!"
        if "?" in lower:
            return "That's a good question! For now though, let me focus on getting the details of your incident so we can help you as quickly as possible."

        return "I understand! Let's get back to your incident report so we can assist you properly."


    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  MODE MANAGEMENT                                                    ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _get_mode(self, session: Dict[str, Any]) -> SessionMode:
        mode = session.get("mode", SessionMode.IDLE)
        if isinstance(mode, str):
            try:
                return SessionMode(mode)
            except ValueError:
                return SessionMode.IDLE
        return mode

    def _transition_mode(self, session: Dict[str, Any], new_mode: SessionMode, reason: str = "") -> None:
        old_mode = self._get_mode(session)
        if old_mode != new_mode:
            sid = session.get("session_id", "?")
            logger.info(f"[{sid}] Mode: {old_mode.value} -> {new_mode.value}" + (f" ({reason})" if reason else ""))
            mode_history = session.get("mode_history", [])
            mode_history.append({
                "from": old_mode.value,
                "to": new_mode.value,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
            })
            session["mode_history"] = mode_history
        session["mode"] = new_mode

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  ENGINE RESPONSE HANDLING                                           ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    async def _handle_engine_response(
        self,
        session_id: str,
        engine_response: Dict[str, Any],
        input_type: str,
    ) -> Dict[str, Any]:
        session = self.active_sessions[session_id]
        message = str(engine_response.get("message", ""))
        action = str(engine_response.get("action", ""))
        data = dict(engine_response.get("data", {}))

        # Sync workflow engine variables -> session structured_data
        engine_variables = engine_response.get("variables", {})
        if engine_variables:
            session["structured_data"].update(engine_variables)

        validation_snapshot = self._evaluate_decision_support(
            structured_data=session.get("structured_data", {}),
            use_case=session.get("use_case", ""),
            workflow_outcome=data.get("outcome"),
        )
        if validation_snapshot:
            session["structured_data"]["_live_validation"] = validation_snapshot["payload"]
            data["validation_status"] = validation_snapshot["payload"]

        # Final decision path
        if engine_response.get("is_complete") or "outcome" in data:
            outcome = data.get("outcome")
            final_payload = await self._finalize_decision(session_id, outcome, data)
            self._add_to_history(session_id, "agent", {"message": final_payload["message"], "action": "complete"})
            final_payload["input_type"] = input_type
            return final_payload

        # Store last question for reprompt capability
        if action == "question":
            session["last_question_data"] = {"message": message, "data": data}

        # Question path — enhance with AI
        enhanced_message = message

        if not enhanced_message or not enhanced_message.strip():
            logger.warning(f"Enhanced message is empty, using original: {message}")
            enhanced_message = message

        self._add_to_history(session_id, "agent", {"message": enhanced_message, "action": action, "data": data})
        result = {
            "session_id": session_id,
            "message": enhanced_message,
            "action": action,
            "data": data,
            "completed": False,
            "input_type": input_type,
        }
        # Attach voice transcript so frontend can update the "transcribing..." bubble
        transcript = session.pop("_last_transcript", None)
        if transcript:
            result["user_transcript"] = transcript
        return result

    async def _finalize_decision(
        self,
        session_id: str,
        outcome: Optional[str],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        session = self.active_sessions[session_id]
        execution_id = session.get("execution_id")
        incident_id = self._ensure_incident(session)
        structured_data = session.get("structured_data", {})
        use_case = session.get("use_case", "")

        session["completed"] = True
        session["completed_at"] = datetime.utcnow()

        if execution_id:
            self._cleanup_execution(execution_id)

        workflow_outcome = outcome
        decision_support = self._evaluate_decision_support(
            structured_data=structured_data,
            use_case=use_case,
            workflow_outcome=workflow_outcome,
        ) or {}

        kb_result = decision_support.get("kb_result")
        risk_result = decision_support.get("risk_result")
        validated_outcome = decision_support.get("validated_outcome")
        # The workflow's own decision is the source of truth. Keep KB/risk
        # validation as supporting metadata only and do not let it override the
        # workflow outcome.
        final_outcome = workflow_outcome or validated_outcome
        outcome_enum = self._map_outcome(final_outcome)

        if outcome_enum:
            risk_score = self._risk_from_outcome(outcome_enum)
            confidence_score = 1.0
        elif risk_result:
            risk_score = risk_result["final_risk_score"]
            confidence_score = risk_result["confidence_score"]
        else:
            risk_score = 0.5
            confidence_score = 0.5

        kb_similarity = decision_support.get("kb_similarity")
        kb_match_type = decision_support.get("kb_match_type")

        # Store KB + risk results in structured_data for frontend display
        structured_data["_kb_validation"] = {
            "verdict": kb_match_type,
            "true_kb_score": round(kb_result.get("true_kb_match", 0), 3) if kb_result else 0,
            "false_kb_score": round(kb_result.get("false_kb_match", 0), 3) if kb_result else 0,
            "confidence": round(kb_result.get("confidence", 0), 3) if kb_result else 0,
            "explicit_split": bool(kb_result.get("explicit_split", False)) if kb_result else False,
            "best_match_id": kb_result.get("best_match_id") if kb_result else None,
            "matched_kb_id": kb_result.get("best_match_id") if kb_result else None,
            "explanation": kb_result.get("explanation", "") if kb_result else "",
            "matched_entry": kb_result.get("matched_entry") if kb_result else None,
            "all_matches": kb_result.get("all_matches", []) if kb_result else [],
        }
        
        # Debug logging for KB validation
        logger.info(f"[{session_id}] KB Validation Result: verdict={kb_match_type}, "
                   f"true_score={kb_result.get('true_kb_match', 0) if kb_result else 0:.3f}, "
                   f"false_score={kb_result.get('false_kb_match', 0) if kb_result else 0:.3f}, "
                   f"confidence={kb_result.get('confidence', 0) if kb_result else 0:.3f}, "
                   f"has_matched_entry={bool(kb_result.get('matched_entry')) if kb_result else False}")
        structured_data["_risk_assessment"] = {
            "preliminary_score": round(risk_result.get("preliminary_risk_score", 0), 3) if risk_result else round(risk_score, 3),
            "kb_adjusted_score": round(risk_result.get("kb_adjusted_risk_score", 0), 3) if risk_result else round(risk_score, 3),
            "final_score": round(risk_score, 3),
            "confidence": round(confidence_score, 3),
            "decision": final_outcome,
            "risk_factors": risk_result.get("risk_factors", {}) if risk_result else {},
        }
        structured_data["_decision_trace"] = {
            "workflow_outcome": workflow_outcome,
            "validated_outcome": validated_outcome,
            "final_outcome": final_outcome,
        }
        session["structured_data"] = structured_data

        # ── Finalize incident ─────────────────────────────────────────
        if incident_id and outcome_enum:
            self.incident_service.finalize_incident(
                incident_id=incident_id,
                outcome=outcome_enum,
                risk_score=risk_score,
                confidence_score=confidence_score,
                kb_similarity_score=kb_similarity,
                kb_match_type=kb_match_type,
                kb_validation_details=kb_result,
                workflow_execution_id=execution_id,
            )
            self.incident_service.update_incident(
                incident_id,
                structured_data=structured_data,
            )
        elif incident_id:
            self.incident_service.update_incident(
                incident_id,
                status=IncidentStatus.COMPLETED,
                workflow_execution_id=execution_id,
                completed_at=datetime.utcnow(),
                structured_data=structured_data,
            )

        # ── Persist conversation history ──────────────────────────────
        if incident_id:
            chat_history = session.get("conversation_history", [])
            if chat_history:
                self.incident_service.update_incident(incident_id, conversation_history=chat_history)
                logger.info(f"[{session_id}] Saved {len(chat_history)} chat messages to incident {incident_id}")

        message = self._format_completion_message(
            final_outcome,
            incident_id,
            workflow_message=data.get("decision_message"),
            workflow_outcome=workflow_outcome,
            validation_details=decision_support.get("payload"),
        )

        # Check if there are paused workflows to offer resuming
        paused = session.get("paused_workflows", [])
        queued = session.get("queued_incidents", [])
        if paused:
            use_cases = [s["use_case"].replace("_", " ").title() for s in paused]
            message += (
                "\n\nYou also have paused reports:\n"
                + "\n".join(f"• {uc}" for uc in use_cases)
                + "\n\nWould you like to resume any of these, start a new report, or are you done?"
            )
            data["options"] = use_cases + ["Start New Report", "No, I'm done"]
            data["paused_use_cases"] = [s["use_case"] for s in paused]
        elif queued:
            message += f"\n\nYou also mentioned another issue. I'll help you with that next."

        return {
            "session_id": session_id,
            "message": message,
            "action": "complete",
            "data": {
                **data,
                "outcome": final_outcome,
                "workflow_outcome": workflow_outcome,
                "validated_outcome": validated_outcome,
                "incident_id": incident_id,
                "kb_validation": structured_data["_kb_validation"],
                "risk_assessment": structured_data["_risk_assessment"],
            },
            "completed": True if not (paused or queued) else False,
            "incident_id": incident_id,
        }

    def _cleanup_execution(self, execution_id: str) -> None:
        """Remove an execution from the engine's active state."""
        self.workflow_engine.active_executions.pop(execution_id, None)
        if hasattr(self.workflow_engine, "_execution_workflows"):
            self.workflow_engine._execution_workflows.pop(execution_id, None)


    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  INCIDENT & WORKFLOW HELPERS (preserved from original)              ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _ensure_incident(self, session: Dict[str, Any], description: Optional[str] = None) -> str:
        incident_id = session.get("incident_id")
        use_case = session.get("use_case")

        if incident_id and self.incident_service.get_incident(incident_id):
            self.incident_service.update_incident(
                incident_id,
                classified_use_case=use_case,
                status=IncidentStatus.IN_PROGRESS,
                workflow_execution_id=session.get("execution_id"),
                reference_id=session.get("reference_id"),
                structured_data=session.get("structured_data", {}),
            )
            return incident_id

        if not description:
            history = session.get("conversation_history", [])
            description = ""
            for item in history:
                if item.get("role") == "user":
                    content = item.get("content", {})
                    description = content.get("message", "")
                    if description:
                        break

        details = session.get("user_details", {})
        initial_data = session.get("initial_data", {})
        reported_location = (
            initial_data.get("location")
            or initial_data.get("location_text")
            or details.get("address")
        )
        reported_geo = (
            initial_data.get("geo_location")
            or initial_data.get("user_geo_location")
            or initial_data.get("geoLocation")
        )
        incident = self.incident_service.create_incident(
            tenant_id=session["tenant_id"],
            user_id=session["user_id"],
            description=description or "Gas incident reported",
            incident_type=use_case,
            user_name=details.get("name"),
            user_phone=details.get("phone"),
            user_address=details.get("address"),
            location=reported_location,
            geo_location=reported_geo,
            user_geo_location=reported_geo,
            structured_data=session.get("structured_data", {}),
            reference_id=session.get("reference_id"),
            reported_by_staff_id=session.get("reported_by_staff_id"),
        )
        session["incident_id"] = incident.incident_id
        return incident.incident_id

    async def _get_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """Fetch runtime tenant config for persona/routing behavior."""
        try:
            db = get_database()
            if db is None:
                return {}
            doc = await db.tenants.find_one({"tenant_id": tenant_id}, {"_id": 0, "config": 1})
            return (doc or {}).get("config", {}) or {}
        except Exception:
            logger.exception("Failed to load tenant config: tenant=%s", tenant_id)
            return {}

    async def _get_latest_workflow(self, tenant_id: str, classified_use_case: str):
        logger.debug(f"Searching for workflow: tenant='{tenant_id}', use_case='{classified_use_case}'")
        config = await self._get_tenant_config(tenant_id)
        default_routing = config.get("default_workflow_routing") or {}

        for candidate in self._candidate_use_cases(classified_use_case):
            override_workflow_id = default_routing.get(candidate)
            if override_workflow_id:
                override_workflow = workflow_repository.get_by_id(override_workflow_id)
                if override_workflow and override_workflow.tenant_id == tenant_id:
                    logger.debug("Using tenant workflow override: %s", override_workflow_id)
                    return override_workflow

            logger.debug(f"  Trying candidate: '{candidate}'")
            workflow_def = workflow_repository.get_latest_by_tenant_use_case(tenant_id, candidate)
            if workflow_def is not None:
                logger.debug(f"  Found workflow: {workflow_def.workflow_id}")
                return workflow_def
        logger.warning("No workflow found for any candidate use cases")
        return None

    def _candidate_use_cases(self, use_case: str):
        normalized = (use_case or "").strip().lower().replace(" ", "_")
        candidates = [normalized] if normalized else []
        for suffix in ("_report", "_issue", "_triggered", "_malfunction", "_suspected", "_request"):
            if normalized.endswith(suffix):
                base = normalized[: -len(suffix)]
                if base and base not in candidates:
                    candidates.append(base)
        return candidates

    def _evaluate_decision_support(
        self,
        structured_data: Dict[str, Any],
        use_case: str,
        workflow_outcome: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not structured_data or not use_case:
            return None

        kb_result = None
        try:
            kb_result = self.kb_service.verify_incident(structured_data, use_case)
        except Exception as exc:
            logger.error("KB verification failed for %s: %s", use_case, exc)
            kb_result = {
                "true_kb_match": 0.0,
                "false_kb_match": 0.0,
                "best_match_type": "false",
                "best_match_id": None,
                "confidence_adjustment": 0.0,
                "explanation": "KB verification unavailable; defaulting to false incident classification",
            }

        property_type = structured_data.get("property_type", "residential")
        risk_result = None
        try:
            risk_result = self.risk_calculator.calculate_enhanced_risk(
                structured_data=structured_data,
                kb_verification=kb_result,
                property_type=property_type,
            )
        except Exception as exc:
            logger.error("Risk calculation failed for %s: %s", use_case, exc)

        validated_outcome = risk_result.get("decision") if risk_result else workflow_outcome
        kb_similarity = kb_result.get("confidence", 0.0) if kb_result else None
        kb_match_type = kb_result.get("best_match_type") if kb_result else None

        payload = {
            "mode": "kb_and_risk",
            "status": "active",
            "kb_verdict": kb_match_type or "false",
            "true_kb_score": round(kb_result.get("true_kb_match", 0.0), 3) if kb_result else 0.0,
            "false_kb_score": round(kb_result.get("false_kb_match", 0.0), 3) if kb_result else 0.0,
            "confidence": round(kb_result.get("confidence", 0.0), 3) if kb_result else 0.0,
            "explicit_split": bool(kb_result.get("explicit_split", False)) if kb_result else False,
            "preliminary_score": round(risk_result.get("preliminary_risk_score", 0.0), 3) if risk_result else None,
            "kb_adjusted_score": round(risk_result.get("kb_adjusted_risk_score", 0.0), 3) if risk_result else None,
            "final_score": round(risk_result.get("final_risk_score", 0.0), 3) if risk_result else None,
            "provisional_decision": validated_outcome,
            "explanation": kb_result.get("explanation", "") if kb_result else "",
        }

        return {
            "kb_result": kb_result,
            "risk_result": risk_result,
            "validated_outcome": validated_outcome,
            "kb_similarity": kb_similarity,
            "kb_match_type": kb_match_type,
            "payload": payload,
        }

    def _select_outcome(
        self,
        workflow_outcome: Optional[str],
        validated_outcome: Optional[str],
    ) -> Optional[str]:
        if not workflow_outcome:
            return validated_outcome
        if not validated_outcome:
            return workflow_outcome

        severity = {
            "false_report": 0,
            "close_with_guidance": 1,
            "monitor": 2,
            "schedule_engineer": 3,
            "emergency_dispatch": 4,
        }
        workflow_rank = severity.get(workflow_outcome, 1)
        validated_rank = severity.get(validated_outcome, 1)
        return workflow_outcome if workflow_rank >= validated_rank else validated_outcome

    def _map_outcome(self, outcome: Optional[str]) -> Optional[IncidentOutcome]:
        if not outcome:
            return None
        try:
            return IncidentOutcome(str(outcome))
        except ValueError:
            return None

    def _format_completion_message(
        self,
        outcome: Optional[str],
        incident_id: str,
        workflow_message: Optional[str] = None,
        workflow_outcome: Optional[str] = None,
        validation_details: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not outcome:
            return "Thank you for reporting. Your incident has been logged."

        reference_id = incident_id.replace("INC-", "REF-", 1)

        outcome_messages = {
            "emergency_dispatch": (
                "Incident Logged - Emergency Response Required\n\n"
                "Thank you for reporting this. Based on your responses, this incident needs urgent attention.\n\n"
                "What happens next:\n"
                "- Your case has been marked as high priority\n"
                "- Emergency response is being arranged\n"
                "- Our team will treat this as urgent\n\n"
                f"Reference ID: {reference_id}\n\n"
                "What you should do now:\n"
                "- Stay out of the property if you are already outside\n"
                "- Open doors and windows if this can be done safely\n"
                "- Do not use gas appliances\n"
                "- Call 999 immediately if anyone is unwell\n"
                "- Contact us again straight away if conditions worsen"
            ),
            "schedule_engineer": (
                "Incident Logged - Engineer Dispatch Required\n\n"
                "Thank you for reporting this gas concern. Based on your responses, "
                "we need to send a qualified engineer to inspect the situation.\n\n"
                "What happens next:\n"
                "- A field engineer will be assigned shortly\n"
                "- You'll receive a call to schedule the visit\n"
                "- Expected response time: Within 4 hours\n\n"
                f"Reference ID: {reference_id}\n\n"
                "What you should do now:\n"
                "- Keep the area well ventilated\n"
                "- Avoid using appliances if you are concerned they may be involved\n"
                "- Contact us again straight away if the situation worsens"
            ),
            "monitor": (
                "Incident Logged - Monitoring Required\n\n"
                "Thank you for reporting this. We've logged your incident and will continue to monitor the situation.\n\n"
                "What happens next:\n"
                "- Your report will be reviewed by our team\n"
                "- We may contact you for additional information\n"
                "- If needed, we'll arrange a follow-up inspection\n\n"
                f"Reference ID: {reference_id}\n\n"
                "What you should do now:\n"
                "- Keep the area well ventilated\n"
                "- Monitor for any changes in the alarm or symptoms\n"
                "- Avoid using appliances if you are concerned they may be involved\n"
                "- Contact us again straight away if the situation worsens"
            ),
            "close_with_guidance": (
                "Incident Logged - Safety Guidance Provided\n\n"
                "Thank you for reporting this concern. Based on your responses, "
                "this appears to be a low-risk situation that can be managed with guidance.\n\n"
                "What happens next:\n"
                "- Your report has been logged for our records\n"
                "- No emergency response is being arranged at this time\n"
                "- You can contact us again if anything changes\n\n"
                f"Reference ID: {reference_id}\n\n"
                "What you should do now:\n"
                "- Keep the area well ventilated\n"
                "- Follow the alarm or appliance guidance given during this chat\n"
                "- Replace or service the alarm if it shows battery, fault, or end-of-life warnings\n"
                "- Contact us again if the alarm pattern changes or anyone feels unwell"
            ),
            "false_report": (
                "Incident Logged\n\n"
                "Thank you for your vigilance in reporting this. Based on the information provided, "
                "this does not appear to require immediate action.\n\n"
                f"Your report has been logged for our records. Reference ID: {reference_id}\n\n"
                "If you have any concerns or notice any changes, please don't hesitate to contact us again."
            ),
        }

        message = outcome_messages.get(
            outcome,
            f"Incident Logged\n\nYour incident has been logged. Reference ID: {reference_id}",
        )

        return message

    def _risk_from_outcome(self, outcome: IncidentOutcome) -> float:
        if outcome == IncidentOutcome.EMERGENCY_DISPATCH:
            return 1.0
        if outcome == IncidentOutcome.SCHEDULE_ENGINEER:
            return 0.7
        if outcome == IncidentOutcome.MONITOR:
            return 0.4
        if outcome == IncidentOutcome.CLOSE_WITH_GUIDANCE:
            return 0.1
        return 0.0

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  MULTIMODAL INPUT                                                   ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    async def _process_multimodal_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize text/audio/video/image payloads into text."""
        if isinstance(user_input, str):
            return {"text": user_input, "original_type": "text", "confidence": 1.0, "metadata": {}}

        if not isinstance(user_input, dict):
            return {"text": str(user_input), "original_type": "text", "confidence": 1.0, "metadata": {}}

        if "audio" in user_input:
            return await self.multimodal_processor.process_input(
                {"type": "audio", "content": user_input.get("audio"),
                 "format": user_input.get("format", "webm"), "metadata": user_input.get("metadata", {})}
            )

        if "video" in user_input:
            return await self.multimodal_processor.process_input(
                {"type": "video", "content": user_input.get("video"),
                 "format": user_input.get("format", "webm"), "metadata": user_input.get("metadata", {})}
            )

        if "image" in user_input:
            return await self.multimodal_processor.process_input(
                {"type": "image", "content": user_input.get("image"),
                 "format": user_input.get("format", "jpeg"), "metadata": user_input.get("metadata", {})}
            )

        if "type" in user_input and "content" in user_input:
            return await self.multimodal_processor.process_input(user_input)

        text = (
            user_input.get("text")
            or user_input.get("message")
            or user_input.get("input")
            or user_input.get("value")
        )
        if isinstance(text, str):
            return {"text": text, "original_type": "text", "confidence": 1.0, "metadata": user_input.get("metadata", {})}

        return {
            "text": json.dumps(user_input, default=str),
            "original_type": "text",
            "confidence": 1.0,
            "metadata": user_input.get("metadata", {}),
        }

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  HISTORY & PUBLIC API (preserved)                                   ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _add_to_history(self, session_id: str, role: str, content: Any):
        session = self.active_sessions.get(session_id)
        if session:
            session["conversation_history"].append(
                {"timestamp": datetime.utcnow().isoformat(), "role": role, "content": content}
            )

    def get_conversation_history(self, session_id: str) -> list:
        session = self.active_sessions.get(session_id)
        if session:
            return session.get("conversation_history", [])
        return []

    # ── Session disconnect / pause persistence ────────────────────────────

    def handle_disconnect(self, session_id: str) -> None:
        """Called when a WebSocket disconnects.

        If the session has an active (incomplete) workflow, snapshot
        it onto the incident so the user can resume later.
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return

        # Nothing to persist if the workflow already completed
        if session.get("completed"):
            self.active_sessions.pop(session_id, None)
            return

        incident_id = session.get("incident_id")
        execution_id = session.get("execution_id")

        if incident_id and execution_id:
            # Build a resumable snapshot
            execution_state = self.workflow_engine.active_executions.get(execution_id)
            snapshot = {
                "execution_id": execution_id,
                "workflow_id": session.get("workflow_id"),
                "workflow_version": session.get("workflow_version"),
                "use_case": session.get("use_case"),
                "last_question_data": session.get("last_question_data"),
                "conversation_history": session.get("conversation_history", []),
                "structured_data": session.get("structured_data", {}),
                "paused_at": datetime.utcnow().isoformat(),
            }
            # Include execution variables if available
            if execution_state:
                snapshot["variables"] = dict(execution_state.variables)
                snapshot["current_node_id"] = execution_state.current_node_id

            self.incident_service.update_incident(
                incident_id,
                status=IncidentStatus.PAUSED,
                workflow_snapshot=snapshot,
            )
            logger.info(
                f"[{session_id}] Session disconnected — incident {incident_id} "
                f"marked PAUSED with workflow snapshot"
            )

        # Clean up the in-memory session
        self.active_sessions.pop(session_id, None)

    def get_paused_incidents(self, user_id: str, tenant_id: Optional[str] = None) -> list:
        """Return incidents the user can resume."""
        return self.incident_service.get_paused_incidents(user_id, tenant_id)

    async def resume_incident(
        self, session_id: str, incident_id: str,
    ) -> Dict[str, Any]:
        """Restore a paused incident's workflow into the given session."""
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        incident = self.incident_service.get_incident(incident_id)
        if not incident or not incident.workflow_snapshot:
            raise ValueError(f"Incident {incident_id} has no resumable state")

        snap = incident.workflow_snapshot
        use_case = snap.get("use_case", "")

        # Re-create the workflow execution in the engine
        workflow_def = await self._get_latest_workflow(session["tenant_id"], use_case)
        if not workflow_def:
            raise ValueError(f"No workflow found for use_case: {use_case}")

        state = await self.workflow_engine.start_execution(
            workflow_def.workflow_id, session["tenant_id"],
        )
        # Restore variables and position from snapshot
        if snap.get("variables"):
            state.variables.update(snap["variables"])
        if snap.get("current_node_id"):
            state.current_node_id = snap["current_node_id"]

        session["execution_id"] = state.execution_id
        session["workflow_id"] = workflow_def.workflow_id
        session["workflow_version"] = workflow_def.version
        session["use_case"] = use_case
        session["incident_id"] = incident_id
        session["last_question_data"] = snap.get("last_question_data")
        session["structured_data"] = snap.get("structured_data", {})
        session["conversation_history"] = snap.get("conversation_history", [])
        self._transition_mode(session, SessionMode.IN_WORKFLOW, f"resumed paused incident {incident_id}")

        # Mark incident back to IN_PROGRESS
        self.incident_service.update_incident(
            incident_id,
            status=IncidentStatus.IN_PROGRESS,
            workflow_snapshot=None,
        )

        logger.info(f"[{session_id}] Resumed paused incident {incident_id} (use_case={use_case})")

        return self._reprompt_current_question(
            session_id,
            prefix=f"Welcome back! Let's continue with your {use_case.replace('_', ' ')} report. ",
        )

    def get_user_incidents(self, user_id: str, tenant_id: Optional[str] = None) -> list:
        return self.incident_service.get_user_incidents(user_id, tenant_id)

    def get_company_incidents(self, tenant_id: str, status_filter: Optional[list] = None, connector_scope: Optional[list] = None) -> list:
        return self.incident_service.get_company_incidents(tenant_id, status_filter, connector_scope)

    def get_incident(self, incident_id: str):
        return self.incident_service.get_incident(incident_id)

    def assign_agent_to_incident(self, incident_id: str, agent_id: str):
        return self.incident_service.assign_agent(incident_id, agent_id)

    def mark_incident_resolved(
        self,
        incident_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None,
        items_used: Optional[list] = None,
        resolution_checklist: Optional[Dict[str, Any]] = None,
        add_to_kb: bool = True,
        resolution_media: Optional[list] = None,
    ):
        return self.incident_service.mark_resolved(
            incident_id,
            resolved_by,
            resolution_notes,
            items_used,
            resolution_checklist,
            kb_service=self.kb_service, add_to_kb=add_to_kb,
            resolution_media=resolution_media,
        )

    def company_approve_resolution(
        self,
        incident_id: str,
        approved_by: str,
        approval_notes: Optional[str] = None,
    ):
        return self.incident_service.company_approve_resolution(
            incident_id, approved_by, approval_notes
        )

    def get_incident_stats(self, tenant_id: str, connector_scope: Optional[list] = None) -> Dict[str, Any]:
        return self.incident_service.get_incident_stats(tenant_id, connector_scope)

    def search_kb(self, query: str, kb_type: Optional[str] = None, limit: int = 10):
        return self.kb_service.search_kb(query, kb_type, limit)

    def get_true_incidents_kb(self):
        return self.kb_service.get_true_incidents()

    def get_false_incidents_kb(self):
        return self.kb_service.get_false_incidents()

    def add_to_true_kb(self, incident_data: Dict[str, Any]) -> str:
        return self.kb_service.add_true_incident(incident_data)

    def add_to_false_kb(self, incident_data: Dict[str, Any]) -> str:
        return self.kb_service.add_false_incident(incident_data)


