"""ConnectorRegistry — discovers and instantiates connector implementations.

The registry is a singleton that maps ConnectorType -> connector class.
Connector implementations register themselves at import time.

Usage:
    registry = ConnectorRegistry()
    registry.register(ConnectorType.SERVICENOW, ServiceNowConnector)

    connector = registry.create(ConnectorType.SERVICENOW, config)
"""
import logging
from typing import Dict, Type, List, Optional

from app.models.connector import ConnectorType, ConnectorConfig
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Singleton registry mapping ConnectorType to implementation classes."""

    _instance: Optional["ConnectorRegistry"] = None
    _connectors: Dict[ConnectorType, Type[BaseConnector]] = {}

    def __new__(cls) -> "ConnectorRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(
        self, connector_type: ConnectorType, connector_class: Type[BaseConnector]
    ) -> None:
        """Register a connector implementation.

        Args:
            connector_type: The type key (e.g., ConnectorType.SERVICENOW).
            connector_class: The class that extends BaseConnector.

        Raises:
            ValueError: If connector_class doesn't extend BaseConnector.
        """
        if not issubclass(connector_class, BaseConnector):
            raise ValueError(
                f"{connector_class.__name__} must extend BaseConnector"
            )

        if connector_type in self._connectors:
            logger.warning(
                f"Overwriting existing connector for {connector_type.value}: "
                f"{self._connectors[connector_type].__name__} -> {connector_class.__name__}"
            )

        self._connectors[connector_type] = connector_class
        logger.info(
            f"Registered connector: {connector_type.value} -> {connector_class.__name__}"
        )

    def create(self, config: ConnectorConfig) -> BaseConnector:
        """Create a connector instance from a config.

        Args:
            config: The ConnectorConfig with type, tenant, URL, etc.

        Returns:
            An instantiated connector (not yet authenticated).

        Raises:
            ValueError: If no connector is registered for this type.
        """
        connector_class = self._connectors.get(config.connector_type)
        if not connector_class:
            available = ", ".join(ct.value for ct in self._connectors.keys())
            raise ValueError(
                f"No connector registered for type '{config.connector_type.value}'. "
                f"Available: [{available}]"
            )

        connector = connector_class(config)
        logger.info(
            f"Created connector instance: {connector_class.__name__} "
            f"for tenant={config.tenant_id}"
        )
        return connector

    def get_class(
        self, connector_type: ConnectorType
    ) -> Optional[Type[BaseConnector]]:
        """Get the registered class for a connector type (without instantiating)."""
        return self._connectors.get(connector_type)

    def list_available(self) -> List[Dict[str, str]]:
        """List all registered connector types.

        Returns:
            [{"type": "servicenow", "class": "ServiceNowConnector"}, ...]
        """
        return [
            {
                "type": ct.value,
                "class": cls.__name__,
            }
            for ct, cls in self._connectors.items()
        ]

    def is_registered(self, connector_type: ConnectorType) -> bool:
        """Check if a connector type has a registered implementation."""
        return connector_type in self._connectors

    def unregister(self, connector_type: ConnectorType) -> bool:
        """Remove a connector registration. Returns True if it existed."""
        if connector_type in self._connectors:
            removed = self._connectors.pop(connector_type)
            logger.info(f"Unregistered connector: {connector_type.value} ({removed.__name__})")
            return True
        return False

    def clear(self) -> None:
        """Remove all registrations. Used in tests."""
        self._connectors.clear()


# Module-level singleton
registry = ConnectorRegistry()
