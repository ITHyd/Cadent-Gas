"""MongoDB connection management using motor (async driver)."""
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    client: AsyncIOMotorClient = None
    db = None


mongodb = MongoDB()


async def connect_to_mongo():
    """Initialize MongoDB connection on app startup."""
    logger.info("Connecting to MongoDB...")
    mongodb.client = AsyncIOMotorClient(settings.MONGODB_URI)
    mongodb.db = mongodb.client[settings.MONGODB_DB_NAME]

    # TTL index: OTP codes auto-delete after 5 minutes
    await mongodb.db.otp_codes.create_index("created_at", expireAfterSeconds=300)
    # Unique index on phone number
    await mongodb.db.users.create_index("phone", unique=True)
    # Index on tenant_id for multi-tenant queries
    await mongodb.db.users.create_index("tenant_id")

    # Tenant collection indexes
    await mongodb.db.tenants.create_index("tenant_id", unique=True)
    await mongodb.db.tenants.create_index("branding.subdomain", unique=True, sparse=True)
    await mongodb.db.tenants.create_index("status")

    # Incidents
    await mongodb.db.incidents.create_index("incident_id", unique=True)
    await mongodb.db.incidents.create_index([("tenant_id", 1), ("created_at", -1)])
    await mongodb.db.incidents.create_index([("user_id", 1), ("created_at", -1)])
    await mongodb.db.incidents.create_index([("status", 1), ("created_at", -1)])
    await mongodb.db.incidents.create_index("reference_id", sparse=True)

    # Workflow definitions (one document per version)
    await mongodb.db.workflow_definitions.create_index(
        [("workflow_id", 1), ("version", 1)],
        unique=True,
    )
    await mongodb.db.workflow_definitions.create_index([("tenant_id", 1), ("use_case", 1)])
    await mongodb.db.workflow_definitions.create_index([("workflow_id", 1), ("is_active", 1)])

    # Agent sessions / live chat state
    await mongodb.db.agent_sessions.create_index("session_id", unique=True)
    await mongodb.db.agent_sessions.create_index([("incident_id", 1), ("updated_at", -1)])
    await mongodb.db.agent_sessions.create_index([("user_id", 1), ("updated_at", -1)])

    # User notifications
    await mongodb.db.user_notifications.create_index("notification_id", unique=True)
    await mongodb.db.user_notifications.create_index([("user_id", 1), ("created_at", -1)])
    await mongodb.db.user_notifications.create_index([("user_id", 1), ("read", 1), ("created_at", -1)])

    # Agents
    await mongodb.db.agents.create_index("agent_id", unique=True)
    await mongodb.db.agents.create_index([("is_available", 1), ("location_area", 1)])

    # Connector collections
    await mongodb.db.connector_configs.create_index(
        [("tenant_id", 1), ("connector_type", 1)],
        unique=True,
    )
    await mongodb.db.connector_configs.create_index("config_id", unique=True)
    await mongodb.db.connector_credentials.create_index("config_id", unique=True)
    await mongodb.db.connector_credentials.create_index("tenant_id")

    # Sync events
    await mongodb.db.sync_events.create_index([("tenant_id", 1), ("created_at", -1)])
    await mongodb.db.sync_events.create_index("idempotency_key", unique=True)
    await mongodb.db.sync_events.create_index("status")
    await mongodb.db.sync_events.create_index("event_id", unique=True)

    # Field mappings
    await mongodb.db.field_mappings.create_index(
        [("tenant_id", 1), ("connector_type", 1), ("version", 1)],
        unique=True,
    )
    await mongodb.db.field_mappings.create_index(
        [("tenant_id", 1), ("connector_type", 1), ("is_active", 1)],
    )
    await mongodb.db.field_mappings.create_index("mapping_id", unique=True)

    # Admin audit logs
    await mongodb.db.admin_audit_logs.create_index([("tenant_id", 1), ("created_at", -1)])
    await mongodb.db.admin_audit_logs.create_index([("actor_user_id", 1), ("created_at", -1)])

    logger.info("Connected to MongoDB successfully")


async def close_mongo_connection():
    """Close MongoDB connection on app shutdown."""
    if mongodb.client:
        mongodb.client.close()
        logger.info("MongoDB connection closed")


def get_database():
    """Get database instance."""
    return mongodb.db
