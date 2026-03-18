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
