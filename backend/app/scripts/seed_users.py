"""Seed dummy users into MongoDB for development/testing."""
import asyncio
import logging
import os
from datetime import datetime

import bcrypt
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Admin credentials — read from env vars; fall back to defaults ONLY in dev
_SEED_ADMIN_PW = os.environ.get("SEED_ADMIN_PASSWORD", "Adm!n@Gas2025#")
_SEED_ANDREW_PW = os.environ.get("SEED_ANDREW_PASSWORD", "Andrew@Gas2025#")
_SEED_SUPER_PW = os.environ.get("SEED_SUPER_PASSWORD", "Sup3r@Platform2025#")
_SEED_PLATADMIN_PW = os.environ.get("SEED_PLATADMIN_PASSWORD", "PlatAdm@Gas2025#")

ADMIN_CREDENTIALS = [
    {"user_id": "company_001", "username": "admin", "password": _SEED_ADMIN_PW},
    {"user_id": "company_002", "username": "andrew", "password": _SEED_ANDREW_PW},
    {"user_id": "super_001", "username": "super", "password": _SEED_SUPER_PW},
    {"user_id": "super_002", "username": "platform_admin", "password": _SEED_PLATADMIN_PW},
]

# NOTE: password fields use plain text here; hashing happens lazily in seed_users()
DUMMY_USERS = [
    # Cadent demo tenant — users
    {"user_id": "user_001", "phone": "+447700900101", "full_name": "James Wilson", "role": "user", "tenant_id": "tenant_demo", "address": "14 Elm Street, Westminster, London SW1A 1AA", "location": "Westminster, London"},
    {"user_id": "user_002", "phone": "+447700900102", "full_name": "Emily Davies", "role": "user", "tenant_id": "tenant_demo", "address": "27 Oak Avenue, Deansgate, Manchester M3 4LQ", "location": "Deansgate, Manchester"},
    {"user_id": "user_003", "phone": "+447700900103", "full_name": "Oliver Thompson", "role": "user", "tenant_id": "tenant_demo", "address": "9 Birch Lane, Headingley, Leeds LS6 3BR", "location": "Headingley, Leeds"},
    {"user_id": "user_004", "phone": "+447700900104", "full_name": "Charlotte Evans", "role": "user", "tenant_id": "tenant_demo", "address": "52 Maple Road, Clifton, Bristol BS8 1AB", "location": "Clifton, Bristol"},
    {"user_id": "user_005", "phone": "+447700900105", "full_name": "William Harris", "role": "user", "tenant_id": "tenant_demo", "address": "3 Pine Close, Canary Wharf, London E14 5HP", "location": "Canary Wharf, London"},
    # Cadent demo tenant — agents
    {"user_id": "agent_001", "phone": "+447700900201", "full_name": "John Smith", "role": "agent", "tenant_id": "tenant_demo"},
    {"user_id": "agent_002", "phone": "+447700900202", "full_name": "David Mitchell", "role": "agent", "tenant_id": "tenant_demo"},
    {"user_id": "agent_003", "phone": "+447700900203", "full_name": "Robert Taylor", "role": "agent", "tenant_id": "tenant_demo"},
    {"user_id": "agent_004", "phone": "+447700900204", "full_name": "Thomas Brown", "role": "agent", "tenant_id": "tenant_demo"},
    {"user_id": "agent_005", "phone": "+447700900205", "full_name": "Daniel Wright", "role": "agent", "tenant_id": "tenant_demo"},
    # Cadent demo tenant — company admins
    {"user_id": "company_001", "phone": "+447700900301", "full_name": "Sarah Morgan", "role": "company", "tenant_id": "tenant_demo", "username": "admin", "_plain_password": _SEED_ADMIN_PW},
    {"user_id": "company_002", "phone": "+447700900302", "full_name": "Andrew Campbell", "role": "company", "tenant_id": "tenant_demo", "username": "andrew", "_plain_password": _SEED_ANDREW_PW, "admin_group_id": "grp_sn_team"},
    # Cadent demo tenant — super users
    {"user_id": "super_001", "phone": "+447700900401", "full_name": "Admin", "role": "super_user", "tenant_id": "tenant_demo", "username": "super", "_plain_password": _SEED_SUPER_PW},
    {"user_id": "super_002", "phone": "+447700900402", "full_name": "Platform Admin", "role": "super_user", "tenant_id": "tenant_demo", "username": "platform_admin", "_plain_password": _SEED_PLATADMIN_PW},
]


async def _migrate_admin_credentials(db):
    """Add username/password_hash to existing admin users that lack them."""
    updated = 0
    for cred in ADMIN_CREDENTIALS:
        result = await db.users.update_one(
            {"user_id": cred["user_id"], "username": {"$exists": False}},
            {"$set": {
                "username": cred["username"],
                "password_hash": _hash_password(cred["password"]),
            }},
        )
        if result.modified_count:
            updated += 1

    # Ensure sparse unique index on username
    await db.users.create_index("username", unique=True, sparse=True)

    if updated:
        logger.info("Migrated %d admin users with username/password credentials", updated)


async def seed_users(db):
    """Seed dummy users into MongoDB.

    This is incremental: existing users are preserved, and missing default users
    are inserted. This allows adding new demo tenants in later phases without
    clearing the database.

    Set SKIP_SEED=true in production to disable seeding entirely.
    """
    if os.environ.get("SKIP_SEED", "").lower() in ("1", "true", "yes"):
        logger.info("SKIP_SEED is set — skipping user seed")
        return

    await db.users.create_index("username", unique=True, sparse=True)

    now = datetime.utcnow()
    inserted = 0
    patched = 0

    for user in DUMMY_USERS:
        existing = await db.users.find_one({"user_id": user["user_id"]})

        if existing:
            # Backfill admin credentials and admin_group_id for seeded users
            updates = {}
            if user.get("username") and not existing.get("username"):
                updates["username"] = user["username"]
            # Always re-hash seed passwords so rotated credentials take effect
            if user.get("_plain_password"):
                updates["password_hash"] = _hash_password(user["_plain_password"])
            if user.get("admin_group_id") and not existing.get("admin_group_id"):
                updates["admin_group_id"] = user["admin_group_id"]
            if user.get("address") and not existing.get("address"):
                updates["address"] = user["address"]
            if user.get("location") and not existing.get("location"):
                updates["location"] = user["location"]

            if updates:
                updates["updated_at"] = now
                await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
                patched += 1
            continue

        # Guard against unique phone collisions when user_id is new.
        phone_conflict = await db.users.find_one({"phone": user["phone"]}, {"user_id": 1, "_id": 0})
        if phone_conflict:
            logger.warning(
                "Skipping seed user %s due to phone collision with existing user_id=%s",
                user["user_id"],
                phone_conflict.get("user_id"),
            )
            continue

        doc = {
            "user_id": user["user_id"],
            "phone": user["phone"],
            "full_name": user["full_name"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_login": None,
        }
        if user.get("username"):
            doc["username"] = user["username"]
        if user.get("_plain_password"):
            doc["password_hash"] = _hash_password(user["_plain_password"])
        if user.get("admin_group_id"):
            doc["admin_group_id"] = user["admin_group_id"]
        if user.get("address"):
            doc["address"] = user["address"]
        if user.get("location"):
            doc["location"] = user["location"]

        try:
            await db.users.insert_one(doc)
            inserted += 1
        except DuplicateKeyError:
            logger.warning(
                "Skipping seed user %s because it already exists under a unique constraint",
                user["user_id"],
            )
            continue

    await _migrate_admin_credentials(db)

    # Remove users that were previously seeded but are no longer in DUMMY_USERS
    current_ids = {u["user_id"] for u in DUMMY_USERS}
    obsolete_ids = ["city_user_001", "city_user_002", "city_user_003", "city_agent_001", "city_agent_002", "company_003", "company_004", "user_006", "user_007", "user_008"]
    removed = 0
    for uid in obsolete_ids:
        if uid not in current_ids:
            result = await db.users.delete_one({"user_id": uid})
            if result.deleted_count:
                removed += 1
                logger.info("Removed obsolete seed user: %s", uid)
    if removed:
        logger.info("Cleaned up %d obsolete seed users", removed)

    total = await db.users.count_documents({})
    logger.info(
        "User seed complete: inserted=%d patched=%d total_users=%d",
        inserted,
        patched,
        total,
    )


async def main():
    """Standalone execution: connect to MongoDB and seed."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.core.config import settings

    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]
    await seed_users(db)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
