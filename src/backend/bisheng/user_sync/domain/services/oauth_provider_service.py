"""OAuth Provider service - BiSheng as OAuth Authorization Server."""

import secrets
import time
from dataclasses import dataclass
from typing import Optional

import jwt


@dataclass
class OAuthClient:
    """OAuth Client application."""

    client_id: str
    client_secret: str
    redirect_uris: list[str]
    allowed_scopes: list[str]
    enabled: bool = True


@dataclass
class AuthorizationCode:
    """OAuth Authorization Code."""

    code: str
    client_id: str
    user_id: int
    redirect_uri: str
    scopes: list[str]
    expires_at: float
    code_challenge: str | None = None


@dataclass
class TokenResponse:
    """OAuth Token Response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None


class OAuthProviderService:
    """BiSheng as OAuth Provider/Authorization Server."""

    # Token settings
    ACCESS_TOKEN_TTL = 3600  # 1 hour
    REFRESH_TOKEN_TTL = 86400 * 7  # 7 days
    CODE_TTL = 600  # 10 minutes

    def __init__(self):
        self._clients: dict[str, OAuthClient] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._refresh_tokens: dict[str, tuple] = {}  # token -> (user_id, scopes)
        self._jwks_key: dict | None = None

    def register_client(
        self,
        client_id: str,
        client_secret: str,
        redirect_uris: list[str],
        allowed_scopes: list[str],
    ) -> OAuthClient:
        """Register an OAuth client application."""
        client = OAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=redirect_uris,
            allowed_scopes=allowed_scopes,
        )
        self._clients[client_id] = client
        return client

    def get_client(self, client_id: str) -> Optional[OAuthClient]:
        """Get client by ID."""
        return self._clients.get(client_id)

    def validate_client(self, client_id: str, client_secret: str) -> Optional[OAuthClient]:
        """Validate client credentials."""
        client = self._clients.get(client_id)
        if not client or not client.enabled:
            return None
        if client.client_secret != client_secret:
            return None
        return client

    def validate_redirect_uri(self, client: OAuthClient, redirect_uri: str) -> bool:
        """Validate redirect URI matches registered URIs."""
        return redirect_uri in client.redirect_uris

    def validate_scopes(self, client: OAuthClient, scopes: list[str]) -> list[str]:
        """Filter requested scopes against allowed scopes."""
        return [s for s in scopes if s in client.allowed_scopes]

    def create_authorization_code(
        self,
        client_id: str,
        user_id: int,
        redirect_uri: str,
        scopes: list[str],
        code_challenge: str | None = None,
    ) -> str:
        """Create and store an authorization code."""
        code = secrets.token_urlsafe(32)
        self._codes[code] = AuthorizationCode(
            code=code,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
            expires_at=time.time() + self.CODE_TTL,
            code_challenge=code_challenge,
        )
        return code

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenResponse:
        """Exchange authorization code for tokens."""
        # Validate client
        client = self.validate_client(client_id, client_secret)
        if not client:
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid client credentials")

        # Validate redirect URI
        if not self.validate_redirect_uri(client, redirect_uri):
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid redirect URI")

        # Get and validate code
        auth_code = self._codes.pop(code, None)
        if not auth_code:
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid or expired code")

        if auth_code.client_id != client_id or auth_code.redirect_uri != redirect_uri:
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Code mismatch")

        if time.time() > auth_code.expires_at:
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_STATE_EXPIRED.http_exception("Code expired")

        # Generate tokens
        return self._generate_tokens(auth_code.user_id, auth_code.scopes, auth_code.client_id)

    def _generate_tokens(
        self,
        user_id: int,
        scopes: list[str],
        client_id: str,
    ) -> TokenResponse:
        """Generate access and refresh tokens."""
        from bisheng.user.domain.models.user import UserDao
        import json

        # Get user info
        import asyncio
        user = asyncio.get_event_loop().run_until_complete(UserDao.aget_user(user_id))

        # Create access token
        access_payload = {
            "sub": str(user_id),
            "client_id": client_id,
            "scope": " ".join(scopes),
            "iat": time.time(),
            "exp": time.time() + self.ACCESS_TOKEN_TTL,
            "type": "access",
        }
        access_token = self._encode_jwt(access_payload)

        # Create refresh token
        refresh_token = secrets.token_urlsafe(32)
        self._refresh_tokens[refresh_token] = (user_id, scopes)

        return TokenResponse(
            access_token=access_token,
            expires_in=self.ACCESS_TOKEN_TTL,
            refresh_token=refresh_token,
            scope=" ".join(scopes),
        )

    def _encode_jwt(self, payload: dict) -> str:
        """Encode JWT with server's signing key."""
        from bisheng.common.services.config_service import settings

        jwt_secret = getattr(settings, "jwt_secret", "default-secret")
        return jwt.encode(payload, jwt_secret, algorithm="HS256")

    def verify_access_token(self, token: str) -> dict | None:
        """Verify access token and return claims."""
        from bisheng.common.services.config_service import settings

        jwt_secret = getattr(settings, "jwt_secret", "default-secret")
        try:
            return jwt.decode(token, jwt_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def get_userinfo(self, token: str) -> dict | None:
        """Get user info for access token."""
        claims = self.verify_access_token(token)
        if not claims:
            return None

        user_id = int(claims.get("sub", 0))
        if not user_id:
            return None

        from bisheng.user.domain.models.user import UserDao
        import asyncio

        user = asyncio.get_event_loop().run_until_complete(UserDao.aget_user(user_id))
        if not user:
            return None

        return {
            "sub": str(user.user_id),
            "name": user.user_name,
            "email": user.email,
            "phone_number": user.phone_number,
        }


# Global singleton instance
oauth_provider_service = OAuthProviderService()
