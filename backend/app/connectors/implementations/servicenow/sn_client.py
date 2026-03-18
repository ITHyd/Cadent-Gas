"""ServiceNow REST API client — thin async HTTP wrapper using httpx.

Handles all direct HTTP communication with a ServiceNow instance:
- Authentication (OAuth2 / Basic)
- CRUD on incident table
- Comments and attachments
- Rate limit / auth error detection

Reference: https://docs.servicenow.com/bundle/latest/page/integrate/inbound-rest/concept/c_TableAPI.html
"""
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.connectors.base_connector import (
    AuthenticationError,
    ConnectorError,
    RateLimitError,
)
from app.models.connector import AuthMethod

logger = logging.getLogger(__name__)

# ServiceNow API paths
SN_TABLE_API = "/api/now/table"
SN_ATTACHMENT_API = "/api/now/attachment"
SN_OAUTH_TOKEN = "/oauth_token.do"

# Default request timeout (seconds)
REQUEST_TIMEOUT = 30.0


class ServiceNowClient:
    """Async HTTP client for the ServiceNow REST API."""

    def __init__(
        self,
        instance_url: str,
        auth_method: AuthMethod = AuthMethod.BASIC,
        table_name: str = "incident",
    ):
        # Normalise URL: strip trailing slash
        self.instance_url = instance_url.rstrip("/")
        self.auth_method = auth_method
        self.table_name = table_name

        # Auth state — populated by authenticate()
        self._auth_headers: Dict[str, str] = {}
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ── Authentication ────────────────────────────────────────────────────

    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """Establish auth session.  Supports OAuth2 and Basic auth."""
        try:
            if self.auth_method == AuthMethod.OAUTH2:
                return await self._authenticate_oauth2(credentials)
            elif self.auth_method == AuthMethod.BASIC:
                return self._authenticate_basic(credentials)
            elif self.auth_method == AuthMethod.API_KEY:
                return self._authenticate_api_key(credentials)
            else:
                raise AuthenticationError(
                    f"Unsupported auth method: {self.auth_method}",
                    connector_type="servicenow",
                )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(
                f"Authentication failed: {exc}",
                connector_type="servicenow",
            ) from exc

    async def _authenticate_oauth2(self, credentials: Dict[str, Any]) -> bool:
        token_url = credentials.get("token_url") or f"{self.instance_url}{SN_OAUTH_TOKEN}"
        payload = {
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(token_url, data=payload)

        if resp.status_code != 200:
            raise AuthenticationError(
                f"OAuth2 token request failed ({resp.status_code}): {resp.text}",
                connector_type="servicenow",
            )

        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 1800))
        self._token_expires_at = time.time() + expires_in - 60  # refresh 60s early
        self._auth_headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        logger.info("ServiceNow OAuth2 authentication successful")
        return True

    def _authenticate_basic(self, credentials: Dict[str, Any]) -> bool:
        import base64

        username = credentials["username"]
        password = credentials["password"]
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth_headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        logger.info("ServiceNow Basic auth credentials set")
        return True

    def _authenticate_api_key(self, credentials: Dict[str, Any]) -> bool:
        header_name = credentials.get("api_key_header", "X-API-Key")
        self._auth_headers = {
            header_name: credentials["api_key"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        logger.info("ServiceNow API-key auth credentials set")
        return True

    # ── Core HTTP helpers ─────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
        data: Optional[bytes] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Send an HTTP request to ServiceNow and return the parsed JSON."""
        url = f"{self.instance_url}{path}"
        headers = {**self._auth_headers, **(extra_headers or {})}

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.request(
                    method, url, headers=headers, json=json, params=params, content=data,
                )
        except httpx.TimeoutException as exc:
            raise ConnectorError(
                f"ServiceNow request timed out: {method} {path}",
                connector_type="servicenow",
                retriable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ConnectorError(
                f"ServiceNow connection error: {exc}",
                connector_type="servicenow",
                retriable=True,
            ) from exc

        return self._handle_response(resp, method, path)

    def _handle_response(
        self, resp: httpx.Response, method: str, path: str
    ) -> Dict[str, Any]:
        """Translate HTTP status codes into appropriate exceptions."""
        if resp.status_code == 401:
            raise AuthenticationError(
                "ServiceNow returned 401 Unauthorized — credentials may be invalid or expired",
                connector_type="servicenow",
            )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            raise RateLimitError(
                "ServiceNow rate limit reached",
                connector_type="servicenow",
                retry_after=retry_after,
            )
        if resp.status_code >= 500:
            raise ConnectorError(
                f"ServiceNow server error ({resp.status_code}): {resp.text[:200]}",
                connector_type="servicenow",
                retriable=True,
            )
        if resp.status_code >= 400:
            raise ConnectorError(
                f"ServiceNow client error ({resp.status_code}): {resp.text[:300]}",
                connector_type="servicenow",
                retriable=False,
            )

        # 200/201/204
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ── Incident CRUD ─────────────────────────────────────────────────────

    async def create_incident(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/now/table/incident — create a new incident."""
        result = await self._request(
            "POST", f"{SN_TABLE_API}/{self.table_name}", json=payload
        )
        record = result.get("result", {})
        logger.info(
            "Created SN incident %s (sys_id=%s)",
            record.get("number"),
            record.get("sys_id"),
        )
        return record

    async def update_incident(
        self, sys_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PATCH /api/now/table/incident/{sys_id} — update an existing incident."""
        result = await self._request(
            "PATCH", f"{SN_TABLE_API}/{self.table_name}/{sys_id}", json=payload
        )
        record = result.get("result", {})
        logger.info("Updated SN incident sys_id=%s", sys_id)
        return record

    async def get_incident(self, sys_id: str) -> Dict[str, Any]:
        """GET /api/now/table/incident/{sys_id} — fetch a single incident."""
        result = await self._request(
            "GET", f"{SN_TABLE_API}/{self.table_name}/{sys_id}"
        )
        return result.get("result", {})

    async def query_incidents(
        self,
        query: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """GET /api/now/table/incident?sysparm_query=... — query multiple incidents."""
        params: Dict[str, Any] = {
            "sysparm_limit": limit,
            "sysparm_offset": offset,
        }
        if query:
            params["sysparm_query"] = query

        result = await self._request(
            "GET", f"{SN_TABLE_API}/{self.table_name}", params=params
        )
        return result.get("result", [])

    # ── Comments ──────────────────────────────────────────────────────────

    async def add_comment(
        self, sys_id: str, comment: str, is_work_note: bool = False
    ) -> Dict[str, Any]:
        """Add a comment or work note to an existing SN incident.

        Uses PATCH to update the comments or work_notes field.
        """
        field = "work_notes" if is_work_note else "comments"
        payload = {field: comment}
        return await self.update_incident(sys_id, payload)

    # ── Attachments ───────────────────────────────────────────────────────

    async def add_attachment(
        self,
        sys_id: str,
        filename: str,
        content_type: str,
        file_data: bytes,
    ) -> Dict[str, Any]:
        """POST /api/now/attachment/file — upload a file to an incident."""
        params = {
            "table_name": self.table_name,
            "table_sys_id": sys_id,
            "file_name": filename,
        }
        extra_headers = {"Content-Type": content_type}
        result = await self._request(
            "POST",
            f"{SN_ATTACHMENT_API}/file",
            params=params,
            data=file_data,
            extra_headers=extra_headers,
        )
        record = result.get("result", {})
        logger.info("Uploaded attachment '%s' to SN incident %s", filename, sys_id)
        return record

    async def get_attachments(self, sys_id: str) -> List[Dict[str, Any]]:
        """GET /api/now/attachment?sysparm_query=table_sys_id={sys_id}."""
        params = {"sysparm_query": f"table_sys_id={sys_id}"}
        result = await self._request("GET", SN_ATTACHMENT_API, params=params)
        return result.get("result", [])

    # ── Connectivity ──────────────────────────────────────────────────────

    async def test_connection(self) -> Dict[str, Any]:
        """Verify connectivity by fetching a single incident record."""
        start = time.time()
        try:
            params = {"sysparm_limit": 1}
            await self._request(
                "GET", f"{SN_TABLE_API}/{self.table_name}", params=params
            )
            latency_ms = round((time.time() - start) * 1000)
            return {
                "status": "ok",
                "message": "Connection successful",
                "latency_ms": latency_ms,
            }
        except ConnectorError as exc:
            latency_ms = round((time.time() - start) * 1000)
            return {
                "status": "error",
                "message": str(exc),
                "latency_ms": latency_ms,
            }
