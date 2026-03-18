"""SAPConnector — concrete implementation of BaseConnector for SAP Service Cloud.

Implements all 12 abstract methods. Delegates HTTP calls to SAPClient
and data transformation to sap_transformer.
"""
import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.connectors.base_connector import BaseConnector, ConnectorError
from app.connectors.implementations.sap.sap_client import SAPClient
from app.connectors.implementations.sap.sap_transformer import (
    canonical_to_sap_payload,
    sap_response_to_canonical,
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


class SAPConnector(BaseConnector):
    """SAP connector — pushes/pulls service order data via the SAP OData API."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        api_path = config.settings.get(
            "api_path", "/sap/opu/odata/sap/API_SERVICE_ORDER_SRV"
        )
        self._client = SAPClient(
            instance_url=config.instance_url,
            auth_method=config.auth_method,
            api_path=api_path,
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
        """Create or update a SAP service order from a CanonicalTicket."""
        sap_payload = canonical_to_sap_payload(ticket, tenant_id=self.config.tenant_id)

        # Extract platform notes before sending to SAP
        platform_notes = sap_payload.pop("_platform_notes", None)

        if ticket.external_id:
            record = await self._client.update_service_order(ticket.external_id, sap_payload)
            action = "updated"
        else:
            record = await self._client.create_service_order(sap_payload)
            action = "created"

        order_id = record.get("ServiceOrderID", "")
        external_url = f"{self.instance_url}/sap/bc/ui5_ui5/ui2/ushell/shells/abap/FioriLaunchpad.html#ServiceOrder-displayFactSheet?ServiceOrder={order_id}"

        # Push platform context as a text entry if this is a new order
        if action == "created" and platform_notes and order_id:
            try:
                await self._client.add_text(order_id, platform_notes, "S001")
            except Exception:
                logger.warning("Failed to add platform notes to SAP order %s", order_id)

        logger.info(
            "push_ticket %s: %s (order_id=%s)",
            action, ticket.ticket_id, order_id,
        )

        return {
            "external_id": order_id,
            "external_number": f"SO-{order_id}" if order_id else "",
            "external_url": external_url,
            "action": action,
        }

    async def pull_ticket(self, external_id: str) -> Optional[CanonicalTicket]:
        try:
            sap_data = await self._client.get_service_order(external_id)
            if not sap_data:
                return None
            return sap_response_to_canonical(sap_data, tenant_id=self.config.tenant_id)
        except ConnectorError:
            logger.warning("Failed to pull SAP ticket %s", external_id, exc_info=True)
            return None

    async def pull_tickets(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalTicket]:
        filter_parts = []
        if filters:
            for key, value in filters.items():
                filter_parts.append(f"{key} eq '{value}'")
        filter_str = " and ".join(filter_parts) if filter_parts else ""

        records = await self._client.query_service_orders(filter_str, limit, offset)
        tickets = []
        for rec in records:
            try:
                tickets.append(sap_response_to_canonical(rec, tenant_id=self.config.tenant_id))
            except Exception:
                logger.warning(
                    "Failed to parse SAP record: %s",
                    rec.get("ServiceOrderID"),
                    exc_info=True,
                )
        return tickets

    # ── Comment Operations ────────────────────────────────────────────────

    async def push_comment(
        self, external_id: str, comment: TicketComment
    ) -> Dict[str, Any]:
        prefix = f"[{comment.author_name or comment.author_id or 'Platform'}] "
        text_type = "S001" if comment.is_public else "S002"
        await self._client.add_text(external_id, prefix + comment.body, text_type)
        return {"external_comment_id": None, "status": "created"}

    async def pull_comments(self, external_id: str) -> List[TicketComment]:
        records = await self._client.get_texts(external_id)
        comments = []
        for rec in records:
            comments.append(
                TicketComment(
                    comment_id=rec.get("TextObjectKey", ""),
                    body=rec.get("LongText", ""),
                    is_public=rec.get("LongTextID") == "S001",
                    source_system="sap",
                    created_at=datetime.utcnow(),
                )
            )
        return comments

    # ── Attachment Operations ─────────────────────────────────────────────

    async def push_attachment(
        self, external_id: str, attachment: TicketAttachment, file_data: bytes
    ) -> Dict[str, Any]:
        record = await self._client.add_attachment(
            order_id=external_id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            file_data=file_data,
        )
        return {
            "external_attachment_id": record.get("DocumentInfoRecordDocNumber"),
            "status": "uploaded",
        }

    async def pull_attachments(self, external_id: str) -> List[TicketAttachment]:
        records = await self._client.get_attachments(external_id)
        attachments = []
        for rec in records:
            attachments.append(
                TicketAttachment(
                    attachment_id=rec.get("DocumentInfoRecordDocNumber", ""),
                    filename=rec.get("FileName", "unknown"),
                    content_type=rec.get("MimeType", "application/octet-stream"),
                    size_bytes=int(rec.get("FileSize", 0)),
                    source_system="sap",
                    external_attachment_id=rec.get("DocumentInfoRecordDocNumber"),
                    uploaded_at=datetime.utcnow(),
                )
            )
        return attachments

    # ── Webhook Handling ──────────────────────────────────────────────────

    WEBHOOK_REPLAY_WINDOW = 300  # 5 minutes

    async def verify_webhook_signature(
        self, payload: bytes, headers: Dict[str, str]
    ) -> bool:
        """Verify HMAC-SHA256 signature from a SAP webhook.

        Expected headers:
            X-SAP-Signature  — hex-encoded HMAC-SHA256 digest
            X-SAP-Timestamp  — Unix epoch seconds (replay protection)
        """
        secret = self.config.settings.get("webhook_secret")
        if not secret:
            logger.warning("No webhook_secret configured for SAP connector %s", self.config.config_id)
            return False

        signature = headers.get("x-sap-signature") or headers.get("X-SAP-Signature")
        if not signature:
            logger.warning("Missing X-SAP-Signature header")
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning("SAP webhook signature mismatch")
            return False

        # Replay protection
        ts_header = headers.get("x-sap-timestamp") or headers.get("X-SAP-Timestamp")
        if ts_header:
            try:
                ts = float(ts_header)
                age = abs(time.time() - ts)
                if age > self.WEBHOOK_REPLAY_WINDOW:
                    logger.warning("SAP webhook timestamp too old: %.0fs", age)
                    return False
            except (ValueError, TypeError):
                logger.warning("Invalid X-SAP-Timestamp header: %s", ts_header)
                return False

        return True

    async def handle_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Optional[CanonicalTicket]:
        """Parse an inbound SAP webhook into a CanonicalTicket.

        SAP payload shapes:
        1. OData wrapped: {"d": {"ServiceOrderID": "...", ...}}
        2. Event Mesh:    {"event": "update", "record": {...}}
        3. Direct:        {"ServiceOrderID": "...", ...}
        """
        if "d" in payload and isinstance(payload["d"], dict):
            record = payload["d"]
            action = "update"
        elif "record" in payload:
            record = payload["record"]
            action = payload.get("event", "update")
        elif "ServiceOrderID" in payload:
            record = payload
            action = payload.get("event", "update")
        else:
            logger.warning("Unrecognised SAP webhook payload — no actionable data")
            return None

        if not record:
            logger.warning("Empty record in SAP webhook payload")
            return None

        try:
            canonical = sap_response_to_canonical(record, tenant_id=self.config.tenant_id)
        except Exception:
            logger.error("Failed to parse SAP webhook record", exc_info=True)
            return None

        canonical.custom_fields["sap_action"] = action
        canonical.custom_fields["sap_order_id"] = record.get("ServiceOrderID", "")

        logger.info(
            "Parsed SAP inbound webhook: action=%s order_id=%s",
            action,
            canonical.external_id,
        )
        return canonical

    # ── Schema Discovery ──────────────────────────────────────────────────

    async def get_field_schema(self) -> Dict[str, Any]:
        return {
            "fields": [
                {"name": "ServiceOrderDescription", "type": "string", "label": "Description", "required": True},
                {"name": "LongText", "type": "string", "label": "Long Text", "required": False},
                {"name": "ServiceOrderStatusCode", "type": "string", "label": "Status", "choices": ["E0001", "E0002", "E0003", "E0004", "E0005", "E0006"]},
                {"name": "ServiceOrderPriorityCode", "type": "string", "label": "Priority", "choices": ["1", "2", "3", "4"]},
                {"name": "ServiceOrderCategoryCode", "type": "string", "label": "Category"},
                {"name": "ReportedByParty", "type": "string", "label": "Reported By"},
                {"name": "ResponsibleEmployee", "type": "string", "label": "Responsible Employee"},
                {"name": "ServiceTeam", "type": "string", "label": "Service Team"},
                {"name": "InstallationPointAddress", "type": "string", "label": "Address"},
                {"name": "ResolutionCode", "type": "string", "label": "Resolution Code"},
                {"name": "ResolutionDescription", "type": "string", "label": "Resolution Notes"},
            ]
        }
