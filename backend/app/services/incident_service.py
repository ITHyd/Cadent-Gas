"""Incident Service for persistence and lifecycle management"""
import asyncio
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import uuid

from app.core.mongodb import get_database
from app.models.incident import (
    Incident, IncidentStatus, IncidentOutcome, IncidentMedia, Agent
)
from app.services.text_validator import validate_resolution_text_fields

logger = logging.getLogger(__name__)

# ── SLA Configuration ─────────────────────────────────────────────────────
# Base SLA hours by outcome type
SLA_BASE_HOURS = {
    IncidentOutcome.EMERGENCY_DISPATCH: 1.0,
    IncidentOutcome.SCHEDULE_ENGINEER: 4.0,
    IncidentOutcome.MONITOR: 24.0,
    IncidentOutcome.CLOSE_WITH_GUIDANCE: 0.0,
    IncidentOutcome.FALSE_REPORT: 0.0,
}

# Location-based SLA multipliers
SLA_LOCATION_MULTIPLIERS = {
    "urban": 1.0,
    "suburban": 1.5,
    "rural": 2.0,
    "remote": 3.0,
}

# Keywords to classify location type
URBAN_KEYWORDS = ["city", "downtown", "central", "metro", "urban", "london", "manchester", "birmingham", "leeds", "glasgow"]
SUBURBAN_KEYWORDS = ["suburb", "residential", "housing estate", "housing", "estate", "outskirts", "town"]
RURAL_KEYWORDS = ["rural", "village", "countryside", "farm", "remote", "island"]

# Agent-field milestone catalog
FIELD_MILESTONE_CATALOG = {
    "depart": {
        "label": "Departed Base",
        "message": "Engineer has departed and is en route.",
        "agent_status": "EN_ROUTE",
    },
    "arrived_perimeter": {
        "label": "Arrived Nearby",
        "message": "Engineer has arrived near the incident location.",
        "agent_status": "EN_ROUTE",
    },
    "on_site": {
        "label": "On Site",
        "message": "Engineer has arrived on site.",
        "agent_status": "ON_SITE",
    },
    "diagnosis_started": {
        "label": "Diagnosis Started",
        "message": "Engineer started root-cause diagnosis.",
        "agent_status": "IN_PROGRESS",
    },
    "repair_started": {
        "label": "Repair Started",
        "message": "Repair work is now in progress.",
        "agent_status": "IN_PROGRESS",
    },
    "verification_passed": {
        "label": "Verification Passed",
        "message": "Post-repair verification passed safety checks.",
        "agent_status": "IN_PROGRESS",
    },
    "handoff_done": {
        "label": "Customer Handoff Complete",
        "message": "Engineer completed customer handoff.",
        "agent_status": "COMPLETED",
    },
}

TERMINAL_ASSISTANCE_STATUSES = {"FULFILLED", "REJECTED", "CANCELLED"}
TERMINAL_ITEM_STATUSES = {"USED", "REJECTED", "CANCELLED"}

# ── Per-request SLA deadlines (minutes) by priority ─────────────────────
REQUEST_SLA_MINUTES = {
    "CRITICAL": 15,
    "HIGH": 30,
    "MEDIUM": 60,
    "NORMAL": 120,
    "LOW": 240,
}

ITEM_SLA_MINUTES = {
    "URGENT": 20,
    "HIGH": 45,
    "NORMAL": 90,
    "LOW": 180,
}


class IncidentService:
    """
    Service for managing incident lifecycle:
    - Create and persist incidents
    - Update status and outcomes
    - Assign agents
    - Mark resolved
    - Query incidents by user/company
    """

    # Travel time estimates in minutes by location type
    TRAVEL_MINUTES = {
        "urban": 20,
        "suburban": 35,
        "rural": 60,
        "remote": 90,
    }

    # Intake-only incidents should not reserve a REF forever.
    _NON_BLOCKING_REFERENCE_STATUSES = {
        IncidentStatus.NEW,
        IncidentStatus.CLASSIFYING,
        IncidentStatus.WAITING_INPUT,
        IncidentStatus.ANALYZING,
        IncidentStatus.PAUSED,
    }

    def __init__(self):
        # In-memory storage (in production, use database)
        self.incidents: Dict[str, Incident] = {}
        self.agents: Dict[str, Agent] = {}
        self._incident_sequence = 1000
        # In-app notification store:  user_id -> [notification_dicts]
        self.user_notifications: Dict[str, List[Dict[str, Any]]] = {}
        # Tenant → user_id caches for notification routing
        self._company_users_by_tenant: Dict[str, List[str]] = {}
        self._agent_users_by_tenant: Dict[str, List[str]] = {}
        # Connector sync service (injected at startup, optional)
        self._sync_service = None
        self._seed_agents()

    async def load_from_db(self, db=None) -> None:
        if db is None:
            db = get_database()
        if db is None:
            return

        docs = await db.incidents.find({}, {"_id": 0}).to_list(None)
        self.incidents = {}
        max_existing = self._incident_sequence

        for doc in docs:
            try:
                incident = Incident.model_validate(doc)
                self.incidents[incident.incident_id] = incident
                match = re.fullmatch(r"INC-(\d+)", str(incident.incident_id).upper())
                if match:
                    max_existing = max(max_existing, int(match.group(1)))
            except Exception as exc:
                logger.error("Failed to hydrate incident from MongoDB: %s", exc)

        self._incident_sequence = max_existing
        logger.info("Loaded incidents from MongoDB: %d", len(self.incidents))

        notif_docs = await db.user_notifications.find({}, {"_id": 0}).sort(
            [("user_id", 1), ("created_at", -1)]
        ).to_list(None)
        self.user_notifications = {}
        for notif in notif_docs:
            uid = notif.get("user_id")
            if not uid:
                continue
            self.user_notifications.setdefault(uid, []).append(notif)
        for uid in list(self.user_notifications.keys()):
            self.user_notifications[uid] = self.user_notifications[uid][:100]
        logger.info("Loaded notifications from MongoDB: %d", len(notif_docs))

        agent_docs = await db.agents.find({}, {"_id": 0}).to_list(None)
        if agent_docs:
            self.agents = {}
            for doc in agent_docs:
                try:
                    agent = Agent.model_validate(doc)
                    self.agents[agent.agent_id] = agent
                except Exception as exc:
                    logger.error("Failed to hydrate agent from MongoDB: %s", exc)
            logger.info("Loaded agents from MongoDB: %d", len(self.agents))
        else:
            for agent in self.agents.values():
                await self._persist_agent(agent)
            logger.info("Seeded agents to MongoDB: %d", len(self.agents))

    async def _persist_incident(self, incident: Incident) -> None:
        db = get_database()
        if db is None:
            return
        await db.incidents.replace_one(
            {"incident_id": incident.incident_id},
            incident.model_dump(mode="json"),
            upsert=True,
        )

    async def _persist_notification(self, notification: Dict[str, Any]) -> None:
        db = get_database()
        if db is None:
            return
        await db.user_notifications.replace_one(
            {"notification_id": notification["notification_id"]},
            dict(notification),
            upsert=True,
        )

    async def _persist_agent(self, agent: Agent) -> None:
        db = get_database()
        if db is None:
            return
        await db.agents.replace_one(
            {"agent_id": agent.agent_id},
            agent.model_dump(mode="json"),
            upsert=True,
        )

    async def _delete_incident_from_db(self, incident_id: str) -> None:
        db = get_database()
        if db is None:
            return
        await db.incidents.delete_one({"incident_id": incident_id})

    def _schedule_persist_incident(self, incident: Optional[Incident]) -> None:
        if incident is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist_incident(incident))
        except RuntimeError:
            pass

    def _schedule_persist_notification(self, notification: Optional[Dict[str, Any]]) -> None:
        if notification is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist_notification(notification))
        except RuntimeError:
            pass

    def _schedule_persist_agent(self, agent: Optional[Agent]) -> None:
        if agent is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist_agent(agent))
        except RuntimeError:
            pass

    def set_sync_service(self, sync_service) -> None:
        """Inject the ConnectorSyncService for outbound sync."""
        self._sync_service = sync_service
        logger.info("ConnectorSyncService attached to IncidentService")

    def _next_incident_id(self) -> str:
        """Generate user-friendly incident IDs like INC-1001."""
        max_existing = self._incident_sequence
        for incident_id in self.incidents.keys():
            match = re.fullmatch(r"INC-(\d+)", str(incident_id).upper())
            if match:
                max_existing = max(max_existing, int(match.group(1)))

        self._incident_sequence = max_existing + 1
        return f"INC-{self._incident_sequence}"

    def _incident_id_from_reference_id(self, reference_id: Optional[str]) -> Optional[str]:
        """Mirror REF-#### as INC-#### when that incident number is free."""
        if not reference_id:
            return None

        match = re.fullmatch(r"REF-(\d+)", str(reference_id).strip().upper())
        if not match:
            return None

        numeric_part = int(match.group(1))
        candidate = f"INC-{numeric_part}"
        if candidate in self.incidents:
            return None

        self._incident_sequence = max(self._incident_sequence, numeric_part)
        return candidate

    async def load_tenant_users(self, db) -> None:
        """Load company/agent user_ids grouped by tenant from MongoDB.

        Called at startup so the sync notification system can route
        notifications to the correct tenant's admins and agents.
        """
        self._company_users_by_tenant.clear()
        self._agent_users_by_tenant.clear()
        async for doc in db.users.find(
            {"role": {"$in": ["company", "agent"]}, "is_active": True},
            {"user_id": 1, "role": 1, "tenant_id": 1, "_id": 0},
        ):
            tid = doc.get("tenant_id")
            uid = doc.get("user_id")
            role = doc.get("role")
            if not tid or not uid:
                continue
            if role == "company":
                self._company_users_by_tenant.setdefault(tid, []).append(uid)
            elif role == "agent":
                self._agent_users_by_tenant.setdefault(tid, []).append(uid)
        logger.info(
            "Loaded tenant user cache: %d tenants with company users, %d with agents",
            len(self._company_users_by_tenant),
            len(self._agent_users_by_tenant),
        )

    def _seed_agents(self):
        """Populate in-memory agent store with sample field engineers.

        IDs match the MongoDB seed users (role='agent') so login, assignment,
        and the FieldAgentDashboard all use the same identity.
        """
        seed = [
            Agent(
                agent_id="agent_001",
                full_name="John Smith",
                phone="+447700900201",
                email="john.smith@utilityresponse.co.uk",
                specialization="Gas Safety Engineer",
                experience_years=12,
                rating=4.8,
                total_jobs_completed=340,
                certifications=["Gas Safe Registered", "CORGI Certified", "IGEM Qualified"],
                is_available=True,
                location="Westminster, London",
                location_area="urban",
                geo_coordinates={"lat": 51.5014, "lng": -0.1419},
                vehicle_type="Ford Transit Response Van",
                vehicle_registration="AB12 CDE",
            ),
            Agent(
                agent_id="agent_002",
                full_name="David Mitchell",
                phone="+447700900202",
                email="david.mitchell@utilityresponse.co.uk",
                specialization="Emergency Response Specialist",
                experience_years=8,
                rating=4.9,
                total_jobs_completed=215,
                certifications=["Gas Safe Registered", "First Aid Certified", "Hazmat Level 2"],
                is_available=True,
                location="Canary Wharf, London",
                location_area="urban",
                geo_coordinates={"lat": 51.5054, "lng": -0.0235},
                vehicle_type="Mercedes Sprinter Emergency Unit",
                vehicle_registration="CD34 FGH",
            ),
            Agent(
                agent_id="agent_003",
                full_name="Robert Taylor",
                phone="+447700900203",
                email="robert.taylor@utilityresponse.co.uk",
                specialization="Senior Gas Inspector",
                experience_years=15,
                rating=4.7,
                total_jobs_completed=480,
                certifications=["Gas Safe Registered", "IGEM/UP/1A", "CO Awareness Certified"],
                is_available=True,
                location="Deansgate, Manchester",
                location_area="urban",
                geo_coordinates={"lat": 53.4784, "lng": -2.2485},
                vehicle_type="Toyota Hilux Field Unit",
                vehicle_registration="EF56 JKL",
            ),
            Agent(
                agent_id="agent_004",
                full_name="Thomas Brown",
                phone="+447700900204",
                email="thomas.brown@utilityresponse.co.uk",
                specialization="Leak Detection Technician",
                experience_years=5,
                rating=4.6,
                total_jobs_completed=120,
                certifications=["Gas Safe Registered", "Advanced Leak Detection"],
                is_available=True,
                location="Headingley, Leeds",
                location_area="suburban",
                geo_coordinates={"lat": 53.8195, "lng": -1.5826},
                vehicle_type="Vauxhall Vivaro Detection Unit",
                vehicle_registration="GH78 MNP",
            ),
            Agent(
                agent_id="agent_005",
                full_name="Daniel Wright",
                phone="+447700900205",
                email="daniel.wright@utilityresponse.co.uk",
                specialization="Pipeline Integrity Engineer",
                experience_years=7,
                rating=4.5,
                total_jobs_completed=185,
                certifications=["Gas Safe Registered", "Pipeline Inspection Certified"],
                is_available=True,
                location="Clifton, Bristol",
                location_area="suburban",
                geo_coordinates={"lat": 51.4560, "lng": -2.6210},
                vehicle_type="Ford Ranger Inspection Unit",
                vehicle_registration="JK90 QRS",
            ),
        ]
        for agent in seed:
            self.agents[agent.agent_id] = agent
        logger.info(f"Seeded {len(self.agents)} field agents")

    def _reference_id_blocks_reuse(self, incident: Incident) -> bool:
        """Only progressed incidents should continue reserving a REF ID."""
        return incident.status not in self._NON_BLOCKING_REFERENCE_STATUSES

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID."""
        return self.agents.get(agent_id)

    def get_all_agents(self) -> List[Agent]:
        """Get all field agents."""
        return list(self.agents.values())

    # ── In-App Notification System ────────────────────────────────────────
    def push_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        notif_type: str = "info",
        incident_id: Optional[str] = None,
        link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Push a notification to a specific user's inbox."""
        notif = {
            "notification_id": f"NOTIF_{uuid.uuid4().hex[:12].upper()}",
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notif_type,  # info, warning, success, critical, assignment
            "incident_id": incident_id,
            "link": link,
            "read": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        if user_id not in self.user_notifications:
            self.user_notifications[user_id] = []
        self.user_notifications[user_id].insert(0, notif)
        # Cap at 100 notifications per user
        self.user_notifications[user_id] = self.user_notifications[user_id][:100]
        self._schedule_persist_notification(notif)
        logger.info(f"Notification pushed to {user_id}: {title}")
        return notif

    def push_notification_to_role(
        self,
        role: str,
        title: str,
        message: str,
        notif_type: str = "info",
        incident_id: Optional[str] = None,
        link: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Push notification to all users with a given role for a specific tenant.

        Uses the tenant user cache populated by ``load_tenant_users()``.
        If *tenant_id* is ``None``, falls back to broadcasting to all tenants.
        """
        if role == "agent":
            if tenant_id and tenant_id in self._agent_users_by_tenant:
                recipients = self._agent_users_by_tenant[tenant_id]
            else:
                recipients = list(self.agents.keys())
            for uid in recipients:
                self.push_notification(uid, title, message, notif_type, incident_id, link)
        elif role in ("company", "admin"):
            if tenant_id and tenant_id in self._company_users_by_tenant:
                recipients = self._company_users_by_tenant[tenant_id]
            else:
                # Fallback: all company users across tenants
                recipients = [uid for uids in self._company_users_by_tenant.values() for uid in uids]
            for uid in recipients:
                self.push_notification(uid, title, message, notif_type, incident_id, link)
        # For user role, push directly by user_id (caller should know the id)

    def get_notifications(self, user_id: str, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Get notifications for a user."""
        notifs = self.user_notifications.get(user_id, [])
        if unread_only:
            return [n for n in notifs if not n.get("read")]
        return notifs

    def mark_notification_read(self, user_id: str, notification_id: str) -> bool:
        """Mark a single notification as read."""
        for notif in self.user_notifications.get(user_id, []):
            if notif["notification_id"] == notification_id:
                notif["read"] = True
                self._schedule_persist_notification(notif)
                return True
        return False

    def mark_all_notifications_read(self, user_id: str) -> int:
        """Mark all notifications as read. Returns count marked."""
        count = 0
        for notif in self.user_notifications.get(user_id, []):
            if not notif.get("read"):
                notif["read"] = True
                self._schedule_persist_notification(notif)
                count += 1
        return count

    def get_unread_count(self, user_id: str) -> int:
        """Get unread notification count."""
        return sum(1 for n in self.user_notifications.get(user_id, []) if not n.get("read"))

    @staticmethod
    def _classify_location_type(location: Optional[str]) -> str:
        """Classify a location string into urban/suburban/rural for SLA."""
        if not location:
            return "suburban"  # default
        import re
        lower = location.lower()
        words = set(re.findall(r'\b\w+\b', lower))
        # Use both substring matching (for multi-word phrases) and word matching
        def _matches(keywords):
            for kw in keywords:
                if ' ' in kw:
                    if kw in lower:
                        return True
                else:
                    if kw in words:
                        return True
            return False
        if _matches(RURAL_KEYWORDS):
            return "rural"
        if _matches(SUBURBAN_KEYWORDS):
            return "suburban"
        if _matches(URBAN_KEYWORDS):
            return "urban"
        return "suburban"

    @staticmethod
    def calculate_sla(
        outcome: IncidentOutcome,
        location: Optional[str] = None,
    ) -> tuple:
        """Calculate SLA hours and estimated resolution datetime.

        Returns:
            (sla_hours, estimated_resolution_at)
        """
        base = SLA_BASE_HOURS.get(outcome, 4.0)
        if base <= 0:
            return (0.0, None)
        loc_type = IncidentService._classify_location_type(location)
        multiplier = SLA_LOCATION_MULTIPLIERS.get(loc_type, 1.0)
        sla_hours = round(base * multiplier, 1)
        estimated_at = datetime.utcnow() + timedelta(hours=sla_hours)
        return (sla_hours, estimated_at)

    def _add_status_history(self, incident: Incident, status: str, message: str = ""):
        """Append an entry to the incident's status timeline."""
        if incident.status_history is None:
            incident.status_history = []
        incident.status_history.append({
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
        })
        self._schedule_persist_incident(incident)

    @staticmethod
    def _validate_coordinates(lat: float, lng: float) -> None:
        if lat < -90 or lat > 90:
            raise ValueError("Latitude must be between -90 and 90")
        if lng < -180 or lng > 180:
            raise ValueError("Longitude must be between -180 and 180")

    @staticmethod
    def _is_open_request(status: Optional[str], terminal_statuses: set) -> bool:
        if not status:
            return True
        return status.upper() not in terminal_statuses

    @staticmethod
    def _required_resolution_fields_missing(checklist: Dict[str, Any]) -> List[str]:
        required = [
            "root_cause",
            "actions_taken",
            "verification_result",
            "safety_checks_completed",
            "handoff_confirmed",
        ]
        missing = []
        for key in required:
            value = checklist.get(key)
            if value is None:
                missing.append(key)
                continue
            if isinstance(value, str) and not value.strip():
                missing.append(key)
                continue
            if isinstance(value, list) and len(value) == 0:
                missing.append(key)
                continue
        # Either a direct evidence note or a verification evidence string must exist.
        evidence = checklist.get("verification_evidence")
        evidence_note = checklist.get("verification_evidence_note")
        if (not isinstance(evidence, str) or not evidence.strip()) and (
            not isinstance(evidence_note, str) or not evidence_note.strip()
        ):
            missing.append("verification_evidence")
        if checklist.get("safety_checks_completed") is not True:
            missing.append("safety_checks_completed:true")
        if checklist.get("handoff_confirmed") is not True:
            missing.append("handoff_confirmed:true")
        return missing

    # ── Per-request SLA & Notifications ──────────────────────────────────

    @staticmethod
    def calculate_request_sla(priority: str, request_type: str = "assistance") -> Dict[str, Any]:
        """Calculate SLA deadline for an individual request."""
        key = (priority or "NORMAL").strip().upper()
        if request_type == "item":
            minutes = ITEM_SLA_MINUTES.get(key, 90)
        else:
            minutes = REQUEST_SLA_MINUTES.get(key, 120)
        deadline = datetime.utcnow() + timedelta(minutes=minutes)
        return {"sla_minutes": minutes, "deadline_at": deadline.isoformat()}

    def _add_customer_notification(
        self,
        incident: Incident,
        notification_type: str,
        title: str,
        message: str,
        severity: str = "info",
        related_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a customer-facing notification to the incident."""
        notif = {
            "notification_id": f"NOTIF_{uuid.uuid4().hex[:10].upper()}",
            "type": notification_type,
            "title": title,
            "message": message,
            "severity": severity,
            "created_at": datetime.utcnow().isoformat(),
            "read": False,
            "related_request_id": related_request_id,
        }
        if incident.customer_notifications is None:
            incident.customer_notifications = []
        incident.customer_notifications.append(notif)
        self._add_status_history(incident, f"notification_{notification_type}", message)
        incident.updated_at = datetime.utcnow()
        return notif

    def assign_backup_agent(
        self,
        incident_id: str,
        request_id: str,
        agent_id: str,
        assigned_by: str,
        role: str = "backup",
    ) -> Optional[Dict[str, Any]]:
        """Assign a backup agent to an incident for a specific assistance request."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        # Find the assistance request
        req = next(
            (r for r in (incident.assistance_requests or []) if r.get("request_id") == request_id),
            None,
        )
        if not req:
            raise ValueError(f"Assistance request {request_id} not found on incident {incident_id}")

        # Validate agent is available
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        if not agent.is_available:
            raise ValueError(f"Agent {agent.full_name} is not available")

        # Prevent assigning primary agent as backup
        if incident.assigned_agent_id == agent_id:
            raise ValueError("Cannot assign the primary agent as a backup agent")

        # Prevent duplicate backup assignment
        existing = [
            ba for ba in (incident.backup_agents or [])
            if ba.get("agent_id") == agent_id and ba.get("request_id") == request_id
        ]
        if existing:
            raise ValueError(f"Agent {agent.full_name} is already assigned as backup for this request")

        # Create backup entry
        backup_entry = {
            "agent_id": agent_id,
            "request_id": request_id,
            "role": role,
            "status": "ASSIGNED",
            "assigned_at": datetime.utcnow().isoformat(),
            "assigned_by": assigned_by,
        }
        if incident.backup_agents is None:
            incident.backup_agents = []
        incident.backup_agents.append(backup_entry)

        # Update the assistance request
        req["status"] = "ACKNOWLEDGED"
        req["assigned_agent_id"] = agent_id
        req["assigned_agent_name"] = agent.full_name
        req["updated_at"] = datetime.utcnow().isoformat()
        req.setdefault("history", []).append({
            "status": "ACKNOWLEDGED",
            "updated_by": assigned_by,
            "note": f"Backup agent {agent.full_name} assigned",
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Mark agent unavailable
        agent.is_available = False

        # Customer notification
        role_label = role.replace("_", " ").title()
        self._add_customer_notification(
            incident,
            "backup_dispatched",
            f"{role_label} Support Dispatched",
            f"A {role_label.lower()} ({agent.full_name}) has been assigned to assist with your incident.",
            severity="info",
            related_request_id=request_id,
        )

        self._add_status_history(
            incident, "backup_agent_assigned",
            f"{role_label} {agent.full_name} assigned for request {request_id}.",
        )
        incident.updated_at = datetime.utcnow()

        logger.info(f"Assigned backup agent {agent_id} ({agent.full_name}) to incident {incident_id} for request {request_id}")

        # Notify backup agent about their assignment
        self.push_notification(
            agent_id,
            f"{role_label} Assignment",
            f"You've been assigned as {role_label.lower()} for incident {incident_id}. Primary agent: {incident.assigned_agent_id or 'N/A'}.",
            notif_type="assignment",
            incident_id=incident_id,
            link=f"/agent/incidents/{incident_id}",
        )
        # Notify primary agent that backup is on the way
        if incident.assigned_agent_id:
            self.push_notification(
                incident.assigned_agent_id,
                f"{role_label} Assigned",
                f"{agent.full_name} ({role_label.lower()}) is on the way to assist you at incident {incident_id}.",
                notif_type="success",
                incident_id=incident_id,
                link=f"/agent/incidents/{incident_id}",
            )

        return backup_entry

    def check_and_create_sla_notifications(self, incident_id: str) -> List[Dict[str, Any]]:
        """Check all open requests for SLA breaches and create customer notifications."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return []

        now = datetime.utcnow()
        created_notifications: List[Dict[str, Any]] = []
        existing_notif_keys = set()
        for n in (incident.customer_notifications or []):
            key = f"{n.get('type')}:{n.get('related_request_id')}"
            existing_notif_keys.add(key)

        # Check assistance requests
        for req in (incident.assistance_requests or []):
            status = (req.get("status") or "").upper()
            if status in TERMINAL_ASSISTANCE_STATUSES:
                continue
            deadline_str = req.get("sla_deadline_at")
            if not deadline_str:
                continue
            try:
                deadline = datetime.fromisoformat(deadline_str)
            except (ValueError, TypeError):
                continue

            remaining = (deadline - now).total_seconds() / 60
            sla_minutes = req.get("sla_minutes", 60)
            req_id = req.get("request_id")

            if remaining <= 0 and f"sla_breach:{req_id}" not in existing_notif_keys:
                notif = self._add_customer_notification(
                    incident, "sla_breach", "Service Delay Notice",
                    "We apologize for the delay in processing your request. "
                    "Your case has been escalated for immediate attention. "
                    "Our team is actively working to resolve this as quickly as possible.",
                    severity="critical",
                    related_request_id=req_id,
                )
                created_notifications.append(notif)
            elif 0 < remaining <= sla_minutes * 0.2 and f"sla_warning:{req_id}" not in existing_notif_keys:
                notif = self._add_customer_notification(
                    incident, "sla_warning", "Update on Your Request",
                    "Your request is taking longer than expected. "
                    "Our team is working to address it and we appreciate your patience.",
                    severity="warning",
                    related_request_id=req_id,
                )
                created_notifications.append(notif)

        # Check item requests
        for req in (incident.item_requests or []):
            status = (req.get("status") or "").upper()
            if status in TERMINAL_ITEM_STATUSES:
                continue
            deadline_str = req.get("sla_deadline_at")
            if not deadline_str:
                continue
            try:
                deadline = datetime.fromisoformat(deadline_str)
            except (ValueError, TypeError):
                continue

            remaining = (deadline - now).total_seconds() / 60
            sla_minutes = req.get("sla_minutes", 90)
            req_id = req.get("request_id")

            if remaining <= 0 and f"sla_breach:{req_id}" not in existing_notif_keys:
                notif = self._add_customer_notification(
                    incident, "sla_breach", "Equipment Delivery Delay",
                    "The equipment delivery for your case is delayed. "
                    "We are expediting this and will update you shortly.",
                    severity="warning",
                    related_request_id=req_id,
                )
                created_notifications.append(notif)

        return created_notifications

    def create_incident(
        self,
        tenant_id: str,
        user_id: str,
        description: str,
        incident_type: Optional[str] = None,
        user_name: Optional[str] = None,
        user_phone: Optional[str] = None,
        user_address: Optional[str] = None,
        location: Optional[str] = None,
        geo_location: Optional[Dict[str, float]] = None,
        user_geo_location: Optional[Dict[str, float]] = None,
        structured_data: Optional[Dict[str, Any]] = None,
        reference_id: Optional[str] = None,
        reported_by_staff_id: Optional[str] = None,
    ) -> Incident:
        """
        Create a new incident
        
        Args:
            tenant_id: Tenant/company ID
            user_id: User ID
            description: Incident description
            incident_type: Type of incident
            user_name: User's full name
            user_phone: User's phone number
            user_address: User's address
            location: Location description
            geo_location: {"lat": float, "lng": float}
            structured_data: Extracted structured variables
        
        Returns:
            Created Incident object
        """
        incident_id = self._incident_id_from_reference_id(reference_id) or self._next_incident_id()
        
        incident = Incident(
            incident_id=incident_id,
            tenant_id=tenant_id,
            user_id=user_id,
            user_name=user_name,
            user_phone=user_phone,
            user_address=user_address,
            reference_id=reference_id,
            description=description,
            incident_type=incident_type,
            location=location,
            geo_location=geo_location,
            user_geo_location=user_geo_location,
            reported_by_staff_id=reported_by_staff_id,
            status=IncidentStatus.NEW,
            structured_data=structured_data or {},
            status_history=[{
                "status": "reported",
                "timestamp": datetime.utcnow().isoformat(),
                "message": (
                    f"Incident reported by staff {reported_by_staff_id} on behalf of user"
                    if reported_by_staff_id
                    else "Incident reported by user"
                ),
            }],
            field_activity=[],
            assistance_requests=[],
            item_requests=[],
            customer_notifications=[],
            backup_agents=[],
            agent_location_history=[],
            media=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.incidents[incident_id] = incident
        self._schedule_persist_incident(incident)
        logger.info(f"✅ INCIDENT CREATED: {incident_id} for user={user_id}, tenant={tenant_id}, type={incident_type}")
        logger.info(f"   Total incidents in memory: {len(self.incidents)}")

        # Notify company about new incident
        self.push_notification_to_role(
            "company",
            "New Incident Reported",
            f"Incident {incident_id} reported by {user_name or user_id}: {description[:80]}",
            notif_type="info",
            incident_id=incident_id,
            link="/company",
            tenant_id=tenant_id,
        )

        return incident
    
    def update_incident(
        self,
        incident_id: str,
        **updates
    ) -> Optional[Incident]:
        """
        Update incident fields
        
        Args:
            incident_id: Incident ID
            **updates: Fields to update
        
        Returns:
            Updated Incident or None if not found
        """
        incident = self.incidents.get(incident_id)
        if not incident:
            logger.warning(f"Incident not found: {incident_id}")
            return None
        
        # Update fields
        for key, value in updates.items():
            if hasattr(incident, key):
                setattr(incident, key, value)
        
        incident.updated_at = datetime.utcnow()
        self._schedule_persist_incident(incident)
        
        logger.info(f"Updated incident {incident_id}: {list(updates.keys())}")
        return incident
    
    def finalize_incident(
        self,
        incident_id: str,
        outcome: IncidentOutcome,
        risk_score: float,
        confidence_score: float,
        kb_similarity_score: Optional[float] = None,
        kb_match_type: Optional[str] = None,
        kb_validation_details: Optional[Dict[str, Any]] = None,
        incident_pattern: Optional[Dict[str, Any]] = None,
        workflow_execution_id: Optional[str] = None
    ) -> Optional[Incident]:
        """
        Finalize incident with risk assessment and decision

        Args:
            incident_id: Incident ID
            outcome: Final outcome decision
            risk_score: Calculated risk score
            confidence_score: Confidence in the decision
            kb_similarity_score: KB similarity score
            kb_match_type: "true" | "false" | "unknown"
            kb_validation_details: Full KB verification result dict
            incident_pattern: Normalized incident pattern for future KB learning/matching
            workflow_execution_id: Workflow execution ID

        Returns:
            Updated Incident or None
        """
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        # Determine status based on outcome
        if outcome == IncidentOutcome.FALSE_REPORT:
            status = IncidentStatus.FALSE_REPORT
        elif outcome == IncidentOutcome.CLOSE_WITH_GUIDANCE:
            # Low-risk incidents with guidance are still logged as completed
            status = IncidentStatus.COMPLETED
        elif outcome == IncidentOutcome.EMERGENCY_DISPATCH:
            status = IncidentStatus.PENDING_COMPANY_ACTION
        elif outcome == IncidentOutcome.SCHEDULE_ENGINEER:
            status = IncidentStatus.PENDING_COMPANY_ACTION
        elif outcome == IncidentOutcome.MONITOR:
            status = IncidentStatus.IN_PROGRESS
        else:
            status = IncidentStatus.COMPLETED

        incident.outcome = outcome
        incident.risk_score = risk_score
        incident.confidence_score = confidence_score
        incident.kb_similarity_score = kb_similarity_score
        incident.kb_match_type = kb_match_type
        incident.kb_validation_details = kb_validation_details
        incident.incident_pattern = incident_pattern
        incident.workflow_execution_id = workflow_execution_id
        incident.status = status
        incident.completed_at = datetime.utcnow()
        incident.updated_at = datetime.utcnow()

        # Calculate SLA based on outcome and location
        sla_hours, estimated_at = self.calculate_sla(outcome, incident.location)
        if sla_hours > 0:
            incident.sla_hours = sla_hours
            incident.estimated_resolution_at = estimated_at

        # Add status history entries
        self._add_status_history(incident, "validated", "Incident validated and assessed")
        outcome_messages = {
            IncidentOutcome.EMERGENCY_DISPATCH: "Emergency response activated. Engineers dispatched immediately.",
            IncidentOutcome.SCHEDULE_ENGINEER: f"Engineer visit scheduled. Estimated arrival within {sla_hours} hours.",
            IncidentOutcome.MONITOR: "Incident is being monitored. Our team will review and follow up.",
            IncidentOutcome.CLOSE_WITH_GUIDANCE: "Incident assessed as low risk. Safety guidance provided.",
            IncidentOutcome.FALSE_REPORT: "Report assessed. No further action required.",
        }
        self._add_status_history(incident, status.value, outcome_messages.get(outcome, "Incident processed."))

        logger.info(f"Finalized incident {incident_id}: {outcome}, risk={risk_score:.2f}, sla={sla_hours}h")

        # Trigger outbound sync to external system (ServiceNow)
        if self._sync_service:
            try:
                import asyncio
                asyncio.ensure_future(self._sync_service.on_incident_finalized(incident))
            except Exception as e:
                logger.error(f"Outbound sync failed for {incident_id}: {e}")

        self._schedule_persist_incident(incident)

        return incident
    
    def assign_agent(
        self,
        incident_id: str,
        agent_id: str
    ) -> Optional[Incident]:
        """
        Assign field agent to incident

        Args:
            incident_id: Incident ID
            agent_id: Agent ID

        Returns:
            Updated Incident or None
        """
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        incident.assigned_agent_id = agent_id
        incident.assigned_at = datetime.utcnow()
        incident.agent_status = "ASSIGNED"
        incident.status = IncidentStatus.DISPATCHED
        incident.updated_at = datetime.utcnow()

        # Calculate estimated arrival based on location type
        loc_type = self._classify_location_type(incident.location)
        minutes = self.TRAVEL_MINUTES.get(loc_type, 35)
        incident.estimated_arrival_at = datetime.utcnow() + timedelta(minutes=minutes)

        # Get agent name for richer status message and mark unavailable
        agent = self.agents.get(agent_id)
        agent_name = agent.full_name if agent else agent_id
        if agent:
            agent.is_available = False
            self._schedule_persist_agent(agent)
        self._add_status_history(
            incident, "dispatched",
            f"{agent_name} assigned and on their way. Estimated arrival in {minutes} minutes."
        )

        logger.info(f"Assigned agent {agent_id} ({agent_name}) to incident {incident_id}, ETA {minutes}min")

        # Trigger outbound sync (assignee changed)
        if self._sync_service:
            try:
                import asyncio
                asyncio.ensure_future(
                    self._sync_service.on_incident_updated(incident, ["assignee_id", "status"])
                )
            except Exception as e:
                logger.error(f"Outbound sync failed for {incident_id}: {e}")

        # Notify agent about new assignment
        self.push_notification(
            agent_id,
            "New Incident Assigned",
            f"You have been assigned to incident {incident_id}. ETA: ~{minutes} min.",
            notif_type="assignment",
            incident_id=incident_id,
            link=f"/agent/incidents/{incident_id}",
        )
        # Notify user that engineer is dispatched
        self.push_notification(
            incident.user_id,
            "Engineer Dispatched",
            f"{agent_name} has been assigned and is on the way. Estimated arrival: ~{minutes} min.",
            notif_type="success",
            incident_id=incident_id,
            link=f"/my-reports/{incident_id}",
        )

        return incident

    def update_agent_location(
        self,
        incident_id: str,
        lat: float,
        lng: float,
        source: str = "gps",
        accuracy: Optional[float] = None,
        updated_by: Optional[str] = None,
    ) -> Optional[Incident]:
        """Update the latest agent location and append a history point."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        self._validate_coordinates(lat, lng)

        point = {
            "lat": lat,
            "lng": lng,
            "source": source,
            "accuracy": accuracy,
            "timestamp": datetime.utcnow().isoformat(),
            "updated_by": updated_by or incident.assigned_agent_id,
        }
        incident.agent_live_location = point
        if incident.agent_location_history is None:
            incident.agent_location_history = []
        incident.agent_location_history.append(point)
        incident.updated_at = datetime.utcnow()
        self._schedule_persist_incident(incident)
        return incident

    def add_field_milestone(
        self,
        incident_id: str,
        milestone: str,
        created_by: str,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Incident]:
        """Append a field-operation milestone and keep status timelines in sync."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        normalized = (milestone or "").strip().lower()
        spec = FIELD_MILESTONE_CATALOG.get(normalized)
        if not spec:
            raise ValueError(f"Unsupported milestone: {milestone}")

        event = {
            "activity_id": f"ACT_{uuid.uuid4().hex[:10].upper()}",
            "milestone": normalized,
            "label": spec["label"],
            "message": spec["message"],
            "notes": notes or "",
            "created_by": created_by,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        if incident.field_activity is None:
            incident.field_activity = []
        incident.field_activity.append(event)

        mapped_agent_status = spec.get("agent_status")
        if mapped_agent_status:
            incident.agent_status = mapped_agent_status
            if mapped_agent_status == "IN_PROGRESS":
                incident.status = IncidentStatus.DISPATCHED
            if mapped_agent_status == "COMPLETED":
                incident.status = IncidentStatus.DISPATCHED
            self._add_status_history(incident, mapped_agent_status.lower(), notes or spec["message"])

        self._add_status_history(incident, f"field_{normalized}", notes or spec["message"])
        incident.updated_at = datetime.utcnow()
        return incident

    def create_assistance_request(
        self,
        incident_id: str,
        created_by: str,
        request_type: str,
        priority: str,
        reason: str,
        details: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        norm_priority = (priority or "medium").strip().upper()
        sla_info = self.calculate_request_sla(norm_priority, "assistance")
        request = {
            "request_id": f"ASR_{uuid.uuid4().hex[:10].upper()}",
            "type": (request_type or "").strip().lower() or "general",
            "priority": norm_priority,
            "reason": reason.strip(),
            "details": details or "",
            "status": "PENDING",
            "created_by": created_by,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "sla_minutes": sla_info["sla_minutes"],
            "sla_deadline_at": sla_info["deadline_at"],
            "history": [{
                "status": "PENDING",
                "updated_by": created_by,
                "note": "Request created",
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
        if incident.assistance_requests is None:
            incident.assistance_requests = []
        incident.assistance_requests.append(request)
        self._add_status_history(
            incident,
            "assistance_requested",
            f"Assistance requested ({request['type']}, {request['priority']}).",
        )
        incident.updated_at = datetime.utcnow()

        # Notify company about assistance request
        self.push_notification_to_role(
            "company",
            "Assistance Requested",
            f"Agent requested {request['type']} ({request['priority']}) for incident {incident_id}: {reason[:60]}",
            notif_type="warning",
            incident_id=incident_id,
            link="/company",
            tenant_id=incident.tenant_id,
        )

        return request

    def update_assistance_request(
        self,
        incident_id: str,
        request_id: str,
        status: str,
        updated_by: str,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        incident = self.incidents.get(incident_id)
        if not incident:
            return None
        requests = incident.assistance_requests or []
        req = next((r for r in requests if r.get("request_id") == request_id), None)
        if not req:
            return None

        next_status = (status or "").strip().upper()
        current = (req.get("status") or "").upper()
        transitions = {
            "PENDING": {"ACKNOWLEDGED", "IN_PROGRESS", "REJECTED", "CANCELLED"},
            "ACKNOWLEDGED": {"IN_PROGRESS", "FULFILLED", "REJECTED", "CANCELLED"},
            "IN_PROGRESS": {"FULFILLED", "REJECTED", "CANCELLED"},
        }
        if current in TERMINAL_ASSISTANCE_STATUSES:
            raise ValueError("Cannot update a closed assistance request")
        if next_status == current:
            return req
        if current in transitions and next_status not in transitions[current]:
            raise ValueError(f"Invalid assistance request transition: {current} -> {next_status}")

        req["status"] = next_status
        req["updated_at"] = datetime.utcnow().isoformat()
        req.setdefault("history", []).append({
            "status": next_status,
            "updated_by": updated_by,
            "note": note or "",
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._add_status_history(
            incident,
            "assistance_request_updated",
            f"Assistance request {req['request_id']} marked {next_status}.",
        )
        incident.updated_at = datetime.utcnow()
        return req

    def create_item_request(
        self,
        incident_id: str,
        created_by: str,
        item_name: str,
        quantity: int,
        urgency: str = "normal",
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        qty = max(1, int(quantity or 1))
        norm_urgency = (urgency or "normal").strip().upper()
        sla_info = self.calculate_request_sla(norm_urgency, "item")
        request = {
            "request_id": f"ITR_{uuid.uuid4().hex[:10].upper()}",
            "item_name": item_name.strip(),
            "quantity": qty,
            "urgency": norm_urgency,
            "notes": notes or "",
            "status": "REQUESTED",
            "created_by": created_by,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "sla_minutes": sla_info["sla_minutes"],
            "sla_deadline_at": sla_info["deadline_at"],
            "history": [{
                "status": "REQUESTED",
                "updated_by": created_by,
                "note": "Request created",
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
        if incident.item_requests is None:
            incident.item_requests = []
        incident.item_requests.append(request)
        self._add_status_history(
            incident,
            "item_requested",
            f"Item request created for {request['item_name']} x{request['quantity']}.",
        )
        incident.updated_at = datetime.utcnow()

        # Notify company about item request
        self.push_notification_to_role(
            "company",
            "Item Requested",
            f"Agent requested {item_name} x{qty} ({norm_urgency}) for incident {incident_id}.",
            notif_type="warning",
            incident_id=incident_id,
            link="/company",
            tenant_id=incident.tenant_id,
        )

        return request

    def update_item_request(
        self,
        incident_id: str,
        request_id: str,
        status: str,
        updated_by: str,
        note: Optional[str] = None,
        eta_minutes: Optional[int] = None,
        warehouse_notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        incident = self.incidents.get(incident_id)
        if not incident:
            return None
        requests = incident.item_requests or []
        req = next((r for r in requests if r.get("request_id") == request_id), None)
        if not req:
            return None

        next_status = (status or "").strip().upper()
        current = (req.get("status") or "").upper()
        transitions = {
            "REQUESTED": {"APPROVED", "REJECTED", "CANCELLED"},
            "APPROVED": {"DISPATCHED", "REJECTED", "CANCELLED"},
            "DISPATCHED": {"DELIVERED", "REJECTED", "CANCELLED"},
            "DELIVERED": {"USED", "CANCELLED"},
        }
        if current in TERMINAL_ITEM_STATUSES:
            raise ValueError("Cannot update a closed item request")
        if next_status == current:
            return req
        if current in transitions and next_status not in transitions[current]:
            raise ValueError(f"Invalid item request transition: {current} -> {next_status}")

        req["status"] = next_status
        req["updated_at"] = datetime.utcnow().isoformat()

        # Add ETA and warehouse notes when dispatching
        if next_status == "DISPATCHED" and eta_minutes:
            req["eta_minutes"] = eta_minutes
            req["estimated_delivery_at"] = (datetime.utcnow() + timedelta(minutes=eta_minutes)).isoformat()
        if next_status == "DISPATCHED" and warehouse_notes:
            req["warehouse_notes"] = warehouse_notes

        req.setdefault("history", []).append({
            "status": next_status,
            "updated_by": updated_by,
            "note": note or "",
            "timestamp": datetime.utcnow().isoformat(),
        })

        if next_status == "USED":
            if incident.items_used is None:
                incident.items_used = []
            label = f"{req.get('item_name', 'Item')} x{req.get('quantity', 1)}"
            if label not in incident.items_used:
                incident.items_used.append(label)

        self._add_status_history(
            incident,
            "item_request_updated",
            f"Item request {req['request_id']} marked {next_status}.",
        )
        incident.updated_at = datetime.utcnow()

        # Notify agent about item status change
        item_name = req.get("item_name", "Item")
        agent_id = incident.assigned_agent_id
        item_messages = {
            "APPROVED": f"Your request for {item_name} has been approved.",
            "DISPATCHED": f"{item_name} has been dispatched." + (f" ETA: ~{eta_minutes} min." if eta_minutes else ""),
            "DELIVERED": f"{item_name} has been delivered to the site.",
            "REJECTED": f"Your request for {item_name} was rejected." + (f" Reason: {note}" if note else ""),
        }
        if agent_id and next_status in item_messages:
            self.push_notification(
                agent_id,
                f"Item {next_status.capitalize()}",
                item_messages[next_status],
                notif_type="success" if next_status in ("APPROVED", "DELIVERED") else "info",
                incident_id=incident_id,
                link=f"/agent/incidents/{incident_id}",
            )

        return req

    def mark_resolved(
        self,
        incident_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None,
        items_used: Optional[List[str]] = None,
        resolution_checklist: Optional[Dict[str, Any]] = None,
        kb_service: Optional[Any] = None,
        add_to_kb: bool = True,
        resolution_media: Optional[list] = None,
    ) -> Optional[Incident]:
        """
        Mark incident as resolved by field agent (pending company review).
        Status goes to RESOLVED; company must approve to move to COMPLETED.
        """
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        checklist = resolution_checklist or {}
        missing = self._required_resolution_fields_missing(checklist)
        if missing:
            raise ValueError(
                "Resolution checklist incomplete. Missing: " + ", ".join(sorted(set(missing)))
            )

        # Validate that text fields contain valid English (reject gibberish)
        text_errors = validate_resolution_text_fields(
            resolution_notes=resolution_notes or "",
            root_cause=checklist.get("root_cause", ""),
            actions_taken=checklist.get("actions_taken", []),
        )
        if text_errors:
            error_details = "; ".join(f"{k}: {v}" for k, v in text_errors.items())
            raise ValueError(f"Text validation failed. {error_details}")

        incident.status = IncidentStatus.RESOLVED
        incident.agent_status = "COMPLETED"
        incident.resolved_by = resolved_by
        incident.resolved_at = datetime.utcnow()
        incident.resolution_notes = resolution_notes
        incident.items_used = items_used or []
        incident.resolution_checklist = checklist
        incident.updated_at = datetime.utcnow()
        if resolution_media:
            incident.resolution_media = resolution_media
        if incident.field_activity is None:
            incident.field_activity = []
        incident.field_activity.append({
            "activity_id": f"ACT_{uuid.uuid4().hex[:10].upper()}",
            "milestone": "incident_resolved",
            "label": "Incident Resolved",
            "message": resolution_notes or "Incident resolved by field engineer.",
            "notes": resolution_notes or "",
            "created_by": resolved_by,
            "metadata": {"checklist": checklist},
            "timestamp": datetime.utcnow().isoformat(),
        })

        self._add_status_history(incident, "resolved", resolution_notes or "Resolution submitted for company review.")

        # Mark agent as available again
        if incident.assigned_agent_id:
            agent = self.agents.get(incident.assigned_agent_id)
            if agent:
                agent.is_available = True
                self._schedule_persist_agent(agent)

        logger.info(f"Marked incident {incident_id} as resolved by {resolved_by}")

        # Trigger outbound sync (resolution)
        if self._sync_service:
            try:
                import asyncio
                asyncio.ensure_future(
                    self._sync_service.on_incident_updated(incident, ["status", "resolved_at", "resolution_notes"])
                )
            except Exception as e:
                logger.error(f"Outbound sync failed for {incident_id}: {e}")

        # Notify user that incident is under review
        self.push_notification(
            incident.user_id,
            "Incident Under Review",
            f"Your incident {incident_id} has been submitted for company review.",
            notif_type="info",
            incident_id=incident_id,
            link=f"/my-reports/{incident_id}",
        )
        # Notify company to review
        self.push_notification_to_role(
            "company",
            "Resolution Awaiting Review",
            f"Incident {incident_id} resolved by {resolved_by}. Please review and approve.",
            notif_type="warning",
            incident_id=incident_id,
            link="/company",
            tenant_id=incident.tenant_id,
        )

        # Add to Knowledge Base if enabled and kb_service provided
        if add_to_kb and kb_service and incident.risk_score is not None:
            try:
                kb_id = kb_service.add_from_incident(
                    incident=incident,
                    outcome=incident.outcome.value if incident.outcome else "unknown",
                    verified_by=resolved_by,
                    risk_score=incident.risk_score
                )
                if kb_id:
                    logger.info(f"Added incident {incident_id} to KB as {kb_id}")
            except Exception as e:
                logger.error(f"Failed to add incident to KB: {e}")

        return incident

    def company_approve_resolution(
        self,
        incident_id: str,
        approved_by: str,
        approval_notes: Optional[str] = None,
    ) -> Optional[Incident]:
        """Company approves the agent's resolution, marking incident as COMPLETED."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        if incident.status != IncidentStatus.RESOLVED:
            raise ValueError(
                f"Incident must be in RESOLVED status to approve. Current: {incident.status.value}"
            )

        incident.status = IncidentStatus.COMPLETED
        incident.completed_at = datetime.utcnow()
        incident.updated_at = datetime.utcnow()

        if incident.resolution_checklist is None:
            incident.resolution_checklist = {}
        incident.resolution_checklist["company_approval"] = {
            "approved_by": approved_by,
            "approved_at": datetime.utcnow().isoformat(),
            "approval_notes": approval_notes,
        }

        self._add_status_history(
            incident, "completed",
            f"Resolution approved by company ({approved_by}). {approval_notes or ''}"
        )

        # Notify user that incident is fully completed
        self.push_notification(
            incident.user_id,
            "Incident Completed",
            f"Your incident {incident_id} has been verified and completed.",
            notif_type="success",
            incident_id=incident_id,
            link=f"/my-reports/{incident_id}",
        )

        # Notify agent
        if incident.assigned_agent_id:
            self.push_notification(
                incident.assigned_agent_id,
                "Resolution Approved",
                f"Incident {incident_id} resolution approved by company.",
                notif_type="success",
                incident_id=incident_id,
                link=f"/agent/incidents/{incident_id}",
            )

        logger.info(f"Company approved resolution for {incident_id} by {approved_by}")
        return incident

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Get incident by ID"""
        return self.incidents.get(incident_id)

    def delete_incident(self, incident_id: str) -> bool:
        """Delete an incident from the in-memory store."""
        if incident_id not in self.incidents:
            return False

        del self.incidents[incident_id]
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._delete_incident_from_db(incident_id))
        except RuntimeError:
            pass
        logger.info(f"Deleted incident {incident_id}")
        return True

    def get_incident_by_reference_id(
        self,
        reference_id: str,
        tenant_id: Optional[str] = None,
        exclude_incident_id: Optional[str] = None,
    ) -> Optional[Incident]:
        """Return the first incident matching a reference ID."""
        if not reference_id:
            return None

        normalized_reference = str(reference_id).strip().upper()
        for incident in self.incidents.values():
            if exclude_incident_id and incident.incident_id == exclude_incident_id:
                continue
            if tenant_id is not None and incident.tenant_id != tenant_id:
                continue
            if not self._reference_id_blocks_reuse(incident):
                continue
            if (incident.reference_id or "").strip().upper() == normalized_reference:
                return incident

        return None
    
    def get_user_incidents(
        self,
        user_id: str,
        tenant_id: Optional[str] = None
    ) -> List[Incident]:
        """
        Get all incidents for a user
        
        Args:
            user_id: User ID
            tenant_id: Optional tenant filter
        
        Returns:
            List of incidents
        """
        # Statuses that mean the workflow is still incomplete / paused — hide from reports
        # Statuses to SHOW in My Reports (user-facing completed/submitted reports)
        _VISIBLE_STATUSES = {
            IncidentStatus.SUBMITTED,
            IncidentStatus.PENDING_COMPANY_ACTION,
            IncidentStatus.IN_PROGRESS,  # Incidents being monitored after workflow completion
            IncidentStatus.DISPATCHED,
            IncidentStatus.RESOLVED,
            IncidentStatus.COMPLETED,
            IncidentStatus.EMERGENCY,
            IncidentStatus.FALSE_REPORT,
            IncidentStatus.CLOSED,
        }

        logger.info(f"🔍 GET_USER_INCIDENTS called: user_id={user_id}, tenant_id={tenant_id}")
        logger.info(f"   Total incidents in memory: {len(self.incidents)}")

        incidents = []
        for incident in self.incidents.values():
            # Match by user_id OR by reported_by_staff_id (admin on-behalf flow)
            is_owner = incident.user_id == user_id
            is_reporter = getattr(incident, "reported_by_staff_id", None) == user_id
            if not is_owner and not is_reporter:
                continue
            if tenant_id is not None and incident.tenant_id != tenant_id:
                continue
            
            # Only show incidents in visible statuses (submitted reports, not in-progress workflows)
            if incident.status not in _VISIBLE_STATUSES:
                logger.info(
                    f"   ⏸ Skipping non-visible status: {incident.incident_id} (status={incident.status.value})"
                )
                continue
            
            incidents.append(incident)
            logger.info(f"   ✅ Match found: {incident.incident_id}")

        # Sort by created_at descending
        incidents.sort(key=lambda x: x.created_at, reverse=True)
        logger.info(f"   Returning {len(incidents)} completed incidents")
        return incidents
    
    @staticmethod
    def _matches_connector_scope(incident: "Incident", scope: List[str]) -> bool:
        """Check if an incident matches the user's connector scope.

        - external_ref is None (portal/chatbot incident) → ALWAYS matches (portal incidents always visible)
        - external_ref.connector_type present → matches if that type is in scope
        """
        ext_ref = incident.external_ref
        # Portal/chatbot incidents (no external_ref) are ALWAYS visible
        if ext_ref is None or not ext_ref.get("connector_type"):
            return True
        # Connector incidents only visible if in scope
        return ext_ref.get("connector_type") in scope

    def get_company_incidents(
        self,
        tenant_id: str,
        status_filter: Optional[List[IncidentStatus]] = None,
        connector_scope: Optional[List[str]] = None,
    ) -> List[Incident]:
        """
        Get all incidents for a company/tenant, optionally filtered by connector scope.

        Args:
            tenant_id: Tenant ID
            status_filter: Optional list of statuses to filter
            connector_scope: Optional list of connector types (+ "portal") to restrict visibility.
                             Empty list or None means no restriction.

        Returns:
            List of incidents
        """
        incidents = []
        for incident in self.incidents.values():
            if incident.tenant_id != tenant_id:
                continue
            # Apply status filter if provided
            if status_filter is not None and incident.status not in status_filter:
                continue
            # Apply connector scope filter (non-empty = restricted)
            if connector_scope and not self._matches_connector_scope(incident, connector_scope):
                continue
            incidents.append(incident)

        # Sort by risk score descending, then created_at descending
        incidents.sort(
            key=lambda x: (-(x.risk_score or 0), x.created_at),
            reverse=True,
        )
        return incidents

    def _compute_sla_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Compute SLA status fields for a request dict."""
        deadline_str = req.get("sla_deadline_at")
        sla_minutes = req.get("sla_minutes", 60)
        if not deadline_str:
            return {"sla_status": "unknown", "remaining_minutes": None, "sla_percentage": 0}
        try:
            deadline = datetime.fromisoformat(deadline_str)
        except (ValueError, TypeError):
            return {"sla_status": "unknown", "remaining_minutes": None, "sla_percentage": 0}
        now = datetime.utcnow()
        remaining = (deadline - now).total_seconds() / 60
        pct = min(100, max(0, ((sla_minutes - remaining) / sla_minutes) * 100)) if sla_minutes > 0 else 0
        if remaining <= 0:
            sla_status = "breached"
        elif remaining <= sla_minutes * 0.2:
            sla_status = "warning"
        else:
            sla_status = "ok"
        return {"sla_status": sla_status, "remaining_minutes": round(remaining, 1), "sla_percentage": round(pct, 1)}

    def get_company_ops_requests(
        self,
        tenant_id: str,
        kind: str = "all",
        status_filter: Optional[List[str]] = None,
        include_closed: bool = False,
        connector_scope: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return flattened assistance/item request queues for company operations."""
        assistance: List[Dict[str, Any]] = []
        item_requests: List[Dict[str, Any]] = []
        status_filter_set = {s.upper() for s in (status_filter or [])}
        kind_norm = (kind or "all").lower()

        # Track incidents to check SLA notifications
        checked_incidents = set()

        for incident in self.incidents.values():
            if incident.tenant_id != tenant_id:
                continue
            if connector_scope and not self._matches_connector_scope(incident, connector_scope):
                continue

            # Auto-check SLA notifications for incidents with open requests
            if incident.incident_id not in checked_incidents:
                self.check_and_create_sla_notifications(incident.incident_id)
                checked_incidents.add(incident.incident_id)

            # Get primary agent name
            primary_agent = self.agents.get(incident.assigned_agent_id) if incident.assigned_agent_id else None
            primary_agent_name = primary_agent.full_name if primary_agent else None

            if kind_norm in ("all", "assistance"):
                for req in (incident.assistance_requests or []):
                    status = (req.get("status") or "PENDING").upper()
                    if not include_closed and status in TERMINAL_ASSISTANCE_STATUSES:
                        continue
                    if status_filter_set and status not in status_filter_set:
                        continue
                    sla = self._compute_sla_status(req)
                    assistance.append({
                        "kind": "assistance",
                        "incident_id": incident.incident_id,
                        "incident_status": incident.status.value if incident.status else None,
                        "agent_id": incident.assigned_agent_id,
                        "primary_agent_name": primary_agent_name,
                        "user_name": incident.user_name,
                        "user_phone": incident.user_phone,
                        "risk_score": incident.risk_score,
                        "incident_description": (incident.description or "")[:120],
                        "incident_location": incident.user_address or incident.location,
                        "incident_type": incident.incident_type or incident.classified_use_case,
                        **sla,
                        **req,
                    })
            if kind_norm in ("all", "item"):
                for req in (incident.item_requests or []):
                    status = (req.get("status") or "REQUESTED").upper()
                    if not include_closed and status in TERMINAL_ITEM_STATUSES:
                        continue
                    if status_filter_set and status not in status_filter_set:
                        continue
                    sla = self._compute_sla_status(req)
                    item_requests.append({
                        "kind": "item",
                        "incident_id": incident.incident_id,
                        "incident_status": incident.status.value if incident.status else None,
                        "agent_id": incident.assigned_agent_id,
                        "primary_agent_name": primary_agent_name,
                        "user_name": incident.user_name,
                        "user_phone": incident.user_phone,
                        "risk_score": incident.risk_score,
                        "incident_description": (incident.description or "")[:120],
                        "incident_location": incident.user_address or incident.location,
                        "incident_type": incident.incident_type or incident.classified_use_case,
                        **sla,
                        **req,
                    })

        # Sort: breached first, then warning, then by updated_at
        sla_order = {"breached": 0, "warning": 1, "ok": 2, "unknown": 3}
        assistance.sort(key=lambda x: (sla_order.get(x.get("sla_status"), 3), -(x.get("updated_at") or x.get("created_at") or "").__hash__()))
        item_requests.sort(key=lambda x: (sla_order.get(x.get("sla_status"), 3), -(x.get("updated_at") or x.get("created_at") or "").__hash__()))
        return {
            "tenant_id": tenant_id,
            "assistance_requests": assistance,
            "item_requests": item_requests,
            "total_assistance": len(assistance),
            "total_items": len(item_requests),
        }
    
    def get_paused_incidents(
        self, user_id: str, tenant_id: Optional[str] = None
    ) -> List[Incident]:
        """Get paused / resumable incidents for a user."""
        result = []
        for incident in self.incidents.values():
            if incident.user_id != user_id:
                continue
            if tenant_id and incident.tenant_id != tenant_id:
                continue
            if incident.status == IncidentStatus.PAUSED and incident.workflow_snapshot:
                result.append(incident)
        result.sort(key=lambda x: x.updated_at, reverse=True)
        return result

    def get_pending_incidents(self, tenant_id: str) -> List[Incident]:
        """Get incidents pending company action"""
        return self.get_company_incidents(
            tenant_id,
            status_filter=[IncidentStatus.PENDING_COMPANY_ACTION]
        )
    
    def get_dispatched_incidents(self, tenant_id: str) -> List[Incident]:
        """Get dispatched incidents"""
        return self.get_company_incidents(
            tenant_id,
            status_filter=[IncidentStatus.DISPATCHED]
        )
    
    def get_incident_stats(
        self,
        tenant_id: str,
        connector_scope: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get incident statistics for a tenant, optionally filtered by connector scope.

        Args:
            tenant_id: Tenant ID
            connector_scope: Optional connector scope filter (empty = all)
        """
        tenant_incidents = [
            inc for inc in self.incidents.values()
            if inc.tenant_id == tenant_id
            and (not connector_scope or self._matches_connector_scope(inc, connector_scope))
        ]
        
        total = len(tenant_incidents)
        
        # NEW count: Portal/chatbot incidents created in last 24 hours
        now = datetime.utcnow()
        twenty_four_hours_ago = now - timedelta(hours=24)
        new_count = sum(
            1 for inc in tenant_incidents 
            if (inc.external_ref is None or not inc.external_ref.get("connector_type"))
            and inc.created_at >= twenty_four_hours_ago
        )
        
        in_progress = sum(1 for inc in tenant_incidents if inc.status in (
            IncidentStatus.IN_PROGRESS, IncidentStatus.WAITING_INPUT, IncidentStatus.PAUSED,
        ))
        pending = sum(1 for inc in tenant_incidents if inc.status == IncidentStatus.PENDING_COMPANY_ACTION)
        dispatched = sum(1 for inc in tenant_incidents if inc.status == IncidentStatus.DISPATCHED)
        resolved = sum(1 for inc in tenant_incidents if inc.status == IncidentStatus.RESOLVED)
        completed = sum(1 for inc in tenant_incidents if inc.status == IncidentStatus.COMPLETED)
        false_reports = sum(1 for inc in tenant_incidents if inc.status == IncidentStatus.FALSE_REPORT)

        risk_scores = [inc.risk_score for inc in tenant_incidents if inc.risk_score is not None]
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0

        return {
            "total": total,
            "new": new_count,
            "in_progress": in_progress,
            "pending": pending,
            "dispatched": dispatched,
            "resolved": resolved,
            "completed": completed,
            "false_reports": false_reports,
            "avg_risk_score": avg_risk
        }
    
    def get_agent_incidents(
        self,
        agent_id: str,
        status_filter: Optional[List[str]] = None
    ) -> List[Incident]:
        """
        Get all incidents assigned to a specific field agent
        
        Args:
            agent_id: Agent ID
            status_filter: Optional list of agent statuses to filter (ASSIGNED, IN_PROGRESS, COMPLETED)
        
        Returns:
            List of incidents assigned to the agent
        """
        incidents = []
        for incident in self.incidents.values():
            is_primary = incident.assigned_agent_id == agent_id
            is_backup = any(
                ba.get("agent_id") == agent_id
                for ba in (incident.backup_agents or [])
            )
            if is_primary or is_backup:
                # Apply status filter if provided
                if status_filter is None or incident.agent_status in status_filter:
                    incidents.append(incident)

        # Sort by assigned_at descending (most recent first)
        incidents.sort(key=lambda x: x.assigned_at or datetime.min, reverse=True)

        logger.info(f"Found {len(incidents)} incidents for agent {agent_id}")
        return incidents
    
    def update_agent_status(
        self,
        incident_id: str,
        agent_status: str
    ) -> Optional[Incident]:
        """
        Update field agent status for an incident
        
        Args:
            incident_id: Incident ID
            agent_status: New agent status (ASSIGNED, IN_PROGRESS, COMPLETED)
        
        Returns:
            Updated Incident or None
        """
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        incident.agent_status = agent_status
        incident.updated_at = datetime.utcnow()

        # Add status history entry for the transition
        agent = self.agents.get(incident.assigned_agent_id) if incident.assigned_agent_id else None
        agent_name = agent.full_name if agent else "Engineer"
        messages = {
            "EN_ROUTE": f"{agent_name} is on the way to your location.",
            "ON_SITE": f"{agent_name} has arrived on site.",
            "IN_PROGRESS": f"{agent_name} has started work on the issue.",
            "COMPLETED": f"{agent_name} has completed the work.",
        }
        if agent_status in messages:
            self._add_status_history(incident, agent_status.lower(), messages[agent_status])

        milestone_by_status = {
            "EN_ROUTE": "depart",
            "ON_SITE": "on_site",
            "IN_PROGRESS": "diagnosis_started",
            "COMPLETED": "handoff_done",
        }
        milestone_key = milestone_by_status.get(agent_status)
        if milestone_key:
            spec = FIELD_MILESTONE_CATALOG[milestone_key]
            if incident.field_activity is None:
                incident.field_activity = []
            incident.field_activity.append({
                "activity_id": f"ACT_{uuid.uuid4().hex[:10].upper()}",
                "milestone": milestone_key,
                "label": spec["label"],
                "message": messages.get(agent_status, spec["message"]),
                "notes": "",
                "created_by": incident.assigned_agent_id or "system",
                "metadata": {"source": "agent_status_update"},
                "timestamp": datetime.utcnow().isoformat(),
            })

        logger.info(f"Updated agent status for incident {incident_id}: {agent_status}")

        # Notify user about agent status change
        user_messages = {
            "EN_ROUTE": f"{agent_name} is on the way to your location.",
            "ON_SITE": f"{agent_name} has arrived on site.",
            "IN_PROGRESS": f"{agent_name} has started working on the issue.",
            "COMPLETED": f"{agent_name} has completed the work on your incident.",
        }
        if agent_status in user_messages:
            self.push_notification(
                incident.user_id,
                f"Engineer {agent_status.replace('_', ' ').title()}",
                user_messages[agent_status],
                notif_type="info" if agent_status != "COMPLETED" else "success",
                incident_id=incident_id,
                link=f"/my-reports/{incident_id}",
            )      
        return incident
