"""User and authentication models"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    COMPANY = "company"
    SUPER_USER = "super_user"
    ADMIN = "admin"


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole
    tenant_id: Optional[str] = None


class UserCreate(UserBase):
    password: str


class User(UserBase):
    user_id: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: User


class TokenData(BaseModel):
    user_id: str
    email: str
    role: UserRole
    tenant_id: Optional[str] = None


# ── Phone / OTP auth models ──────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    phone: str  # Format: +44XXXXXXXXXX


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class UserInDB(BaseModel):
    """MongoDB user document model."""
    user_id: str
    phone: str
    full_name: str
    role: UserRole
    tenant_id: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    username: Optional[str] = None
    password_hash: Optional[str] = None
    admin_group_id: Optional[str] = None  # References AdminGroup.group_id within tenant
