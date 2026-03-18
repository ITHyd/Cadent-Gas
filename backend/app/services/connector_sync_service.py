"""ConnectorSyncService — bidirectional sync orchestrator.

Bridges the incident lifecycle with the connector framework.

Outbound (platform → external):
  When an incident is finalized, assigned, updated, or resolved this service
  converts it to a CanonicalTicket, publishes a SyncEvent, and pushes it.

Inbound (external → platform):
  When a webhook arrives from an external system this service receives the
  CanonicalTicket, publishes an INBOUND SyncEvent, looks up the linked
  incident, and applies the changes.

Designed to be injected into IncidentService as an optional dependency so the
existing incident flow is unaffected when connectors are not configured.
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from app.connectors.base_connector import ConnectorError
from app.connectors.connector_manager import ConnectorManager
from app.connectors.sync_event_bus import SyncEventBus
from app.models.connector import (
    CanonicalStatus,
    CanonicalTicket,
    ConnectorType,
    ExternalTicketLink,
    SyncDirection,
    SyncEvent,
    SyncEventType,
    SyncStatus,
)
from app.models.incident import Incident, IncidentStatus

logger = logging.getLogger(__name__)


def _get_transformer(connector_type: ConnectorType):
    """Return the transformer module for a given connector type."""
    if connector_type == ConnectorType.SERVICENOW:
        from app.connectors.implementations.servicenow import sn_transformer
        return sn_transformer
    elif connector_type == ConnectorType.SAP:
        from app.connectors.implementations.sap import sap_transformer
        return sap_transformer
    else:
        # Fallback to ServiceNow transformer for unknown types
        from app.connectors.implementations.servicenow import sn_transformer
        return sn_transformer


class ConnectorSyncService:
    """Orchestrates bidirectional data sync between platform incidents and external systems."""

    # Canonical status → IncidentStatus (inbound mapping)
    _CANONICAL_TO_INCIDENT_STATUS: Dict[str, IncidentStatus] = {
        "new": IncidentStatus.NEW,
        "open": IncidentStatus.IN_PROGRESS,
        "in_progress": IncidentStatus.IN_PROGRESS,
        "pending": IncidentStatus.WAITING_INPUT,
        "on_hold": IncidentStatus.PAUSED,
        "resolved": IncidentStatus.RESOLVED,
        "closed": IncidentStatus.CLOSED,
        "cancelled": IncidentStatus.FALSE_REPORT,
    }

    def __init__(
        self,
        connector_manager: ConnectorManager,
        sync_event_bus: SyncEventBus,
        incident_service: Any,  # avoid circular import — typed loosely
        db: Any = None,         # MongoDB reference for user lookups
    ):
        self._manager = connector_manager
        self._bus = sync_event_bus
        self._incident_service = incident_service
        self._db = db

        # In-memory store for ExternalTicketLinks (MongoDB in production)
        self._links: Dict[str, ExternalTicketLink] = {}
        # Index: (incident_id, connector_type) → link_id
        self._link_index: Dict[str, str] = {}
        # Reverse index: external_id → incident_id (populated by _create_link)
        self._external_to_incident: Dict[str, str] = {}

    def initialize(self) -> None:
        """Register event bus handlers.  Call once at startup.

        The event bus dispatches by ``event_type`` only. Since outbound and
        inbound events may share the same type (e.g. TICKET_UPDATED), the
        handlers check ``event.direction`` internally to decide whether to
        push or apply changes.
        """
        self._bus.register_handler(
            SyncEventType.TICKET_CREATED,
            self._dispatch_by_direction,
        )
        self._bus.register_handler(
            SyncEventType.TICKET_UPDATED,
            self._dispatch_by_direction,
        )
        self._bus.register_handler(
            SyncEventType.STATUS_CHANGED,
            self._dispatch_by_direction,
        )
        self._bus.register_handler(
            SyncEventType.TICKET_RESOLVED,
            self._dispatch_by_direction,
        )
        self._bus.register_handler(
            SyncEventType.TICKET_CLOSED,
            self._dispatch_by_direction,
        )
        self._bus.register_handler(
            SyncEventType.ASSIGNEE_CHANGED,
            self._dispatch_by_direction,
        )
        self._bus.register_handler(
            SyncEventType.COMMENT_ADDED,
            self._dispatch_by_direction,
        )
        logger.info("ConnectorSyncService initialized — outbound + inbound handlers registered")

    async def _dispatch_by_direction(self, event: SyncEvent) -> bool:
        """Route an event to the correct handler based on direction."""
        if event.direction == SyncDirection.INBOUND:
            return await self._handle_inbound_update(event)
        # Outbound
        if event.event_type == SyncEventType.TICKET_CREATED:
            return await self._handle_outbound_ticket_created(event)
        return await self._handle_outbound_ticket_updated(event)

    # ── Public hooks (called from IncidentService) ────────────────────────

    async def on_incident_finalized(self, incident: Incident) -> Optional[SyncEvent]:
        """Called after finalize_incident().  Publishes TICKET_CREATED event."""
        connector_type = self._resolve_connector_type(incident.tenant_id)
        if not connector_type:
            return None  # no active connector for this tenant

        transformer = _get_transformer(connector_type)
        canonical = transformer.incident_to_canonical(incident)

        event = await self._bus.publish(
            tenant_id=incident.tenant_id,
            connector_type=connector_type,
            event_type=SyncEventType.TICKET_CREATED,
            direction=SyncDirection.OUTBOUND,
            source="api_push",
            payload=canonical.dict(),
            incident_id=incident.incident_id,
        )

        if event:
            # Immediately try to process (fire-and-forget style for now)
            await self._bus.process_all_pending()

        return event

    async def on_incident_updated(
        self, incident: Incident, changed_fields: Optional[List[str]] = None
    ) -> Optional[SyncEvent]:
        """Called after incident updates (assign, status change, resolve, etc.)."""
        # Only sync if incident already has an external link
        if not incident.external_ref or not incident.external_ref.get("external_id"):
            return None

        connector_type = self._resolve_connector_type(incident.tenant_id)
        if not connector_type:
            return None

        # Choose event type based on what changed
        event_type = SyncEventType.TICKET_UPDATED
        if changed_fields:
            if "status" in changed_fields:
                event_type = SyncEventType.STATUS_CHANGED
            elif "resolved_at" in changed_fields or "resolution_notes" in changed_fields:
                event_type = SyncEventType.TICKET_RESOLVED

        transformer = _get_transformer(connector_type)
        canonical = transformer.incident_to_canonical(incident)

        event = await self._bus.publish(
            tenant_id=incident.tenant_id,
            connector_type=connector_type,
            event_type=event_type,
            direction=SyncDirection.OUTBOUND,
            source="api_push",
            payload=canonical.dict(),
            incident_id=incident.incident_id,
            external_id=incident.external_ref.get("external_id"),
        )

        if event:
            await self._bus.process_all_pending()

        return event

    # ── Event handlers ────────────────────────────────────────────────────

    async def _handle_outbound_ticket_created(self, event: SyncEvent) -> bool:
        """Handle TICKET_CREATED: push new ticket to external system."""
        try:
            canonical = self._reconstruct_canonical(event.payload)

            result = await self._manager.push_ticket(
                tenant_id=event.tenant_id,
                connector_type=event.connector_type,
                ticket=canonical,
            )

            # Update incident with external reference
            self._update_incident_external_ref(
                incident_id=event.incident_id,
                connector_type=event.connector_type,
                external_id=result["external_id"],
                external_number=result["external_number"],
                external_url=result.get("external_url"),
            )

            # Create ExternalTicketLink
            self._create_link(
                incident_id=event.incident_id,
                tenant_id=event.tenant_id,
                connector_type=event.connector_type,
                external_id=result["external_id"],
                external_number=result["external_number"],
                external_url=result.get("external_url"),
                event_id=event.event_id,
            )

            logger.info(
                "Outbound ticket created: incident=%s → external=%s (%s)",
                event.incident_id,
                result["external_number"],
                result["external_id"],
            )
            return True

        except ConnectorError as exc:
            event.error_message = str(exc)
            event.error_details = {"retriable": exc.retriable}
            logger.warning("Outbound push failed: %s — %s", event.incident_id, exc)
            return exc.retriable  # return False to retry if retriable

        except Exception as exc:
            event.error_message = str(exc)
            logger.error("Unexpected error in outbound push: %s", exc, exc_info=True)
            return False

    async def _handle_outbound_ticket_updated(self, event: SyncEvent) -> bool:
        """Handle TICKET_UPDATED / STATUS_CHANGED / TICKET_RESOLVED."""
        try:
            canonical = self._reconstruct_canonical(event.payload)

            result = await self._manager.push_ticket(
                tenant_id=event.tenant_id,
                connector_type=event.connector_type,
                ticket=canonical,
            )

            # Update link's last_synced_at
            link_key = f"{event.incident_id}:{event.connector_type.value}"
            link_id = self._link_index.get(link_key)
            if link_id and link_id in self._links:
                link = self._links[link_id]
                link.last_synced_at = datetime.utcnow()
                link.last_sync_direction = SyncDirection.OUTBOUND
                link.last_sync_event_id = event.event_id
                link.sync_status = SyncStatus.LINKED
                link.version += 1

            # Update incident external_ref timestamp
            self._update_incident_external_ref(
                incident_id=event.incident_id,
                connector_type=event.connector_type,
                external_id=result["external_id"],
                external_number=result["external_number"],
                external_url=result.get("external_url"),
            )

            logger.info(
                "Outbound ticket updated: incident=%s → external=%s",
                event.incident_id,
                result.get("external_number"),
            )
            return True

        except ConnectorError as exc:
            event.error_message = str(exc)
            logger.warning("Outbound update failed: %s — %s", event.incident_id, exc)
            return False
        except Exception as exc:
            event.error_message = str(exc)
            logger.error("Unexpected error in outbound update: %s", exc, exc_info=True)
            return False

    # ── Inbound webhook hook (called from webhook API) ──────────────────

    async def on_webhook_received(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        canonical: CanonicalTicket,
        raw_payload: Dict[str, Any],
    ) -> Optional[SyncEvent]:
        """Called by the webhook endpoint after handle_webhook() returns a CanonicalTicket.

        Publishes an inbound SyncEvent and processes it immediately.
        """
        # Detect event type from the canonical ticket
        external_id = canonical.external_id or canonical.custom_fields.get("sn_sys_id", "")

        # Look up existing canonical via the linked incident (if any)
        incident_id = self._external_to_incident.get(external_id)
        old_canonical = None
        transformer = _get_transformer(connector_type)
        if incident_id:
            incident = self._incident_service.get_incident(incident_id)
            if incident:
                old_canonical = transformer.incident_to_canonical(incident)

        change_info = transformer.detect_changes(canonical, old_canonical)

        event = await self._bus.publish(
            tenant_id=tenant_id,
            connector_type=connector_type,
            event_type=change_info["event_type"],
            direction=SyncDirection.INBOUND,
            source="webhook",
            payload=canonical.dict(),
            incident_id=incident_id,
            external_id=external_id,
        )

        if event:
            await self._bus.process_all_pending()

        return event

    # ── Inbound event handler ─────────────────────────────────────────────

    async def _handle_inbound_update(self, event: SyncEvent) -> bool:
        """Handle an inbound event — apply external changes to platform incident."""
        try:
            canonical = self._reconstruct_canonical(event.payload)
            external_id = event.external_id or canonical.external_id or ""

            # Look up incident by external_id
            incident_id = event.incident_id or self._external_to_incident.get(external_id)
            if not incident_id:
                logger.warning(
                    "Inbound event for unknown external_id=%s — no linked incident",
                    external_id,
                )
                # Return True so the event is not retried (it's not a transient error)
                return True

            incident = self._incident_service.get_incident(incident_id)
            if not incident:
                logger.warning("Linked incident %s not found in store", incident_id)
                return True

            # Resolve assignee phone → platform agent ID
            await self._resolve_identities(canonical, incident.tenant_id)

            # Apply changes
            self._apply_inbound_changes(incident, canonical, event.connector_type)

            # Update ExternalTicketLink
            link_key = f"{incident_id}:{event.connector_type.value}"
            link_id = self._link_index.get(link_key)
            if link_id and link_id in self._links:
                link = self._links[link_id]
                link.last_synced_at = datetime.utcnow()
                link.last_sync_direction = SyncDirection.INBOUND
                link.last_sync_event_id = event.event_id
                link.sync_status = SyncStatus.LINKED
                link.version += 1

            logger.info(
                "Inbound update applied: external=%s → incident=%s (type=%s)",
                external_id, incident_id, event.event_type.value,
            )
            return True

        except Exception as exc:
            event.error_message = str(exc)
            logger.error("Failed to apply inbound update: %s", exc, exc_info=True)
            return False

    def _apply_inbound_changes(
        self, incident: Incident, canonical: CanonicalTicket, connector_type: Optional[ConnectorType] = None
    ) -> None:
        """Apply changes from a CanonicalTicket to an Incident (inbound sync)."""
        now = datetime.utcnow()
        changes_applied: List[str] = []
        source_label = f"{connector_type.value}_webhook" if connector_type else "external_webhook"

        # Status mapping
        if canonical.status:
            status_str = canonical.status.value if isinstance(canonical.status, CanonicalStatus) else str(canonical.status)
            new_status = self._CANONICAL_TO_INCIDENT_STATUS.get(status_str)
            if new_status and incident.status != new_status:
                old_status = incident.status
                incident.status = new_status
                changes_applied.append(f"status: {old_status.value}→{new_status.value}")

                # Append to status_history for timeline visibility
                if hasattr(incident, "status_history") and isinstance(incident.status_history, list):
                    incident.status_history.append({
                        "from": old_status.value,
                        "to": new_status.value,
                        "changed_at": now.isoformat(),
                        "changed_by": source_label,
                        "reason": f"Inbound sync from {source_label}",
                    })

        # Assignee
        if canonical.assignee_id and canonical.assignee_id != incident.assigned_agent_id:
            incident.assigned_agent_id = canonical.assignee_id
            changes_applied.append("assignee_id")

        # Resolution
        if canonical.resolution_notes and canonical.resolution_notes != incident.resolution_notes:
            incident.resolution_notes = canonical.resolution_notes
            changes_applied.append("resolution_notes")

        if canonical.resolved_at and incident.resolved_at != canonical.resolved_at:
            incident.resolved_at = canonical.resolved_at
            changes_applied.append("resolved_at")

        # Update sync metadata
        incident.sync_version = (incident.sync_version or 0) + 1
        incident.updated_at = now

        if incident.external_ref and isinstance(incident.external_ref, dict):
            incident.external_ref["last_synced_at"] = now.isoformat()
            incident.external_ref["sync_status"] = "linked"

        if changes_applied:
            logger.info(
                "Inbound changes applied to %s: %s",
                incident.incident_id, ", ".join(changes_applied),
            )

    # ── User identity resolution ───────────────────────────────────────

    async def _resolve_user_by_phone(self, phone: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Look up a platform user by phone number within a tenant."""
        if self._db is None or not phone:
            return None
        phone = str(phone).strip()
        if not phone:
            return None
        return await self._db.users.find_one(
            {"phone": phone, "tenant_id": tenant_id},
            {"user_id": 1, "full_name": 1, "role": 1, "_id": 0},
        )

    async def _resolve_user_by_id(self, user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Look up a platform user by user_id within a tenant."""
        if self._db is None or not user_id:
            return None
        user_id = str(user_id).strip()
        if not user_id:
            return None
        return await self._db.users.find_one(
            {"user_id": user_id, "tenant_id": tenant_id},
            {"user_id": 1, "full_name": 1, "role": 1, "_id": 0},
        )

    async def _auto_provision_user(
        self, phone: str, name: str, role: str, tenant_id: str, source: str = "sap",
    ) -> Dict[str, Any]:
        """Auto-create a platform user from external system data.

        Called when a SAP reporter/engineer has no matching platform account.
        The created user can immediately log in via OTP.
        """
        phone = str(phone).strip()
        name = str(name).strip()

        # Check same tenant first, then cross-tenant (phone index is global)
        existing = await self._resolve_user_by_phone(phone, tenant_id)
        if existing:
            return existing
        cross = await self._db.users.find_one(
            {"phone": phone},
            {"user_id": 1, "full_name": 1, "role": 1, "_id": 0},
        )
        if cross:
            return cross

        user_id = f"ext_{role}_{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        doc = {
            "user_id": user_id,
            "phone": phone,
            "full_name": name,
            "role": role,
            "tenant_id": tenant_id,
            "is_active": True,
            "auto_provisioned": True,
            "provisioned_from": source,
            "created_at": now,
            "updated_at": now,
            "last_login": None,
        }
        try:
            await self._db.users.insert_one(doc)
        except DuplicateKeyError:
            # Race condition or cross-tenant duplicate — return existing user
            fallback = await self._db.users.find_one(
                {"phone": phone},
                {"user_id": 1, "full_name": 1, "role": 1, "_id": 0},
            )
            if fallback:
                return fallback
            return {"user_id": "unknown", "full_name": name, "role": role}

        logger.info(
            "Auto-provisioned %s: user_id=%s name=%s phone=%s tenant=%s",
            role, user_id, name, phone, tenant_id,
        )
        return {"user_id": user_id, "full_name": name, "role": role}

    async def _resolve_identities(self, canonical: CanonicalTicket, tenant_id: str) -> Dict[str, bool]:
        """Resolve reporter and assignee from phone numbers to platform user IDs.

        If no existing user is found and we have both phone + name, auto-provision
        a new platform user so they appear in Tenant Management and can log in.
        """
        results = {
            "reporter_resolved": False,
            "reporter_provisioned": False,
            "assignee_resolved": False,
            "assignee_provisioned": False,
        }

        # Legacy compatibility:
        # If *_id carries a non-platform value (for example a SAP display name),
        # clear it so phone+name identity resolution can proceed.
        if self._db is not None and canonical.reporter_id:
            reporter = await self._resolve_user_by_id(canonical.reporter_id, tenant_id)
            if reporter:
                canonical.reporter_name = canonical.reporter_name or reporter.get("full_name")
            else:
                if not canonical.reporter_name:
                    canonical.reporter_name = canonical.reporter_id
                canonical.reporter_id = None

        if self._db is not None and canonical.assignee_id:
            assignee = await self._resolve_user_by_id(canonical.assignee_id, tenant_id)
            if assignee:
                canonical.assignee_name = canonical.assignee_name or assignee.get("full_name")
            else:
                if not canonical.assignee_name:
                    canonical.assignee_name = canonical.assignee_id
                canonical.assignee_id = None

        # Role hints allow connectors to override default user/agent roles
        hints = canonical.custom_fields or {}
        reporter_role = hints.get("reporter_role", "user")
        assignee_role = hints.get("assignee_role", "agent")

        # Resolve reporter
        if canonical.reporter_contact and not canonical.reporter_id:
            user = await self._resolve_user_by_phone(canonical.reporter_contact, tenant_id)
            if user:
                canonical.reporter_id = user["user_id"]
                canonical.reporter_name = canonical.reporter_name or user.get("full_name")
                results["reporter_resolved"] = True
                logger.info("Resolved reporter %s -> %s", canonical.reporter_contact, user["user_id"])
            elif self._db is not None and canonical.reporter_name:
                user = await self._auto_provision_user(
                    phone=canonical.reporter_contact,
                    name=canonical.reporter_name,
                    role=reporter_role,
                    tenant_id=tenant_id,
                )
                canonical.reporter_id = user["user_id"]
                results["reporter_provisioned"] = True

        # Resolve assignee
        if canonical.assignee_contact and not canonical.assignee_id:
            agent = await self._resolve_user_by_phone(canonical.assignee_contact, tenant_id)
            if agent:
                canonical.assignee_id = agent["user_id"]
                canonical.assignee_name = canonical.assignee_name or agent.get("full_name")
                results["assignee_resolved"] = True
                logger.info("Resolved assignee %s -> %s", canonical.assignee_contact, agent["user_id"])
            elif self._db is not None and canonical.assignee_name:
                agent = await self._auto_provision_user(
                    phone=canonical.assignee_contact,
                    name=canonical.assignee_name,
                    role=assignee_role,
                    tenant_id=tenant_id,
                )
                canonical.assignee_id = agent["user_id"]
                results["assignee_provisioned"] = True

        return results

    # ── Internal helpers ──────────────────────────────────────────────────

    def _resolve_connector_type(self, tenant_id: str) -> Optional[ConnectorType]:
        """Find the active connector type for a tenant (returns first active)."""
        configs = self._manager.get_tenant_configs(tenant_id)
        for cfg in configs:
            if cfg.is_active:
                return cfg.connector_type
        return None

    def _reconstruct_canonical(self, payload: Dict[str, Any]):
        """Rebuild a CanonicalTicket from an event payload dict."""
        from app.models.connector import CanonicalTicket
        return CanonicalTicket(**payload)

    def _update_incident_external_ref(
        self,
        incident_id: str,
        connector_type: ConnectorType,
        external_id: str,
        external_number: str,
        external_url: Optional[str] = None,
    ) -> None:
        """Update the incident's external_ref dict."""
        incident = self._incident_service.get_incident(incident_id)
        if not incident:
            logger.warning("Cannot update external_ref — incident %s not found", incident_id)
            return

        incident.external_ref = {
            "connector_type": connector_type.value,
            "external_id": external_id,
            "external_number": external_number,
            "external_url": external_url,
            "sync_status": "linked",
            "last_synced_at": datetime.utcnow().isoformat(),
        }
        incident.sync_version += 1
        incident.updated_at = datetime.utcnow()

    def _create_link(
        self,
        incident_id: str,
        tenant_id: str,
        connector_type: ConnectorType,
        external_id: str,
        external_number: str,
        external_url: Optional[str],
        event_id: str,
    ) -> ExternalTicketLink:
        """Create and store an ExternalTicketLink."""
        now = datetime.utcnow()
        link = ExternalTicketLink(
            link_id=f"LNK_{uuid.uuid4().hex[:12].upper()}",
            incident_id=incident_id,
            tenant_id=tenant_id,
            connector_type=connector_type,
            external_id=external_id,
            external_number=external_number,
            external_url=external_url,
            sync_status=SyncStatus.LINKED,
            last_synced_at=now,
            last_sync_direction=SyncDirection.OUTBOUND,
            last_sync_event_id=event_id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._links[link.link_id] = link
        self._link_index[f"{incident_id}:{connector_type.value}"] = link.link_id
        # Populate reverse index so inbound webhooks can find the incident
        self._external_to_incident[external_id] = incident_id
        logger.info("Created ExternalTicketLink: %s → %s", incident_id, external_number)
        return link

    # ── Backfill & Reconciliation ────────────────────────────────────────

    async def sync_external_identities(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        limit: int = 500,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve/provision tenant users from external ticket identities only.

        This does not create incidents. It scans external tickets, extracts
        reporter/assignee identity fields, and ensures matching platform users
        (roles: user, agent) exist for Tenant Management visibility.
        """
        connector = self._manager.get_active_connector(tenant_id, connector_type)
        if not connector:
            raise ValueError(f"No active {connector_type.value} connector for tenant {tenant_id}")

        try:
            external_tickets = await connector.pull_tickets(
                filters=filters or {},
                limit=limit,
                offset=offset,
            )
        except ConnectorError as exc:
            raise ValueError(f"Failed to pull tickets for identity sync: {exc}")

        results = {
            "connector_type": connector_type.value,
            "tickets_scanned": 0,
            "reporters_resolved": 0,
            "reporters_provisioned": 0,
            "assignees_resolved": 0,
            "assignees_provisioned": 0,
            "failed": 0,
        }

        for ext_ticket in external_tickets:
            try:
                canonical = ext_ticket if isinstance(ext_ticket, CanonicalTicket) else CanonicalTicket(**ext_ticket)
                identity_result = await self._resolve_identities(canonical, tenant_id)
                results["tickets_scanned"] += 1
                results["reporters_resolved"] += 1 if identity_result["reporter_resolved"] else 0
                results["reporters_provisioned"] += 1 if identity_result["reporter_provisioned"] else 0
                results["assignees_resolved"] += 1 if identity_result["assignee_resolved"] else 0
                results["assignees_provisioned"] += 1 if identity_result["assignee_provisioned"] else 0
            except Exception:
                results["failed"] += 1
                logger.exception(
                    "Identity sync failed for one external ticket: tenant=%s connector=%s",
                    tenant_id,
                    connector_type.value,
                )

        logger.info(
            "Identity sync completed: tenant=%s connector=%s scanned=%d provisioned(u=%d,a=%d) failed=%d",
            tenant_id,
            connector_type.value,
            results["tickets_scanned"],
            results["reporters_provisioned"],
            results["assignees_provisioned"],
            results["failed"],
        )
        return results

    # Backfill & Reconciliation
    async def backfill(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        limit: int = 100,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Pull historical tickets from external system and import them as incidents in batch.

        Creates incidents directly, links them to the external tickets, and publishes
        a single summary sync event (instead of one event per ticket).
        """
        connector = self._manager.get_active_connector(tenant_id, connector_type)
        if not connector:
            raise ValueError(f"No active {connector_type.value} connector for tenant {tenant_id}")

        results = {"imported": 0, "skipped": 0, "failed": 0, "errors": []}

        try:
            external_tickets = await connector.pull_tickets(
                filters=filters or {},
                limit=limit,
                offset=offset,
            )
        except ConnectorError as exc:
            raise ValueError(f"Failed to pull tickets: {exc}")

        for ext_ticket in external_tickets:
            try:
                # pull_tickets() already returns CanonicalTicket objects
                canonical = ext_ticket if isinstance(ext_ticket, CanonicalTicket) else CanonicalTicket(**ext_ticket)
                ext_id = canonical.external_id or ""

                # Skip if already linked
                if ext_id in self._external_to_incident:
                    results["skipped"] += 1
                    continue

                # Create incident directly from canonical ticket
                incident = await self._create_incident_from_canonical(canonical, tenant_id, connector_type)

                # Create ExternalTicketLink so webhooks can find this incident later
                self._create_link(
                    incident_id=incident.incident_id,
                    tenant_id=tenant_id,
                    connector_type=connector_type,
                    external_id=ext_id,
                    external_number=canonical.external_number or ext_id,
                    external_url=None,
                    event_id=f"backfill_{ext_id}",
                )

                results["imported"] += 1

            except Exception as exc:
                results["failed"] += 1
                results["errors"].append({
                    "external_id": ext_id or "unknown",
                    "external_number": (canonical.external_number or ext_id) if canonical else "unknown",
                    "error": str(exc),
                })
                logger.warning("Backfill import failed for ticket %s: %s", ext_id, exc)

        # Log ONE summary sync event (already completed — work is done above)
        if external_tickets:
            from app.models.connector import SyncEventStatus
            summary_event = await self._bus.publish(
                tenant_id=tenant_id,
                connector_type=connector_type,
                event_type=SyncEventType.TICKET_CREATED,
                direction=SyncDirection.INBOUND,
                source="backfill_batch",
                payload={
                    "batch": True,
                    "total_pulled": len(external_tickets),
                    "imported": results["imported"],
                    "skipped": results["skipped"],
                    "failed": results["failed"],
                },
                external_id=f"backfill_{tenant_id}_{connector_type.value}",
            )
            # Mark as completed immediately — incidents were already created above
            if summary_event:
                summary_event.status = SyncEventStatus.COMPLETED
                summary_event.processed_at = datetime.utcnow()
                # Remove from pending queue so it doesn't get processed again
                try:
                    self._bus._pending.remove(summary_event)
                except ValueError:
                    pass

        logger.info(
            "Backfill completed: tenant=%s connector=%s imported=%d skipped=%d failed=%d",
            tenant_id, connector_type.value, results["imported"], results["skipped"], results["failed"],
        )
        return results

    async def _create_incident_from_canonical(
        self, canonical: CanonicalTicket, tenant_id: str, connector_type: ConnectorType
    ) -> Incident:
        """Create an Incident from a CanonicalTicket (used during backfill)."""
        # Resolve reporter/assignee phone numbers to platform user IDs
        await self._resolve_identities(canonical, tenant_id)

        now = datetime.utcnow()
        description = canonical.title
        if canonical.description and canonical.description != canonical.title:
            description = f"{canonical.title}\n\n{canonical.description}"

        incident = self._incident_service.create_incident(
            tenant_id=tenant_id,
            user_id=canonical.reporter_id or "external_import",
            description=description,
            incident_type=canonical.category,
            user_name=canonical.reporter_name,
            user_phone=canonical.reporter_contact,
            location=canonical.location,
            geo_location=canonical.geo_location,
        )

        # Map external status to incident status
        if canonical.status:
            status_str = canonical.status.value if isinstance(canonical.status, CanonicalStatus) else str(canonical.status)
            mapped_status = self._CANONICAL_TO_INCIDENT_STATUS.get(status_str)
            if mapped_status:
                incident.status = mapped_status

        # Set external reference so the UI shows the link
        incident.external_ref = {
            "connector_type": connector_type.value,
            "external_id": canonical.external_id,
            "external_number": canonical.external_number,
            "sync_status": "linked",
            "last_synced_at": now.isoformat(),
        }

        # Copy over resolution data if present
        if canonical.resolution_notes:
            incident.resolution_notes = canonical.resolution_notes
        if canonical.resolved_at:
            incident.resolved_at = canonical.resolved_at
        if canonical.risk_score is not None:
            incident.risk_score = canonical.risk_score

        # Set resolved assignee as assigned agent
        if canonical.assignee_id:
            incident.assigned_agent_id = canonical.assignee_id

        incident.sync_version = 1
        incident.updated_at = now

        return incident

    async def reconcile(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
    ) -> Dict[str, Any]:
        """Compare linked tickets between platform and external system to detect drift.

        Returns summary of drift details for each linked ticket.
        """
        connector = self._manager.get_active_connector(tenant_id, connector_type)
        if not connector:
            raise ValueError(f"No active {connector_type.value} connector for tenant {tenant_id}")

        transformer = _get_transformer(connector_type)
        results = {"total_checked": 0, "in_sync": 0, "drifted": 0, "errors": 0, "drift_details": []}

        tenant_links = [l for l in self._links.values() if l.tenant_id == tenant_id and l.connector_type == connector_type]

        for link in tenant_links:
            results["total_checked"] += 1
            try:
                # Pull current state from external system
                ext_ticket = await connector.pull_ticket(link.external_id)
                if not ext_ticket:
                    results["errors"] += 1
                    continue

                # Get internal incident
                incident = self._incident_service.get_incident(link.incident_id)
                if not incident:
                    results["errors"] += 1
                    continue

                internal_canonical = transformer.incident_to_canonical(incident)
                external_canonical = CanonicalTicket(**ext_ticket) if isinstance(ext_ticket, dict) else ext_ticket

                # Compare key fields
                drifts = self._compare_tickets(internal_canonical, external_canonical)
                if drifts:
                    results["drifted"] += 1
                    results["drift_details"].append({
                        "incident_id": link.incident_id,
                        "external_id": link.external_id,
                        "external_number": link.external_number,
                        "drifted_fields": drifts,
                    })
                else:
                    results["in_sync"] += 1

            except Exception as exc:
                results["errors"] += 1
                logger.warning("Reconcile error for link %s: %s", link.link_id, exc)

        logger.info(
            "Reconciliation completed: tenant=%s connector=%s checked=%d drifted=%d",
            tenant_id, connector_type.value, results["total_checked"], results["drifted"],
        )
        return results

    def _compare_tickets(
        self, internal: CanonicalTicket, external: CanonicalTicket
    ) -> List[Dict[str, Any]]:
        """Compare two canonical tickets and return a list of drifted fields."""
        drifts = []
        compare_fields = ["status", "priority", "title", "assignee_id", "resolution_notes"]

        for field in compare_fields:
            int_val = getattr(internal, field, None)
            ext_val = getattr(external, field, None)
            if int_val is not None and ext_val is not None:
                int_str = int_val.value if hasattr(int_val, "value") else str(int_val)
                ext_str = ext_val.value if hasattr(ext_val, "value") else str(ext_val)
                if int_str != ext_str:
                    drifts.append({
                        "field": field,
                        "internal_value": int_str,
                        "external_value": ext_str,
                    })
        return drifts

    # ── Query helpers (used by API) ───────────────────────────────────────

    def get_link(self, incident_id: str, connector_type: ConnectorType) -> Optional[ExternalTicketLink]:
        link_key = f"{incident_id}:{connector_type.value}"
        link_id = self._link_index.get(link_key)
        return self._links.get(link_id) if link_id else None

    def get_tenant_links(self, tenant_id: str) -> List[ExternalTicketLink]:
        return [l for l in self._links.values() if l.tenant_id == tenant_id]

    async def clear_tenant_data(self, tenant_id: str) -> Dict[str, int]:
        """Remove all sync data for a tenant (events, links, reverse index)."""
        # Clear links
        links_removed = 0
        for link in list(self._links.values()):
            if link.tenant_id == tenant_id:
                self._links.pop(link.link_id, None)
                key = f"{link.incident_id}:{link.connector_type.value}"
                self._link_index.pop(key, None)
                self._external_to_incident.pop(link.external_id, None)
                links_removed += 1
        # Clear events via the bus
        events_removed = await self._bus.clear_tenant_events(tenant_id)
        logger.info("Cleared tenant sync data: tenant=%s links=%d events=%d", tenant_id, links_removed, events_removed)
        return {"links_removed": links_removed, "events_removed": events_removed}

