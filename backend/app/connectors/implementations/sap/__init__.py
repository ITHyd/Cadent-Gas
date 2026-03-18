"""SAP connector implementation — auto-registers on import."""
from app.connectors.implementations.sap.sap_connector import SAPConnector
from app.connectors.connector_registry import registry
from app.models.connector import ConnectorType

registry.register(ConnectorType.SAP, SAPConnector)
