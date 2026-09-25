"""LDAP Provider implementation."""

from typing import TYPE_CHECKING

from loguru import logger

from bisheng.common.errcode.user_sync import LdapErrorCode
from bisheng.user_sync.domain.models import LdapConfig, LdapConfigDao
from bisheng.user_sync.domain.providers.base import AuthResult, UserAttrs, UserSyncProvider

if TYPE_CHECKING:
    from fastapi import Request


class LdapProvider(UserSyncProvider):
    """LDAP authentication provider."""

    source = "ldap"

    def __init__(self, tenant_id: int):
        super().__init__(tenant_id)
        self.config: LdapConfig | None = None

    async def _load_config(self) -> LdapConfig:
        """Load LDAP config with tenant precedence."""
        if self.config is not None:
            return self.config

        config = await LdapConfigDao.aget_for_tenant(self.tenant_id)
        if config is None or not config.enabled:
            raise LdapErrorCode.LDAP_CONFIG_NOT_FOUND.http_exception()

        self.config = config
        return config

    async def authenticate(self, request: "Request") -> AuthResult:
        """
        Authenticate user via LDAP bind.

        Expected body:
        {
            "username": str,
            "password": str  # RSA encrypted
        }
        """

        body = await request.json()
        username = body.get("username", "").strip()
        encrypted_password = body.get("password", "")

        if not username or not encrypted_password:
            raise LdapErrorCode.LDAP_AUTH_FAILED.http_exception()

        # Decrypt password (RSA private key decryption)
        password = self._decrypt_password(encrypted_password)
        if not password:
            raise LdapErrorCode.LDAP_AUTH_FAILED.http_exception()

        # Load config
        config = await self._load_config()

        # Build bind DN
        bind_dn = self._build_bind_dn(username, config)
        logger.debug("LDAP bind attempt for user=%s", username)

        # Perform LDAP bind
        user_entry = await self._ldap_bind(
            server_url=config.server_url,
            bind_dn=bind_dn,
            password=password,
            base_dn=config.base_dn,
            user_filter=config.user_filter,
            use_ssl=config.use_ssl,
            timeout=config.timeout,
        )

        if user_entry is None:
            raise LdapErrorCode.LDAP_AUTH_FAILED.http_exception()

        # Return auth result
        return AuthResult(
            external_id=user_entry.get("uid", [username])[0]
            if isinstance(user_entry.get("uid"), list)
            else user_entry.get("uid", username),
            name=user_entry.get("cn", [None])[0] if isinstance(user_entry.get("cn"), list) else user_entry.get("cn"),
            email=user_entry.get("mail", [None])[0]
            if isinstance(user_entry.get("mail"), list)
            else user_entry.get("mail"),
            phone=user_entry.get("mobile", [None])[0]
            if isinstance(user_entry.get("mobile"), list)
            else user_entry.get("mobile"),
            department=user_entry.get("department", [None])[0]
            if isinstance(user_entry.get("department"), list)
            else user_entry.get("department"),
            raw_attributes=user_entry,
        )

    def _build_bind_dn(self, username: str, config: LdapConfig) -> str:
        """Build the bind DN for LDAP authentication."""
        # Replace {username} placeholder in user_filter or build DN
        if "{username}" in config.user_filter:
            # User filter contains the full DN pattern
            return config.user_filter.replace("{username}", username)
        # Default: uid=username,ou=users,base_dn
        return f"uid={username},{config.bind_dn}"

    def _decrypt_password(self, encrypted: str) -> str | None:
        """Decrypt RSA-encrypted password with fallback for development."""
        # Fast path: if it looks like plain text (short, no base64 chars), return as-is
        # This supports development mode where password is sent unencrypted
        if len(encrypted) < 128 and not self._is_likely_encrypted(encrypted):
            return encrypted

        try:
            import base64

            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.ciphers import algorithms

            # Get RSA private key from settings
            from bisheng.common.services.config_service import settings

            rsa_private_key = getattr(settings, "rsa_private_key", None)
            if not rsa_private_key:
                # Fallback: check for development-only plain password mode
                ldapPlainPassword = getattr(settings, "ldap_plain_password", None)
                if ldapPlainPassword:
                    logger.warning("Using plain password mode - NOT for production")
                    return encrypted
                logger.warning("RSA private key not configured")
                return None

            # Load private key
            private_key = serialization.load_pem_private_key(
                rsa_private_key.encode(),
                password=None,
                backend=default_backend(),
            )

            # Decode encrypted data
            encrypted_bytes = base64.b64decode(encrypted)

            # Decrypt with OAEP padding
            decrypted = private_key.decrypt(
                encrypted_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=algorithms.SHA256()),
                    algorithm=algorithms.SHA256(),
                    label=None,
                ),
            )

            return decrypted.decode()
        except Exception as e:
            logger.exception("Password decryption failed: %s", e)
            return None

    def _is_likely_encrypted(self, data: str) -> bool:
        """Check if string looks like base64 encrypted data."""
        import re

        # Base64 pattern
        base64_pattern = re.compile(r"^[A-Za-z0-9+/]+=*$")
        return bool(base64_pattern.match(data) and len(data) > 32)

    async def _ldap_bind(
        self,
        server_url: str,
        bind_dn: str,
        password: str,
        base_dn: str,
        user_filter: str,
        use_ssl: bool,
        timeout: int,
    ) -> dict | None:
        """Perform LDAP bind and return user attributes."""
        try:
            import ssl

            from ldap3 import ALL, Connection, Server, Tls

            # Create server
            server = Server(server_url, get_info=ALL, connect_timeout=timeout)

            # Create TLS context
            if use_ssl:
                tls = Tls(cafile=None, version=ssl.PROTOCOL_TLS_CLIENT)
            else:
                tls = None

            # Create connection
            conn = Connection(
                server,
                user=bind_dn,
                password=password,
                auto_bind=True,
                tls=tls,
                receive_timeout=timeout,
            )

            if not conn.bound:
                return None

            # Search for user attributes
            search_filter = user_filter.replace("{username}", bind_dn.split(",")[0].split("=")[1])
            conn.search(
                search_base=base_dn,
                search_filter=f"({search_filter})",
                attributes=["uid", "cn", "mail", "mobile", "department"],
            )

            if not conn.entries:
                return None

            entry = conn.entries[0]
            result = {}
            for attr in ["uid", "cn", "mail", "mobile", "department"]:
                if hasattr(entry, attr):
                    result[attr] = getattr(entry, attr).value

            conn.unbind()
            return result

        except Exception as e:
            logger.exception("LDAP bind failed: %s", e)
            if "INVALID_CREDENTIALS" in str(e) or "49" in str(e):
                raise LdapErrorCode.LDAP_AUTH_FAILED.http_exception()
            if "TIMEOUT" in str(e) or "timed out" in str(e).lower():
                raise LdapErrorCode.LDAP_TIMEOUT.http_exception()
            raise LdapErrorCode.LDAP_CONNECTION_FAILED.http_exception()

    async def get_user_attrs(self, auth_result: AuthResult) -> UserAttrs:
        """Extract user attributes from auth result."""
        return auth_result.to_user_attrs()
