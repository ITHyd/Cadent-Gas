"""SAP OData API client — thin async HTTP wrapper using httpx.

Handles all direct HTTP communication with a SAP Service Cloud / S/4HANA instance:
- Authentication (OAuth2 / API Key)
- CSRF token management (required for write operations)
- CRUD on service order entities
- Comments (ServiceOrderText) and attachments

Reference: https://api.sap.com/api/API_SERVICE_ORDER_SRV
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

# SAP OData API paths
DEFAULT_API_PATH = "/sap/opu/odata/sap/API_SERVICE_ORDER_SRV"
SAP_ENTITY_SERVICE_ORDER = "/A_ServiceOrder"
SAP_ENTITY_TEXT = "/A_ServiceOrderText"
SAP_ATTACHMENT_API = "/sap/opu/odata/sap/API_CV_ATTACHMENT_SRV/AttachmentContentSet"

# Default request timeout (seconds)
REQUEST_TIMEOUT = 30.0


class SAPClient:
    """Async HTTP client for the SAP OData REST API."""

    def __init__(
        self,
        instance_url: str,
        auth_method: AuthMethod = AuthMethod.OAUTH2,
        api_path: str = DEFAULT_API_PATH,
    ):
        self.instance_url = instance_url.rstrip("/")
        self.auth_method = auth_method
        self.api_path = api_path

        # Auth state
        self._auth_headers: Dict[str, str] = {}
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._csrf_token: Optional[str] = None

    # ── Authentication ─────────────────────────────────────────────────────

    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """Establish auth session. Supports OAuth2, API Key, and Basic auth."""
        try:
            if self.auth_method == AuthMethod.OAUTH2:
                return await self._authenticate_oauth2(credentials)
            elif self.auth_method == AuthMethod.API_KEY:
                return self._authenticate_api_key(credentials)
            elif self.auth_method == AuthMethod.BASIC:
                return self._authenticate_basic(credentials)
            else:
                raise AuthenticationError(
                    f"Unsupported auth method: {self.auth_method}",
                    connector_type="sap",
                )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(
                f"SAP authentication failed: {exc}",
                connector_type="sap",
            ) from exc

    async def _authenticate_oauth2(self, credentials: Dict[str, Any]) -> bool:
        token_url = credentials.get("token_url")
        if not token_url:
            raise AuthenticationError(
                "OAuth2 token_url is required for SAP authentication",
                connector_type="sap",
            )
        payload = {
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(token_url, data=payload)

        if resp.status_code != 200:
            raise AuthenticationError(
                f"SAP OAuth2 token request failed ({resp.status_code}): {resp.text}",
                connector_type="sap",
            )

        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 1800))
        self._token_expires_at = time.time() + expires_in - 60
        self._auth_headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        logger.info("SAP OAuth2 authentication successful")
        return True

    def _authenticate_api_key(self, credentials: Dict[str, Any]) -> bool:
        header_name = credentials.get("api_key_header", "APIKey")
        self._auth_headers = {
            header_name: credentials["api_key"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        logger.info("SAP API-key auth credentials set")
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
        logger.info("SAP Basic auth credentials set")
        return True

    # ── CSRF Token ─────────────────────────────────────────────────────────

    async def _fetch_csrf_token(self) -> str:
        """Fetch a CSRF token from SAP (required before POST/PATCH/DELETE)."""
        url = f"{self.instance_url}{self.api_path}"
        headers = {**self._auth_headers, "X-CSRF-Token": "Fetch"}
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.get(url, headers=headers)
            token = resp.headers.get("x-csrf-token", "")
            if token:
                self._csrf_token = token
                return token
            logger.warning("SAP did not return a CSRF token")
            return ""
        except Exception as exc:
            logger.warning("Failed to fetch SAP CSRF token: %s", exc)
            return ""

    # ── Core HTTP helpers ──────────────────────────────────────────────────

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
        """Send an HTTP request to SAP and return the parsed JSON."""
        url = f"{self.instance_url}{path}"
        headers = {**self._auth_headers, **(extra_headers or {})}

        # CSRF token required for write operations
        if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
            if not self._csrf_token:
                await self._fetch_csrf_token()
            if self._csrf_token:
                headers["X-CSRF-Token"] = self._csrf_token

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.request(
                    method, url, headers=headers, json=json, params=params, content=data,
                )
        except httpx.TimeoutException as exc:
            raise ConnectorError(
                f"SAP request timed out: {method} {path}",
                connector_type="sap",
                retriable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ConnectorError(
                f"SAP connection error: {exc}",
                connector_type="sap",
                retriable=True,
            ) from exc

        return self._handle_response(resp, method, path)

    def _handle_response(
        self, resp: httpx.Response, method: str, path: str
    ) -> Dict[str, Any]:
        """Translate HTTP status codes into appropriate exceptions."""
        if resp.status_code == 401:
            raise AuthenticationError(
                "SAP returned 401 Unauthorized — credentials may be invalid or expired",
                connector_type="sap",
            )
        if resp.status_code == 403:
            # CSRF token expired — clear it so next request fetches a new one
            self._csrf_token = None
            raise ConnectorError(
                "SAP returned 403 Forbidden — CSRF token may have expired",
                connector_type="sap",
                retriable=True,
            )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            raise RateLimitError(
                "SAP rate limit reached",
                connector_type="sap",
                retry_after=retry_after,
            )
        if resp.status_code >= 500:
            raise ConnectorError(
                f"SAP server error ({resp.status_code}): {resp.text[:200]}",
                connector_type="sap",
                retriable=True,
            )
        if resp.status_code >= 400:
            raise ConnectorError(
                f"SAP client error ({resp.status_code}): {resp.text[:300]}",
                connector_type="sap",
                retriable=False,
            )

        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ── Service Order CRUD ─────────────────────────────────────────────────

    async def create_service_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST — create a new service order."""
        path = f"{self.api_path}{SAP_ENTITY_SERVICE_ORDER}"
        result = await self._request("POST", path, json=payload)
        # OData v2 wraps in {"d": {...}}
        record = result.get("d", result)
        logger.info(
            "Created SAP service order %s",
            record.get("ServiceOrderID"),
        )
        return record

    async def update_service_order(
        self, order_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PATCH — update an existing service order."""
        path = f"{self.api_path}{SAP_ENTITY_SERVICE_ORDER}('{order_id}')"
        result = await self._request("PATCH", path, json=payload)
        record = result.get("d", result) if result else {}
        logger.info("Updated SAP service order %s", order_id)
        return record

    async def get_service_order(self, order_id: str) -> Dict[str, Any]:
        """GET — fetch a single service order."""
        path = f"{self.api_path}{SAP_ENTITY_SERVICE_ORDER}('{order_id}')"
        result = await self._request("GET", path)
        return result.get("d", result)

    async def query_service_orders(
        self,
        filter_str: str = "",
        top: int = 100,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """GET — query multiple service orders with OData $filter."""
        params: Dict[str, Any] = {
            "$top": top,
            "$skip": skip,
            "$format": "json",
        }
        if filter_str:
            params["$filter"] = filter_str

        path = f"{self.api_path}{SAP_ENTITY_SERVICE_ORDER}"
        result = await self._request("GET", path, params=params)
        data = result.get("d", result)
        return data.get("results", []) if isinstance(data, dict) else []

    # ── Comments (ServiceOrderText) ────────────────────────────────────────

    async def add_text(
        self, order_id: str, text: str, text_type: str = "S001"
    ) -> Dict[str, Any]:
        """Add a text entry to a service order."""
        path = f"{self.api_path}{SAP_ENTITY_TEXT}"
        payload = {
            "ServiceOrder": order_id,
            "Language": "EN",
            "LongTextID": text_type,
            "LongText": text,
        }
        result = await self._request("POST", path, json=payload)
        return result.get("d", result)

    async def get_texts(self, order_id: str) -> List[Dict[str, Any]]:
        """Fetch all text entries for a service order."""
        params = {
            "$filter": f"ServiceOrder eq '{order_id}'",
            "$format": "json",
        }
        path = f"{self.api_path}{SAP_ENTITY_TEXT}"
        result = await self._request("GET", path, params=params)
        data = result.get("d", result)
        return data.get("results", []) if isinstance(data, dict) else []

    # ── Attachments ────────────────────────────────────────────────────────

    async def add_attachment(
        self,
        order_id: str,
        filename: str,
        content_type: str,
        file_data: bytes,
    ) -> Dict[str, Any]:
        """Upload a file attachment to a service order."""
        slug = f"ServiceOrder='{order_id}',FileName='{filename}'"
        extra_headers = {
            "Content-Type": content_type,
            "Slug": slug,
        }
        result = await self._request(
            "POST",
            SAP_ATTACHMENT_API,
            data=file_data,
            extra_headers=extra_headers,
        )
        record = result.get("d", result)
        logger.info("Uploaded attachment '%s' to SAP order %s", filename, order_id)
        return record

    async def get_attachments(self, order_id: str) -> List[Dict[str, Any]]:
        """List attachments for a service order."""
        params = {
            "$filter": f"LinkedSAPObjectKey eq '{order_id}'",
            "$format": "json",
        }
        result = await self._request("GET", SAP_ATTACHMENT_API, params=params)
        data = result.get("d", result)
        return data.get("results", []) if isinstance(data, dict) else []

    # ── Connectivity ───────────────────────────────────────────────────────

    async def test_connection(self) -> Dict[str, Any]:
        """Verify connectivity by fetching a single service order record."""
        start = time.time()
        try:
            params = {"$top": 1, "$format": "json"}
            await self._request(
                "GET",
                f"{self.api_path}{SAP_ENTITY_SERVICE_ORDER}",
                params=params,
            )
            latency_ms = round((time.time() - start) * 1000)
            return {
                "status": "ok",
                "message": "SAP connection successful",
                "latency_ms": latency_ms,
            }
        except ConnectorError as exc:
            latency_ms = round((time.time() - start) * 1000)
            return {
                "status": "error",
                "message": str(exc),
                "latency_ms": latency_ms,
            }
