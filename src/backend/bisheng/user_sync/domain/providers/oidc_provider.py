"""OIDC Provider base class for Casdoor/Keycloak/etc."""

from abc import abstractmethod
from typing import TYPE_CHECKING

from loguru import logger

from bisheng.user_sync.domain.providers.oauth_provider import OAuthProvider

if TYPE_CHECKING:
    pass


class OidcProvider(OAuthProvider):
    """
    Base class for OIDC providers (Casdoor, Keycloak, etc.).

    OIDC is built on OAuth2.0 with an ID Token layer.
    This extends OAuthProvider with OIDC-specific features.
    """

    @property
    def source(self) -> str:
        return f"oidc_{self.provider}"

    @abstractmethod
    async def get_oidc_discovery_url(self) -> str:
        """Get the OIDC discovery document URL (.well-known/openid-configuration)."""

    @abstractmethod
    async def fetch_oidc_discovery(self) -> dict:
        """Fetch and cache the OIDC discovery document."""

    @abstractmethod
    async def get_userinfo(self, access_token: str) -> dict:
        """Get user info from the IdP userinfo endpoint."""

    async def authenticate_callback(self, code: str) -> "AuthResult":
        """
        Authenticate via OIDC callback.

        OIDC flow:
        1. Exchange code for tokens (includes id_token)
        2. Validate id_token signature
        3. Extract user info from id_token claims
        """
        # Exchange code for tokens
        tokens = await self.exchange_code(code)

        id_token = tokens.get("id_token")
        if not id_token:
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.http_exception(
                "No ID token received"
            )

        # Validate and decode the ID token
        claims = await self._validate_id_token(id_token)

        # Get user info (optional, for additional claims)
        access_token = tokens.get("access_token", "")
        userinfo = {}
        try:
            userinfo = await self.get_userinfo(access_token)
        except Exception as e:
            logger.warning("Failed to fetch userinfo: %s", e)

        # Merge claims from id_token and userinfo
        email = claims.get("email") or userinfo.get("email", "")
        name = claims.get("name") or userinfo.get("name", "")
        sub = claims.get("sub") or userinfo.get("sub", "")

        # Use email as external_id if sub not available
        external_id = sub or email
        if not external_id:
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_USER_INFO_FAILED.http_exception(
                "No identifier found in ID token or userinfo"
            )

        return AuthResult(
            external_id=external_id,
            name=name,
            email=email,
            phone=userinfo.get("phone_number") or claims.get("phone_number"),
        )

    @abstractmethod
    async def _validate_id_token(self, id_token: str) -> dict:
        """
        Validate the ID token and return claims.

        Should verify:
        - Signature using IdP's public key (JWKS)
        - Issuer matches
        - Audience matches
        - Expiration
        """

    async def get_user_attrs(self, auth_result: "AuthResult") -> "UserAttrs":
        """Extract user attributes from auth result."""
        return auth_result.to_user_attrs()


# Re-export AuthResult for convenience
from bisheng.user_sync.domain.providers.base import AuthResult, UserAttrs
