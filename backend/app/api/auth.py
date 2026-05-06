"""Authentication API endpoints — phone + OTP flow + username/password login."""
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.models.user import SendOTPRequest, VerifyOTPRequest, AdminLoginRequest
from app.services.auth_service import auth_service
from app.core.auth_dependencies import get_current_user
from app.core.mongodb import get_database
from app.core.rate_limit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)


class RefreshTokenRequest(BaseModel):
    refresh_token: str

SENSITIVE_FIELDS = {"_id", "password_hash"}


def _normalize_company_connector_scope(scope: list) -> list:
    """Ensure company users keep visibility of portal/chatbot incidents."""
    if not scope:
        return []
    normalized = list(dict.fromkeys(scope))
    if "portal" not in normalized:
        normalized.append("portal")
    return normalized


async def _enrich_user_with_scope(user: dict) -> dict:
    """Resolve connector_scope from the user's admin_group_id and tenant's admin_groups.

    Sets user["_connector_scope"] which gets embedded in the JWT.
    Non-company users or ungrouped users get [] (no restriction = see everything).
    """
    if user.get("role") not in ("company",) or not user.get("admin_group_id"):
        user["_connector_scope"] = []
        return user

    db = get_database()
    tenant = await db.tenants.find_one(
        {"tenant_id": user.get("tenant_id")},
        {"admin_groups": 1},
    )
    if not tenant:
        user["_connector_scope"] = []
        return user

    for group in tenant.get("admin_groups") or []:
        if group.get("group_id") == user["admin_group_id"]:
            user["_connector_scope"] = _normalize_company_connector_scope(
                group.get("connector_scope", [])
            )
            return user

    # Group not found (stale reference) — treat as general admin
    user["_connector_scope"] = []
    return user


def _serialize_user(user: dict) -> dict:
    """Build a JSON-safe user dict, excluding sensitive fields."""
    user_data = {k: v for k, v in user.items() if k not in SENSITIVE_FIELDS}
    # Include resolved connector_scope if present
    if "_connector_scope" in user:
        user_data["connector_scope"] = user["_connector_scope"]
    # Remove internal key
    user_data.pop("_connector_scope", None)
    for key in ("created_at", "updated_at", "last_login"):
        if user_data.get(key):
            user_data[key] = user_data[key].isoformat()
    return user_data


@router.post("/send-otp")
@limiter.limit("5/minute")
async def send_otp(request: Request, body: SendOTPRequest):
    """Step 1: submit phone number, receive OTP (dev: returned in response)."""
    user = await auth_service.find_user_by_phone(body.phone)
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this phone number")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    otp = await auth_service.generate_and_store_otp(body.phone)

    return {
        "message": "OTP sent successfully",
        "phone": body.phone,
        "otp": otp,
        "expires_in_seconds": 300,
    }


@router.post("/verify-otp")
@limiter.limit("10/minute")
async def verify_otp(request: Request, body: VerifyOTPRequest):
    """Step 2: submit phone + OTP, receive JWT tokens + user profile."""
    user = await auth_service.find_user_by_phone(body.phone)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_valid = await auth_service.verify_otp(body.phone, body.otp)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")

    await _enrich_user_with_scope(user)
    tokens = auth_service.create_token_pair(user)
    return {**tokens, "user": _serialize_user(user)}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    user = await auth_service.find_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await _enrich_user_with_scope(user)
    return _serialize_user(user)


@router.post("/refresh")
async def refresh_token(body: RefreshTokenRequest):
    """Exchange a refresh token for a new access + refresh token pair."""
    payload = auth_service.decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await auth_service.find_user_by_id(payload["user_id"])
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    await _enrich_user_with_scope(user)
    return auth_service.create_token_pair(user)


@router.post("/admin-login")
@limiter.limit("10/minute")
async def admin_login(request: Request, body: AdminLoginRequest):
    """Authenticate admin/company/super_user with username + password."""
    user = await auth_service.find_user_by_username(body.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    allowed_roles = {"company", "super_user", "admin"}
    if user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="This login is only for admin users")

    password_hash = user.get("password_hash")
    if not password_hash:
        raise HTTPException(status_code=401, detail="Password login not configured for this account")

    if not auth_service.verify_password(body.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Update last_login
    db = get_database()
    await db.users.update_one(
        {"username": body.username},
        {"$set": {"last_login": datetime.utcnow()}},
    )

    await _enrich_user_with_scope(user)
    tokens = auth_service.create_token_pair(user)
    return {**tokens, "user": _serialize_user(user)}


@router.get("/lookup-by-phone")
async def lookup_by_phone(
    phone: str,
    current_user: dict = Depends(get_current_user),
):
    """Look up a customer by phone number (company admin only, tenant-scoped)."""
    if current_user.get("role") not in ("company", "super_user", "admin"):
        raise HTTPException(status_code=403, detail="Only company admins can look up customers")

    # Normalize phone: strip spaces/dashes, ensure +44 prefix
    import re
    phone = re.sub(r"[\s\-()]", "", phone)
    if re.match(r"^\d{10}$", phone):
        phone = "+44" + phone
    elif re.match(r"^0\d{10}$", phone):
        phone = "+44" + phone[1:]
    elif re.match(r"^44\d{10}$", phone):
        phone = "+" + phone
    elif not phone.startswith("+"):
        phone = "+" + phone

    caller_tenant = current_user.get("tenant_id")
    db = get_database()
    user = await db.users.find_one({
        "phone": phone,
        "tenant_id": caller_tenant,
        "role": "user",
    })
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found in your tenant")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Customer account is deactivated")

    return {
        "user_id": user["user_id"],
        "full_name": user.get("full_name", ""),
        "phone": user["phone"],
        "address": user.get("address", ""),
        "location": user.get("location", ""),
    }
