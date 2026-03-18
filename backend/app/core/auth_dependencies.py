"""FastAPI authentication dependencies."""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status, WebSocket, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.services.auth_service import auth_service
from app.models.user import UserRole

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Extract and validate JWT from the Authorization header."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = auth_service.decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_user_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> Optional[dict]:
    """Validate JWT from WebSocket query param ?token=xxx."""
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return None

    payload = auth_service.decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid or expired token")
        return None

    return payload


def require_role(*roles: UserRole):
    """
    Factory returning a dependency that enforces role-based access.

    Usage::

        @router.get("/admin-only")
        async def endpoint(user=Depends(require_role(UserRole.SUPER_USER, UserRole.ADMIN))):
            ...
    """
    async def _role_checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role")
        if user_role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {[r.value for r in roles]}",
            )
        return current_user
    return _role_checker
