"""CredentialVault — AES-256 encrypted storage for connector secrets.

All connector credentials (OAuth tokens, API keys, passwords) are encrypted
before storage in MongoDB and decrypted only when needed for API calls.

Security guarantees:
    - AES-256-GCM encryption (authenticated encryption)
    - Per-tenant isolation (tenant_id checked on every access)
    - Audit logging on every read/write
    - Encryption key derived from platform SECRET_KEY + salt
"""
import base64
import hashlib
import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.core.mongodb import get_database
from app.models.connector import (
    ConnectorCredentials,
    AuthMethod,
)

logger = logging.getLogger(__name__)

# Fields that contain secrets and must be encrypted
ENCRYPTED_FIELDS = {
    "client_id",
    "client_secret",
    "access_token",
    "refresh_token",
    "username",
    "password",
    "api_key",
    "access_key_id",
    "secret_access_key",
}


class CredentialVault:
    """Encrypted credential storage with per-tenant isolation.

    Uses AES-256-GCM for encryption. The encryption key is derived from
    the platform's SECRET_KEY using PBKDF2.
    """

    def __init__(self, secret_key: str):
        """Initialize vault with the platform secret key.

        Args:
            secret_key: The platform's SECRET_KEY from config.
        """
        self._salt = b"connector_vault_v1"
        self._key = self._derive_key(secret_key)
        # Fallback in-memory cache (used when DB is unavailable).
        self._store: Dict[str, Dict[str, Any]] = {}
        self._known_configs = set()

    def _credentials_col(self):
        db = get_database()
        return db.connector_credentials if db is not None else None

    async def bootstrap_cache(self) -> None:
        """Prime known config IDs from persistent storage."""
        col = self._credentials_col()
        if col is None:
            return
        try:
            async for doc in col.find({}, {"config_id": 1, "_id": 0}):
                cfg = doc.get("config_id")
                if cfg:
                    self._known_configs.add(cfg)
        except Exception:
            logger.exception("Failed to bootstrap credential cache")

    def _derive_key(self, secret_key: str) -> bytes:
        """Derive a 256-bit AES key from the platform secret using PBKDF2."""
        return hashlib.pbkdf2_hmac(
            "sha256",
            secret_key.encode("utf-8"),
            self._salt,
            iterations=100_000,
            dklen=32,
        )

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string using AES-256-GCM.

        Returns:
            Base64-encoded string: nonce(12) + ciphertext + tag(16)
        """
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            # Fallback: base64 encoding only (NOT secure, for dev/demo only)
            logger.warning("cryptography package not installed — using base64 fallback (NOT SECURE)")
            return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("utf-8")

        nonce = os.urandom(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # Combine nonce + ciphertext for storage
        return "aes:" + base64.b64encode(nonce + ciphertext).decode("utf-8")

    def _decrypt(self, encrypted: str) -> str:
        """Decrypt an encrypted string.

        Args:
            encrypted: The base64-encoded encrypted string from _encrypt.

        Returns:
            Decrypted plaintext.
        """
        if encrypted.startswith("b64:"):
            # Fallback decode
            return base64.b64decode(encrypted[4:]).decode("utf-8")

        if not encrypted.startswith("aes:"):
            raise ValueError("Unknown encryption format")

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise RuntimeError("cryptography package required for AES decryption")

        raw = base64.b64decode(encrypted[4:])
        nonce = raw[:12]
        ciphertext = raw[12:]
        aesgcm = AESGCM(self._key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def _encrypt_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt all secret fields in a credential dict."""
        encrypted = dict(data)
        for field in ENCRYPTED_FIELDS:
            if field in encrypted and encrypted[field] is not None:
                encrypted[field] = self._encrypt(str(encrypted[field]))
        return encrypted

    def _decrypt_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt all secret fields in a credential dict."""
        decrypted = dict(data)
        for field in ENCRYPTED_FIELDS:
            if field in decrypted and decrypted[field] is not None:
                try:
                    decrypted[field] = self._decrypt(str(decrypted[field]))
                except Exception as e:
                    logger.error(f"Failed to decrypt field '{field}': {e}")
                    decrypted[field] = None
        return decrypted

    # ── CRUD Operations ──────────────────────────────────────────────────

    async def store_credentials(
        self,
        config_id: str,
        tenant_id: str,
        auth_method: AuthMethod,
        credentials: Dict[str, Any],
    ) -> str:
        """Store encrypted credentials for a connector config.

        Args:
            config_id: The ConnectorConfig.config_id this belongs to.
            tenant_id: Tenant ID for isolation.
            auth_method: OAuth2, Basic, API Key, or IAM.
            credentials: Raw credential dict with plaintext secrets.

        Returns:
            credential_id of the stored credentials.
        """
        credential_id = f"CRED_{uuid.uuid4().hex[:12].upper()}"
        now = datetime.utcnow()

        # Build the credential record
        record = {
            "credential_id": credential_id,
            "config_id": config_id,
            "tenant_id": tenant_id,
            "auth_method": auth_method.value if isinstance(auth_method, AuthMethod) else auth_method,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "access_count": 0,
        }

        # Merge in the credential fields
        for key, value in credentials.items():
            if value is not None:
                record[key] = value

        # Encrypt secret fields
        encrypted_record = self._encrypt_fields(record)

        col = self._credentials_col()
        if col is not None:
            await col.update_one(
                {"config_id": config_id},
                {"$set": encrypted_record},
                upsert=True,
            )
            self._known_configs.add(config_id)
        else:
            self._store[config_id] = encrypted_record

        logger.info(
            f"Stored credentials for config={config_id} tenant={tenant_id} "
            f"method={auth_method} credential_id={credential_id}"
        )
        return credential_id

    async def get_credentials(
        self, config_id: str, tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt credentials for a connector config.

        Args:
            config_id: The ConnectorConfig.config_id.
            tenant_id: Tenant ID (enforced for isolation).

        Returns:
            Decrypted credential dict, or None if not found.

        Raises:
            PermissionError: If tenant_id doesn't match stored credentials.
        """
        col = self._credentials_col()
        if col is not None:
            record = await col.find_one({"config_id": config_id}, {"_id": 0})
        else:
            record = self._store.get(config_id)
        if not record:
            logger.warning(f"No credentials found for config={config_id}")
            return None

        # Tenant isolation check
        stored_tenant = record.get("tenant_id")
        if stored_tenant != tenant_id:
            logger.error(
                f"Tenant isolation violation: requested tenant={tenant_id} "
                f"but credentials belong to tenant={stored_tenant}"
            )
            raise PermissionError(
                f"Credentials for config={config_id} do not belong to tenant={tenant_id}"
            )

        # Decrypt
        decrypted = self._decrypt_fields(record)

        # Audit: increment access count
        access_count = int(record.get("access_count", 0)) + 1
        now_iso = datetime.utcnow().isoformat()
        record["access_count"] = access_count
        record["last_accessed_at"] = now_iso

        if col is not None:
            await col.update_one(
                {"config_id": config_id},
                {"$set": {"access_count": access_count, "last_accessed_at": now_iso}},
            )
        else:
            self._store[config_id] = record

        logger.info(
            f"Retrieved credentials for config={config_id} tenant={tenant_id} "
            f"(access #{access_count})"
        )
        return decrypted

    async def update_credentials(
        self, config_id: str, tenant_id: str, updates: Dict[str, Any]
    ) -> bool:
        """Update specific credential fields (e.g., rotate tokens).

        Args:
            config_id: The ConnectorConfig.config_id.
            tenant_id: Tenant ID for isolation.
            updates: Fields to update (will be encrypted).

        Returns:
            True if updated successfully.
        """
        col = self._credentials_col()
        if col is not None:
            record = await col.find_one({"config_id": config_id}, {"_id": 0})
        else:
            record = self._store.get(config_id)
        if not record:
            return False

        if record.get("tenant_id") != tenant_id:
            raise PermissionError(
                f"Credentials for config={config_id} do not belong to tenant={tenant_id}"
            )

        # Encrypt new secret values
        encrypted_updates = self._encrypt_fields(updates)
        now_iso = datetime.utcnow().isoformat()
        encrypted_updates["updated_at"] = now_iso
        encrypted_updates["last_rotated_at"] = now_iso

        if col is not None:
            await col.update_one({"config_id": config_id}, {"$set": encrypted_updates})
        else:
            record.update(encrypted_updates)
            self._store[config_id] = record

        logger.info(
            f"Updated credentials for config={config_id} tenant={tenant_id} "
            f"fields={list(updates.keys())}"
        )
        return True

    async def delete_credentials(self, config_id: str, tenant_id: str) -> bool:
        """Delete credentials for a connector config.

        Args:
            config_id: The ConnectorConfig.config_id.
            tenant_id: Tenant ID for isolation.

        Returns:
            True if deleted, False if not found.
        """
        col = self._credentials_col()
        if col is not None:
            record = await col.find_one({"config_id": config_id}, {"_id": 0})
        else:
            record = self._store.get(config_id)
        if not record:
            return False

        if record.get("tenant_id") != tenant_id:
            raise PermissionError(
                f"Credentials for config={config_id} do not belong to tenant={tenant_id}"
            )

        if col is not None:
            await col.delete_one({"config_id": config_id})
        else:
            del self._store[config_id]
        self._known_configs.discard(config_id)
        logger.info(f"Deleted credentials for config={config_id} tenant={tenant_id}")
        return True

    async def list_configs_with_credentials(self, tenant_id: str) -> List[str]:
        """List all config_ids that have stored credentials for a tenant."""
        col = self._credentials_col()
        if col is not None:
            configs = []
            async for rec in col.find({"tenant_id": tenant_id}, {"config_id": 1, "_id": 0}):
                if rec.get("config_id"):
                    configs.append(rec["config_id"])
            return configs
        return [
            config_id
            for config_id, record in self._store.items()
            if record.get("tenant_id") == tenant_id
        ]

    def has_credentials(self, config_id: str) -> bool:
        """Check if credentials exist for a config (no decryption)."""
        return config_id in self._known_configs or config_id in self._store
