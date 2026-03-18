"""BaseConnector — abstract interface that every connector must implement.

All connectors (ServiceNow, SAP, Jira) extend this class and implement
the abstract methods. The ConnectorManager calls these methods; the connector
handles the external system specifics.

Data flow through a connector:
    Outbound: CanonicalTicket → connector.push_ticket() → External API
    Inbound:  External Webhook → connector.handle_webhook() → CanonicalTicket
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from app.models.connector import (
    CanonicalTicket,
    TicketComment,
    TicketAttachment,
    ConnectorConfig,
    ConnectorType,
    HealthStatus,
)

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Base exception for all connector errors."""

    def __init__(self, message: str, connector_type: str = "", retriable: bool = False):
        self.connector_type = connector_type
        self.retriable = retriable
        super().__init__(message)


class AuthenticationError(ConnectorError):
    """Raised when connector fails to authenticate with external system."""

    def __init__(self, message: str, connector_type: str = ""):
        super().__init__(message, connector_type, retriable=True)


class RateLimitError(ConnectorError):
    """Raised when external system rate-limits the connector."""

    def __init__(self, message: str, connector_type: str = "", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message, connector_type, retriable=True)


class BaseConnector(ABC):
    """Abstract base class for all external system connectors.

    Every connector implementation must:
    1. Accept a ConnectorConfig in __init__
    2. Implement all abstract methods below
    3. Register itself in the ConnectorRegistry

    Connectors are stateless per-call — they read config/credentials
    at init time and make API calls per method invocation.
    """

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.connector_type: ConnectorType = config.connector_type
        self.tenant_id: str = config.tenant_id
        self.instance_url: str = config.instance_url
        self._is_authenticated: bool = False

    # ── Connection Lifecycle ─────────────────────────────────────────────

    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """Establish authenticated session with the external system.

        Args:
            credentials: Decrypted credential dict (client_id, client_secret, etc.)

        Returns:
            True if authentication succeeded.

        Raises:
            AuthenticationError: If authentication fails.
        """
        ...

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """Verify the connector can reach and authenticate with the external system.

        Returns:
            {
                "status": "ok" | "error",
                "message": "Connection successful" | error details,
                "latency_ms": round-trip time,
                "external_version": system version string (if available),
            }
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Quick health probe. Called periodically by ConnectorManager.

        Returns:
            HealthStatus enum value.
        """
        ...

    # ── Ticket Operations ────────────────────────────────────────────────

    @abstractmethod
    async def push_ticket(self, ticket: CanonicalTicket) -> Dict[str, Any]:
        """Create or update a ticket in the external system.

        If ticket.external_id is set, update the existing ticket.
        If ticket.external_id is None, create a new ticket.

        Args:
            ticket: The canonical ticket to push.

        Returns:
            {
                "external_id": "sys_id_abc123",      # External system's ID
                "external_number": "INC0010001",      # Human-readable number
                "external_url": "https://...",         # Deep link
                "action": "created" | "updated",
            }

        Raises:
            ConnectorError: On failure.
        """
        ...

    @abstractmethod
    async def pull_ticket(self, external_id: str) -> Optional[CanonicalTicket]:
        """Fetch a single ticket from the external system by its ID.

        Args:
            external_id: The external system's ticket ID (e.g., SN sys_id).

        Returns:
            CanonicalTicket if found, None if not.
        """
        ...

    @abstractmethod
    async def pull_tickets(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalTicket]:
        """Fetch multiple tickets from the external system.

        Args:
            filters: System-specific query filters.
            limit: Max tickets to return.
            offset: Pagination offset.

        Returns:
            List of CanonicalTicket objects.
        """
        ...

    # ── Comment Operations ───────────────────────────────────────────────

    @abstractmethod
    async def push_comment(
        self, external_id: str, comment: TicketComment
    ) -> Dict[str, Any]:
        """Add a comment to a ticket in the external system.

        Args:
            external_id: The external ticket ID.
            comment: The comment to push.

        Returns:
            {"external_comment_id": "...", "status": "created"}
        """
        ...

    @abstractmethod
    async def pull_comments(self, external_id: str) -> List[TicketComment]:
        """Fetch all comments for a ticket from the external system.

        Args:
            external_id: The external ticket ID.

        Returns:
            List of TicketComment objects.
        """
        ...

    # ── Attachment Operations ────────────────────────────────────────────

    @abstractmethod
    async def push_attachment(
        self, external_id: str, attachment: TicketAttachment, file_data: bytes
    ) -> Dict[str, Any]:
        """Upload an attachment to a ticket in the external system.

        Args:
            external_id: The external ticket ID.
            attachment: Attachment metadata.
            file_data: Raw file bytes (<=5MB enforced by caller).

        Returns:
            {"external_attachment_id": "...", "status": "uploaded"}
        """
        ...

    @abstractmethod
    async def pull_attachments(self, external_id: str) -> List[TicketAttachment]:
        """List attachments for a ticket in the external system.

        Args:
            external_id: The external ticket ID.

        Returns:
            List of TicketAttachment metadata (file_data fetched separately).
        """
        ...

    # ── Webhook Handling ─────────────────────────────────────────────────

    @abstractmethod
    async def handle_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Optional[CanonicalTicket]:
        """Parse an inbound webhook from the external system.

        Validates the webhook signature, extracts the ticket data,
        and converts it to a CanonicalTicket.

        Args:
            payload: Raw webhook body (parsed JSON).
            headers: HTTP headers (for signature verification).

        Returns:
            CanonicalTicket extracted from the webhook, or None if invalid/ignored.

        Raises:
            ConnectorError: If signature verification fails.
        """
        ...

    @abstractmethod
    async def verify_webhook_signature(
        self, payload: bytes, headers: Dict[str, str]
    ) -> bool:
        """Verify the HMAC signature of an inbound webhook.

        Args:
            payload: Raw request body bytes.
            headers: HTTP headers containing the signature.

        Returns:
            True if signature is valid.
        """
        ...

    # ── Schema Discovery ─────────────────────────────────────────────────

    @abstractmethod
    async def get_field_schema(self) -> Dict[str, Any]:
        """Discover available fields in the external system's ticket model.

        Used by the Field Mapping UI to let admins configure mappings.

        Returns:
            {
                "fields": [
                    {"name": "short_description", "type": "string", "label": "Short Description", "required": True},
                    {"name": "priority", "type": "integer", "label": "Priority", "choices": [1,2,3,4,5]},
                    ...
                ]
            }
        """
        ...

    # ── Utility ──────────────────────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"type={self.connector_type.value} "
            f"tenant={self.tenant_id} "
            f"url={self.instance_url} "
            f"auth={self._is_authenticated}>"
        )
