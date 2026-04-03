from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from .config import settings


class BackendClient:
    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def _login(self) -> str:
        async with httpx.AsyncClient(
            base_url=settings.backend_base_url,
            timeout=settings.request_timeout_seconds,
        ) as client:
            response = await client.post(
                "/api/v1/auth/admin-login",
                json={
                    "username": settings.backend_username,
                    "password": settings.backend_password,
                },
            )
            response.raise_for_status()
            payload = response.json()

        self._access_token = payload["access_token"]
        # Backend access token lifetime is 30 minutes by default.
        self._token_expires_at = time.time() + (25 * 60)
        return self._access_token

    async def _get_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        return await self._login()

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        token = await self._get_token()
        async with httpx.AsyncClient(
            base_url=settings.backend_base_url,
            timeout=settings.request_timeout_seconds,
        ) as client:
            response = await client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()


backend_client = BackendClient()
