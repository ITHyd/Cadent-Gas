"""ConnectorManager — lifecycle management for tenant connectors.

Orchestrates the full lifecycle: configure → store credentials → authenticate
→ test → activate → push/pull → health check → deactivate → delete.

This is the primary service that the rest of the application interacts with.
API endpoints and the incident service call ConnectorManager, not individual
connectors directly.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.models.connector import (
    ConnectorConfig,
    ConnectorType,
    AuthMethod,
    HealthStatus,
    CanonicalTicket,
    TicketComment,
    TicketAttachment,
)
from app.connectors.base_connector import (
    BaseConnector,
    ConnectorError,
    AuthenticationError,
)
from app.connectors.connector_registry import registry
from app.connectors.credential_vault import CredentialVault
from app.core.mongodb import get_database

logger = logging.getLogger(__name__)


class ConnectorManager:
    """Manages connector lifecycle for all tenants.

    Responsibilities:
    - Create/update/delete connector configurations
    - Authenticate connectors using Credential Vault
    - Maintain a pool of active connector instances
    - Route push/pull operations to the correct connector
    - Monitor connector health
    """

    def __init__(self, credential_vault: CredentialVault):
        self._vault = credential_vault
        # Active connector instances: config_id -> BaseConnector
        self._active_connectors: Dict[str, BaseConnector] = {}
        # Connector configs: config_id -> ConnectorConfig
        self._configs: Dict[str, ConnectorConfig] = {}
        # Tenant index: tenant_id -> [config_id, ...]
        self._tenant_configs: Dict[str, List[str]] = {}

    def _configs_col(self):
        db = get_database()
        return db.connector_configs if db is not None else None

    async def load_from_db(self) -> None:
        """Hydrate connector config cache from MongoDB."""
        col = self._configs_col()
        if col is None:
            return

        self._configs.clear()
        self._tenant_configs.clear()
        async for doc in col.find({}, {"_id": 0}):
            try:
                cfg = ConnectorConfig(**doc)
                self._configs[cfg.config_id] = cfg
                self._tenant_configs.setdefault(cfg.tenant_id, []).append(cfg.config_id)
            except Exception:
                logger.exception(
                    "Failed to parse connector config during hydration: config_id=%s",
                    doc.get("config_id"),
                )
        logger.info("Connector configs hydrated from MongoDB: %d", len(self._configs))

    async def hydrate_active_connectors(self) -> None:
        """Re-activate connectors marked active in DB when credentials are present."""
        for cfg in list(self._configs.values()):
            if not cfg.is_active:
                continue
            if not self._vault.has_credentials(cfg.config_id):
                logger.warning(
                    "Skipping active connector hydration; missing credentials: config=%s tenant=%s",
                    cfg.config_id,
                    cfg.tenant_id,
                )
                continue
            try:
                await self.activate(cfg.config_id, cfg.tenant_id)
            except Exception:
                logger.exception(
                    "Failed to hydrate active connector config=%s tenant=%s",
                    cfg.config_id,
                    cfg.tenant_id,
                )

    async def _persist_config(self, config: ConnectorConfig) -> None:
        col = self._configs_col()
        if col is None:
            return
        await col.update_one(
            {"config_id": config.config_id},
            {"$set": config.model_dump()},
            upsert=True,
        )

    # ── Configuration CRUD ───────────────────────────────────────────────

    async def create_config(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        display_name: str,
        instance_url: str,
        auth_method: AuthMethod = AuthMethod.OAUTH2,
        settings: Optional[Dict[str, Any]] = None,
    ) -> ConnectorConfig:
        """Create a new connector configuration for a tenant.

        The connector is NOT active until explicitly activated after testing.

        Args:
            tenant_id: Which tenant this connector belongs to.
            connector_type: ServiceNow, SAP, Jira, etc.
            display_name: Human-readable name.
            instance_url: External system URL.
            auth_method: How to authenticate.
            settings: Connector-specific settings dict.

        Returns:
            The created ConnectorConfig.

        Raises:
            ValueError: If connector type isn't registered or tenant already has one.
        """
        # Check if connector type is registered
        if not registry.is_registered(connector_type):
            raise ValueError(
                f"No connector implementation registered for '{connector_type.value}'. "
                f"Available: {[c['type'] for c in registry.list_available()]}"
            )

        # Check for duplicate (one connector per type per tenant)
        for existing_id in self._tenant_configs.get(tenant_id, []):
            existing = self._configs.get(existing_id)
            if existing and existing.connector_type == connector_type:
                raise ValueError(
                    f"Tenant '{tenant_id}' already has a {connector_type.value} connector "
                    f"(config_id={existing_id}). Update or delete it first."
                )

        config_id = f"CFG_{uuid.uuid4().hex[:12].upper()}"
        now = datetime.utcnow()

        config = ConnectorConfig(
            config_id=config_id,
            tenant_id=tenant_id,
            connector_type=connector_type,
            display_name=display_name,
            instance_url=instance_url,
            auth_method=auth_method,
            is_active=False,
            settings=settings or {},
            health_status=HealthStatus.UNKNOWN,
            created_at=now,
            updated_at=now,
        )

        self._configs[config_id] = config
        self._tenant_configs.setdefault(tenant_id, []).append(config_id)
        await self._persist_config(config)

        logger.info(
            f"Created connector config: {config_id} type={connector_type.value} "
            f"tenant={tenant_id}"
        )
        return config

    async def update_config(
        self, config_id: str, tenant_id: str, updates: Dict[str, Any]
    ) -> Optional[ConnectorConfig]:
        """Update a connector configuration.

        If the connector is active, it will be deactivated and must be
        re-tested and re-activated.
        """
        config = self._configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return None

        # Deactivate if currently active (config changed, needs re-test)
        if config.is_active:
            await self.deactivate(config_id, tenant_id)

        for key, value in updates.items():
            if hasattr(config, key) and key not in ("config_id", "tenant_id", "created_at"):
                setattr(config, key, value)

        config.updated_at = datetime.utcnow()
        await self._persist_config(config)
        logger.info(f"Updated config {config_id}: {list(updates.keys())}")
        return config

    async def delete_config(self, config_id: str, tenant_id: str) -> bool:
        """Delete a connector configuration and its credentials."""
        config = self._configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return False

        # Deactivate first
        if config.is_active:
            await self.deactivate(config_id, tenant_id)

        # Delete credentials
        await self._vault.delete_credentials(config_id, tenant_id)

        # Remove from stores
        del self._configs[config_id]
        tenant_list = self._tenant_configs.get(tenant_id, [])
        if config_id in tenant_list:
            tenant_list.remove(config_id)
        col = self._configs_col()
        if col is not None:
            await col.delete_one({"config_id": config_id})

        logger.info(f"Deleted connector config: {config_id} tenant={tenant_id}")
        return True

    def get_config(self, config_id: str) -> Optional[ConnectorConfig]:
        """Get a connector config by ID."""
        return self._configs.get(config_id)

    def get_tenant_configs(self, tenant_id: str) -> List[ConnectorConfig]:
        """Get all connector configs for a tenant."""
        config_ids = self._tenant_configs.get(tenant_id, [])
        return [self._configs[cid] for cid in config_ids if cid in self._configs]

    def get_tenant_connector_by_type(
        self, tenant_id: str, connector_type: ConnectorType
    ) -> Optional[ConnectorConfig]:
        """Get a tenant's connector config for a specific type."""
        for config in self.get_tenant_configs(tenant_id):
            if config.connector_type == connector_type:
                return config
        return None

    # ── Credential Management ────────────────────────────────────────────

    async def store_credentials(
        self,
        config_id: str,
        tenant_id: str,
        credentials: Dict[str, Any],
    ) -> str:
        """Store credentials for a connector config.

        Args:
            config_id: The connector config these credentials belong to.
            tenant_id: Tenant ID for isolation.
            credentials: Raw credential dict (will be encrypted).

        Returns:
            credential_id
        """
        config = self._configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            raise ValueError(f"Config {config_id} not found for tenant {tenant_id}")

        return await self._vault.store_credentials(
            config_id=config_id,
            tenant_id=tenant_id,
            auth_method=config.auth_method,
            credentials=credentials,
        )

    # ── Connector Lifecycle ──────────────────────────────────────────────

    async def test_connection(
        self, config_id: str, tenant_id: str
    ) -> Dict[str, Any]:
        """Test a connector's connection to the external system.

        Creates a temporary connector instance, authenticates it,
        and runs a test connection. Does NOT activate it.

        Returns:
            {"status": "ok"|"error", "message": "...", "latency_ms": N}
        """
        config = self._configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return {"status": "error", "message": "Config not found"}

        try:
            connector = self._create_connector_instance(config)

            # Get credentials
            creds = await self._vault.get_credentials(config_id, tenant_id)
            if not creds:
                return {"status": "error", "message": "No credentials stored for this connector"}

            # Authenticate
            await connector.authenticate(creds)

            # Test
            result = await connector.test_connection()
            return result

        except AuthenticationError as e:
            return {"status": "error", "message": f"Authentication failed: {e}"}
        except ConnectorError as e:
            return {"status": "error", "message": f"Connection failed: {e}"}
        except Exception as e:
            logger.exception(f"Test connection failed for config={config_id}")
            return {"status": "error", "message": f"Unexpected error: {e}"}

    async def activate(self, config_id: str, tenant_id: str) -> bool:
        """Activate a connector — makes it live for push/pull operations.

        Requires: credentials stored + test_connection passed.

        Returns:
            True if activated successfully.
        """
        config = self._configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return False

        if config.is_active:
            logger.info(f"Connector {config_id} is already active")
            if config_id in self._active_connectors:
                return True

        # Verify credentials exist
        if not self._vault.has_credentials(config_id):
            raise ValueError(
                f"Cannot activate connector {config_id}: no credentials stored. "
                "Store credentials first, then test, then activate."
            )

        try:
            connector = self._create_connector_instance(config)

            # Authenticate
            creds = await self._vault.get_credentials(config_id, tenant_id)
            await connector.authenticate(creds)

            # Store active instance
            self._active_connectors[config_id] = connector
            config.is_active = True
            config.health_status = HealthStatus.HEALTHY
            config.updated_at = datetime.utcnow()
            await self._persist_config(config)

            logger.info(f"Activated connector: {config_id} tenant={tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to activate connector {config_id}: {e}")
            config.health_status = HealthStatus.DOWN
            return False

    async def deactivate(self, config_id: str, tenant_id: str) -> bool:
        """Deactivate a connector — stops push/pull operations."""
        config = self._configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return False

        self._active_connectors.pop(config_id, None)
        config.is_active = False
        config.updated_at = datetime.utcnow()
        await self._persist_config(config)

        logger.info(f"Deactivated connector: {config_id} tenant={tenant_id}")
        return True

    def get_active_connector(
        self, tenant_id: str, connector_type: ConnectorType
    ) -> Optional[BaseConnector]:
        """Get the active connector instance for a tenant and type.

        This is the primary method used by the incident service to get
        the right connector for push/pull operations.
        """
        config = self.get_tenant_connector_by_type(tenant_id, connector_type)
        if not config or not config.is_active:
            return None
        return self._active_connectors.get(config.config_id)

    # ── Ticket Operations (delegated to active connector) ────────────────

    async def push_ticket(
        self, tenant_id: str, connector_type: ConnectorType, ticket: CanonicalTicket
    ) -> Dict[str, Any]:
        """Push a ticket to the external system via the tenant's active connector."""
        connector = self.get_active_connector(tenant_id, connector_type)
        if not connector:
            raise ConnectorError(
                f"No active {connector_type.value} connector for tenant {tenant_id}",
                connector_type=connector_type.value,
            )
        return await connector.push_ticket(ticket)

    async def pull_ticket(
        self, tenant_id: str, connector_type: ConnectorType, external_id: str
    ) -> Optional[CanonicalTicket]:
        """Pull a single ticket from the external system."""
        connector = self.get_active_connector(tenant_id, connector_type)
        if not connector:
            return None
        return await connector.pull_ticket(external_id)

    async def push_comment(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        external_id: str,
        comment: TicketComment,
    ) -> Dict[str, Any]:
        """Push a comment to a ticket in the external system."""
        connector = self.get_active_connector(tenant_id, connector_type)
        if not connector:
            raise ConnectorError(
                f"No active {connector_type.value} connector for tenant {tenant_id}",
                connector_type=connector_type.value,
            )
        return await connector.push_comment(external_id, comment)

    async def push_attachment(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        external_id: str,
        attachment: TicketAttachment,
        file_data: bytes,
    ) -> Dict[str, Any]:
        """Push an attachment to a ticket in the external system."""
        # Enforce 5MB limit
        max_bytes = 5 * 1024 * 1024
        if len(file_data) > max_bytes:
            raise ValueError(
                f"Attachment size ({len(file_data)} bytes) exceeds 5MB limit"
            )

        connector = self.get_active_connector(tenant_id, connector_type)
        if not connector:
            raise ConnectorError(
                f"No active {connector_type.value} connector for tenant {tenant_id}",
                connector_type=connector_type.value,
            )
        return await connector.push_attachment(external_id, attachment, file_data)

    # ── Webhook Handling ─────────────────────────────────────────────────

    async def handle_webhook(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Optional[CanonicalTicket]:
        """Route an inbound webhook to the correct connector for processing."""
        connector = self.get_active_connector(tenant_id, connector_type)
        if not connector:
            logger.warning(
                f"Webhook received for inactive connector: "
                f"tenant={tenant_id} type={connector_type.value}"
            )
            return None
        return await connector.handle_webhook(payload, headers)

    # ── Health Monitoring ────────────────────────────────────────────────

    async def health_check(self, config_id: str) -> HealthStatus:
        """Run a health check on an active connector."""
        connector = self._active_connectors.get(config_id)
        if not connector:
            return HealthStatus.UNKNOWN

        config = self._configs.get(config_id)
        try:
            status = await connector.health_check()
            if config:
                config.health_status = status
                config.last_health_check_at = datetime.utcnow()
                await self._persist_config(config)
            return status
        except Exception as e:
            logger.error(f"Health check failed for {config_id}: {e}")
            if config:
                config.health_status = HealthStatus.DOWN
                config.last_health_check_at = datetime.utcnow()
                await self._persist_config(config)
            return HealthStatus.DOWN

    async def health_check_all(self) -> Dict[str, HealthStatus]:
        """Run health checks on all active connectors."""
        results = {}
        for config_id in list(self._active_connectors.keys()):
            results[config_id] = await self.health_check(config_id)
        return results

    # ── Internal ─────────────────────────────────────────────────────────

    def _create_connector_instance(self, config: ConnectorConfig) -> BaseConnector:
        """Create a connector instance from config using the registry."""
        return registry.create(config)

    # ── Info ─────────────────────────────────────────────────────────────

    def list_available_connectors(self) -> List[Dict[str, str]]:
        """List all registered connector types."""
        return registry.list_available()

    def get_status_summary(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Get status summary of all connectors for a tenant."""
        configs = self.get_tenant_configs(tenant_id)
        return [
            {
                "config_id": c.config_id,
                "connector_type": c.connector_type.value,
                "display_name": c.display_name,
                "is_active": c.is_active,
                "health_status": c.health_status.value,
                "instance_url": c.instance_url,
                "last_health_check_at": c.last_health_check_at.isoformat() if c.last_health_check_at else None,
                "last_successful_sync_at": c.last_successful_sync_at.isoformat() if c.last_successful_sync_at else None,
                "auth_method": c.auth_method.value,
                "settings": c.settings,
                "has_credentials": self._vault.has_credentials(c.config_id),
            }
            for c in configs
        ]
