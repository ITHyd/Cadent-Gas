"""ServiceNow connector implementation — auto-registers on import."""
from app.connectors.implementations.servicenow.sn_connector import ServiceNowConnector
from app.connectors.connector_registry import registry
from app.models.connector import ConnectorType

# Auto-register when this package is imported
registry.register(ConnectorType.SERVICENOW, ServiceNowConnector)
