"""ServiceNowConnector — concrete implementation of BaseConnector for ServiceNow.

Implements all 12 abstract methods.  Delegates HTTP calls to ServiceNowClient
and data transformation to sn_transformer.
"""
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, List, Optional

from app.connectors.base_connector import BaseConnector, ConnectorError
from app.connectors.implementations.servicenow.sn_client import ServiceNowClient
from app.connectors.implementations.servicenow.sn_transformer import (
    canonical_to_sn_payload,
    sn_response_to_canonical,
)
from app.models.connector import (
    CanonicalTicket,
    ConnectorConfig,
    ConnectorType,
    HealthStatus,
    TicketAttachment,
    TicketComment,
)

logger = logging.getLogger(__name__)


class ServiceNowConnector(BaseConnector):
    """ServiceNow connector — pushes/pulls incident data via the SN Table API."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        table_name = config.settings.get("table_name", "incident")
        self._client = ServiceNowClient(
            instance_url=config.instance_url,
            auth_method=config.auth_method,
            table_name=table_name,
        )

    # ── Connection Lifecycle ──────────────────────────────────────────────

    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        result = await self._client.authenticate(credentials)
        self._is_authenticated = result
        return result

    async def test_connection(self) -> Dict[str, Any]:
        return await self._client.test_connection()

    async def health_check(self) -> HealthStatus:
        try:
            result = await self._client.test_connection()
            if result["status"] == "ok":
                latency = result.get("latency_ms", 0)
                return HealthStatus.DEGRADED if latency > 5000 else HealthStatus.HEALTHY
            return HealthStatus.DOWN
        except Exception:
            return HealthStatus.DOWN

    # ── Ticket Operations ─────────────────────────────────────────────────

    async def push_ticket(self, ticket: CanonicalTicket) -> Dict[str, Any]:
        """Create or update a ServiceNow incident from a CanonicalTicket."""
        sn_payload = canonical_to_sn_payload(ticket)

        if ticket.external_id:
            # Update existing
            record = await self._client.update_incident(ticket.external_id, sn_payload)
            action = "updated"
        else:
            # Create new
            record = await self._client.create_incident(sn_payload)
            action = "created"

        sys_id = record.get("sys_id", "")
        number = record.get("number", "")
        external_url = f"{self.instance_url}/nav_to.do?uri=incident.do?sys_id={sys_id}"

        logger.info(
            "push_ticket %s: %s (sys_id=%s, number=%s)",
            action, ticket.ticket_id, sys_id, number,
        )

        return {
            "external_id": sys_id,
            "external_number": number,
            "external_url": external_url,
            "action": action,
        }

    async def pull_ticket(self, external_id: str) -> Optional[CanonicalTicket]:
        try:
            sn_data = await self._client.get_incident(external_id)
            if not sn_data:
                return None
            return sn_response_to_canonical(sn_data)
        except ConnectorError:
            logger.warning("Failed to pull ticket %s", external_id, exc_info=True)
            return None

    async def pull_tickets(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalTicket]:
        # Build SN encoded query from filters dict
        query_parts = []
        if filters:
            for key, value in filters.items():
                query_parts.append(f"{key}={value}")
        query = "^".join(query_parts) if query_parts else ""

        records = await self._client.query_incidents(query, limit, offset)
        tickets = []
        for rec in records:
            try:
                tickets.append(sn_response_to_canonical(rec))
            except Exception:
                logger.warning("Failed to parse SN record: %s", rec.get("sys_id"), exc_info=True)
        return tickets

    # ── Comment Operations ────────────────────────────────────────────────

    async def push_comment(
        self, external_id: str, comment: TicketComment
    ) -> Dict[str, Any]:
        is_work_note = not comment.is_public
        prefix = f"[{comment.author_name or comment.author_id or 'Platform'}] "
        await self._client.add_comment(external_id, prefix + comment.body, is_work_note)
        return {"external_comment_id": None, "status": "created"}

    async def pull_comments(self, external_id: str) -> List[TicketComment]:
        # Full journal entry pull requires sys_journal_field table — deferred to Phase 2
        logger.info("pull_comments not yet implemented for ServiceNow")
        return []

    # ── Attachment Operations ─────────────────────────────────────────────

    async def push_attachment(
        self, external_id: str, attachment: TicketAttachment, file_data: bytes
    ) -> Dict[str, Any]:
        record = await self._client.add_attachment(
            sys_id=external_id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            file_data=file_data,
        )
        return {
            "external_attachment_id": record.get("sys_id"),
            "status": "uploaded",
        }

    async def pull_attachments(self, external_id: str) -> List[TicketAttachment]:
        records = await self._client.get_attachments(external_id)
        from datetime import datetime as dt

        attachments = []
        for rec in records:
            attachments.append(
                TicketAttachment(
                    attachment_id=rec.get("sys_id", ""),
                    filename=rec.get("file_name", "unknown"),
                    content_type=rec.get("content_type", "application/octet-stream"),
                    size_bytes=int(rec.get("size_bytes", 0)),
                    source_system="servicenow",
                    external_attachment_id=rec.get("sys_id"),
                    external_url=rec.get("download_link"),
                    uploaded_at=dt.utcnow(),
                )
            )
        return attachments

    # ── Webhook Handling ────────────────────────────────────────────────────

    # Maximum age (seconds) for a webhook timestamp before it's rejected
    WEBHOOK_REPLAY_WINDOW = 300  # 5 minutes

    async def verify_webhook_signature(
        self, payload: bytes, headers: Dict[str, str]
    ) -> bool:
        """Verify HMAC-SHA256 signature from a ServiceNow webhook.

        Expected headers:
            X-ServiceNow-Signature  — hex-encoded HMAC-SHA256 digest
            X-ServiceNow-Timestamp  — Unix epoch seconds (replay protection)

        The HMAC secret is stored in ``self.config.settings["webhook_secret"]``.
        """
        secret = self.config.settings.get("webhook_secret")
        if not secret:
            logger.warning(
                "No webhook_secret configured for connector %s — rejecting webhook",
                self.config.config_id,
            )
            return False

        # -- Signature check ------------------------------------------------
        signature = headers.get("x-servicenow-signature") or headers.get("X-ServiceNow-Signature")
        if not signature:
            logger.warning("Missing X-ServiceNow-Signature header")
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning("Webhook signature mismatch")
            return False

        # -- Replay protection ----------------------------------------------
        ts_header = headers.get("x-servicenow-timestamp") or headers.get("X-ServiceNow-Timestamp")
        if ts_header:
            try:
                ts = float(ts_header)
                age = abs(time.time() - ts)
                if age > self.WEBHOOK_REPLAY_WINDOW:
                    logger.warning(
                        "Webhook timestamp too old: %.0fs (limit %ds)",
                        age, self.WEBHOOK_REPLAY_WINDOW,
                    )
                    return False
            except (ValueError, TypeError):
                logger.warning("Invalid X-ServiceNow-Timestamp header: %s", ts_header)
                return False

        return True

    async def handle_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Optional[CanonicalTicket]:
        """Parse an inbound ServiceNow webhook into a CanonicalTicket.

        ServiceNow Business Rules / Flow Designer can POST the incident
        record as JSON.  Typical payload shapes:

        1. Direct record:  ``{ "sys_id": "…", "number": "INC…", … }``
        2. Wrapped record: ``{ "record": { … }, "sys_action": "update" }``

        The method detects both shapes, extracts the record, and converts
        it to a CanonicalTicket via ``sn_response_to_canonical()``.
        """
        # Detect payload shape
        if "record" in payload:
            record = payload["record"]
            action = payload.get("sys_action", "update")
        elif "sys_id" in payload:
            record = payload
            action = payload.get("sys_action", "update")
        else:
            logger.warning("Unrecognised webhook payload — no 'record' or 'sys_id' key")
            return None

        if not record:
            logger.warning("Empty record in webhook payload")
            return None

        try:
            canonical = sn_response_to_canonical(record)
        except Exception:
            logger.error("Failed to parse SN webhook record", exc_info=True)
            return None

        # Annotate with the SN action so downstream handlers can decide on event type
        canonical.custom_fields["sn_action"] = action
        canonical.custom_fields["sn_sys_id"] = record.get("sys_id", "")

        logger.info(
            "Parsed inbound webhook: action=%s sys_id=%s number=%s",
            action,
            canonical.external_id,
            canonical.external_number,
        )
        return canonical

    # ── Schema Discovery ──────────────────────────────────────────────────

    async def get_field_schema(self) -> Dict[str, Any]:
        return {
            "fields": [
                {"name": "short_description", "type": "string", "label": "Short Description", "required": True},
                {"name": "description", "type": "string", "label": "Description", "required": False},
                {"name": "state", "type": "integer", "label": "State", "choices": [1, 2, 3, 6, 7, 8]},
                {"name": "priority", "type": "integer", "label": "Priority", "choices": [1, 2, 3, 4, 5]},
                {"name": "category", "type": "string", "label": "Category"},
                {"name": "subcategory", "type": "string", "label": "Subcategory"},
                {"name": "caller_id", "type": "reference", "label": "Caller"},
                {"name": "assigned_to", "type": "reference", "label": "Assigned to"},
                {"name": "assignment_group", "type": "reference", "label": "Assignment group"},
                {"name": "location", "type": "string", "label": "Location"},
                {"name": "close_code", "type": "string", "label": "Close Code"},
                {"name": "close_notes", "type": "string", "label": "Close Notes"},
                {"name": "work_notes", "type": "journal", "label": "Work Notes"},
                {"name": "comments", "type": "journal", "label": "Additional Comments"},
            ]
        }
