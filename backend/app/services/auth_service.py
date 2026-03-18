"""Authentication service — OTP generation/verification, JWT management, user lookup."""
import secrets
import string
import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError
from app.core.config import settings
from app.core.mongodb import get_database

logger = logging.getLogger(__name__)


class AuthService:

    @staticmethod
    def hash_password(plain_password: str) -> str:
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    @staticmethod
    async def find_user_by_phone(phone: str) -> Optional[dict]:
        db = get_database()
        return await db.users.find_one({"phone": phone})

    @staticmethod
    async def find_user_by_id(user_id: str) -> Optional[dict]:
        db = get_database()
        return await db.users.find_one({"user_id": user_id})

    @staticmethod
    async def find_user_by_username(username: str) -> Optional[dict]:
        db = get_database()
        return await db.users.find_one({"username": username})

    @staticmethod
    async def generate_and_store_otp(phone: str) -> str:
        """Generate 6-digit OTP and store in MongoDB (upsert, 5-min TTL)."""
        db = get_database()
        otp = "".join(secrets.choice(string.digits) for _ in range(6))

        await db.otp_codes.update_one(
            {"phone": phone},
            {"$set": {
                "phone": phone,
                "otp": otp,
                "created_at": datetime.utcnow(),
                "attempts": 0,
            }},
            upsert=True,
        )
        logger.info("OTP generated for phone ending %s", phone[-4:])
        return otp

    @staticmethod
    async def verify_otp(phone: str, otp: str) -> bool:
        """Validate OTP — max 5 attempts, 5-min expiry, single-use."""
        db = get_database()
        record = await db.otp_codes.find_one({"phone": phone})

        if not record:
            return False

        # Brute-force protection
        if record.get("attempts", 0) >= 5:
            return False

        await db.otp_codes.update_one(
            {"phone": phone},
            {"$inc": {"attempts": 1}},
        )

        if record["otp"] != otp:
            return False

        # Belt-and-suspenders expiry check (TTL index handles cleanup)
        if datetime.utcnow() - record["created_at"] > timedelta(minutes=5):
            return False

        # Valid — delete OTP (single use) and update last_login
        await db.otp_codes.delete_one({"phone": phone})
        await db.users.update_one(
            {"phone": phone},
            {"$set": {"last_login": datetime.utcnow()}},
        )
        return True

    # ── JWT helpers ───────────────────────────────────────────────────────

    @staticmethod
    def create_access_token(data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def create_refresh_token(data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except JWTError:
            return None

    @staticmethod
    def create_token_pair(user: dict) -> dict:
        token_data = {
            "user_id": user["user_id"],
            "phone": user["phone"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        }
        # Include connector scope for RBAC (resolved at login)
        if user.get("admin_group_id"):
            token_data["admin_group_id"] = user["admin_group_id"]
        if "_connector_scope" in user:
            token_data["connector_scope"] = user["_connector_scope"]
        return {
            "access_token": AuthService.create_access_token(token_data),
            "refresh_token": AuthService.create_refresh_token(token_data),
            "token_type": "bearer",
        }


auth_service = AuthService()
