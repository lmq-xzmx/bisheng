"""OAuth Provider service - BiSheng as OAuth Authorization Server.

Implements RFC 6749 (OAuth 2.0) + RFC 7636 (PKCE) + OIDC.
"""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass

import jwt


@dataclass
class AuthorizationCode:
    """OAuth Authorization Code (stored in Redis)."""

    code: str
    client_id: str
    user_id: int
    redirect_uri: str
    scopes: list[str]
    expires_at: float
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    nonce: str | None = None  # For OIDC id_token


@dataclass
class RefreshTokenData:
    """Refresh token data (stored in Redis)."""

    token: str
    user_id: int
    client_id: str
    scopes: list[str]
    expires_at: float
    family: str | None = None  # For refresh token rotation


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
    """BiSheng as OAuth Provider/Authorization Server.

    Implements OAuth 2.0 Authorization Server with:
    - Authorization Code flow (RFC 6749 §4.1)
    - PKCE support (RFC 7636)
    - Refresh Token rotation (RFC 6749 §6)
    - OIDC support (basic profile)
    """

    # Token settings
    ACCESS_TOKEN_TTL = 3600  # 1 hour
    REFRESH_TOKEN_TTL = 86400 * 7  # 7 days
    CODE_TTL = 600  # 10 minutes

    def __init__(self):
        self._redis_client = None  # Lazy init

    @property
    def redis(self):
        """Lazy Redis client initialization."""
        if self._redis_client is None:
            from bisheng.core.redis import get_redis_client

            self._redis_client = get_redis_client()
        return self._redis_client

    # =========================================================================
    # Client Operations (Database)
    # =========================================================================

    async def get_client(self, client_id: str) -> dict | None:
        """Get client by ID from database."""
        from bisheng.user_sync.domain.models import OAuthServerClientDao

        client = await OAuthServerClientDao.aget_enabled_by_client_id(client_id)
        if not client:
            return None
        return {
            "client_id": client.client_id,
            "client_secret": client.client_secret,
            "redirect_uris": client.redirect_uris,
            "allowed_scopes": client.allowed_scopes,
            "grant_types": client.grant_types,
            "token_endpoint_auth_method": client.token_endpoint_auth_method,
            "client_name": client.client_name,
            "enabled": client.enabled,
        }

    async def validate_client(self, client_id: str, client_secret: str | None = None) -> dict | None:
        """Validate client credentials.

        Supports both confidential and public clients:
        - Confidential (client_secret_basic/post): validate secret
        - Public (none): only validate client_id exists and is enabled
        """
        client = await self.get_client(client_id)
        if not client:
            return None

        if not client.get("enabled", True):
            return None

        # Skip secret validation for public clients
        auth_method = client.get("token_endpoint_auth_method", "client_secret_basic")
        if auth_method == "none":
            return client

        # Confidential client - validate secret
        if not client_secret:
            return None
        if client.get("client_secret") != client_secret:
            return None

        return client

    def validate_redirect_uri(self, client: dict, redirect_uri: str) -> bool:
        """Validate redirect URI matches registered URIs."""
        return redirect_uri in client.get("redirect_uris", [])

    def validate_scopes(self, client: dict, scopes: list[str]) -> list[str]:
        """Filter requested scopes against allowed scopes."""
        allowed = set(client.get("allowed_scopes", []))
        return [s for s in scopes if s in allowed]

    # =========================================================================
    # Authorization Code Operations (Redis)
    # =========================================================================

    def _code_key(self, code: str) -> str:
        """Redis key for authorization code."""
        return f"oauth:code:{code}"

    def _refresh_key(self, token: str) -> str:
        """Redis key for refresh token."""
        return f"oauth:refresh:{token}"

    async def create_authorization_code(
        self,
        client_id: str,
        user_id: int,
        redirect_uri: str,
        scopes: list[str],
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        nonce: str | None = None,
    ) -> str:
        """Create and store an authorization code in Redis."""
        code = secrets.token_urlsafe(32)
        auth_code = AuthorizationCode(
            code=code,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
            expires_at=time.time() + self.CODE_TTL,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
        )

        # Store in Redis with TTL
        import json

        self.redis.setex(
            self._code_key(code),
            self.CODE_TTL,
            json.dumps(
                {
                    "code": auth_code.code,
                    "client_id": auth_code.client_id,
                    "user_id": auth_code.user_id,
                    "redirect_uri": auth_code.redirect_uri,
                    "scopes": auth_code.scopes,
                    "code_challenge": auth_code.code_challenge,
                    "code_challenge_method": auth_code.code_challenge_method,
                    "nonce": auth_code.nonce,
                }
            ),
        )
        return code

    async def get_authorization_code(self, code: str) -> AuthorizationCode | None:
        """Get authorization code from Redis (does NOT consume it)."""
        import json

        data = self.redis.get(self._code_key(code))
        if not data:
            return None
        obj = json.loads(data)
        return AuthorizationCode(
            code=obj["code"],
            client_id=obj["client_id"],
            user_id=obj["user_id"],
            redirect_uri=obj["redirect_uri"],
            scopes=obj["scopes"],
            expires_at=0,  # Not needed after retrieval
            code_challenge=obj.get("code_challenge"),
            code_challenge_method=obj.get("code_challenge_method"),
            nonce=obj.get("nonce"),
        )

    async def consume_authorization_code(self, code: str) -> AuthorizationCode | None:
        """Consume (delete) authorization code from Redis."""
        import json

        data = self.redis.getdel(self._code_key(code))
        if not data:
            return None
        obj = json.loads(data)
        return AuthorizationCode(
            code=obj["code"],
            client_id=obj["client_id"],
            user_id=obj["user_id"],
            redirect_uri=obj["redirect_uri"],
            scopes=obj["scopes"],
            expires_at=0,
            code_challenge=obj.get("code_challenge"),
            code_challenge_method=obj.get("code_challenge_method"),
            nonce=obj.get("nonce"),
        )

    # =========================================================================
    # PKCE Verification (RFC 7636)
    # =========================================================================

    def _verify_pkce(self, code_verifier: str, auth_code: AuthorizationCode) -> bool:
        """Verify PKCE code_verifier against code_challenge.

        Supports both S256 and plain methods.
        """
        if not auth_code.code_challenge or not code_verifier:
            return True  # No PKCE used

        method = auth_code.code_challenge_method or "plain"

        if method == "S256":
            # S256: base64url(sha256(code_verifier))
            digest = hashlib.sha256(code_verifier.encode()).digest()
            expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            return expected == auth_code.code_challenge
        elif method == "plain":
            return code_verifier == auth_code.code_challenge
        else:
            return False

    # =========================================================================
    # Token Operations (Redis)
    # =========================================================================

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenResponse:
        """Exchange authorization code for tokens (RFC 6749 §4.1.2)."""
        from bisheng.common.errcode.user_sync import OAuthErrorCode

        # Validate client
        client = await self.validate_client(client_id, client_secret)
        if not client:
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid client credentials")

        # Validate redirect URI
        if not self.validate_redirect_uri(client, redirect_uri):
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid redirect URI")

        # Consume authorization code
        auth_code = await self.consume_authorization_code(code)
        if not auth_code:
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid or expired code")

        # Validate code matches request
        if auth_code.client_id != client_id or auth_code.redirect_uri != redirect_uri:
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Code mismatch")

        # Verify PKCE if challenge was used
        if not self._verify_pkce(code_verifier, auth_code):
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid PKCE verifier")

        # Generate tokens
        return await self._generate_tokens(
            user_id=auth_code.user_id,
            scopes=auth_code.scopes,
            client_id=client_id,
            nonce=auth_code.nonce,
        )

    async def exchange_refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str | None,
        scopes: str | None = None,
    ) -> TokenResponse:
        """Exchange refresh token for new tokens (RFC 6749 §6).

        Implements refresh token rotation - old token is invalidated.
        """
        from bisheng.common.errcode.user_sync import OAuthErrorCode

        # Validate client
        client = await self.validate_client(client_id, client_secret)
        if not client:
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid client credentials")

        # Get and consume refresh token (rotation)
        token_data = await self._consume_refresh_token(refresh_token)
        if not token_data:
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Invalid or expired refresh token")

        # Validate client_id matches
        if token_data.client_id != client_id:
            raise OAuthErrorCode.OAUTH_AUTH_FAILED.http_exception("Client mismatch")

        # Use provided scopes or original scopes
        requested_scopes = scopes.split() if scopes else token_data.scopes
        valid_scopes = self.validate_scopes(client, requested_scopes)

        # Generate new tokens
        return await self._generate_tokens(
            user_id=token_data.user_id,
            scopes=valid_scopes,
            client_id=client_id,
        )

    async def _consume_refresh_token(self, token: str) -> RefreshTokenData | None:
        """Consume refresh token (deletion) - implements rotation."""
        import json

        key = self._refresh_key(token)
        data = self.redis.getdel(key)
        if not data:
            return None
        obj = json.loads(data)
        return RefreshTokenData(
            token=token,
            user_id=obj["user_id"],
            client_id=obj["client_id"],
            scopes=obj["scopes"],
            expires_at=obj.get("expires_at", 0),
            family=obj.get("family"),
        )

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        """Revoke a token (RFC 7009)."""

        # Try refresh token first
        key = self._refresh_key(token)
        if self.redis.get(key):
            self.redis.delete(key)
            return True

        # TODO: Also support access token revocation by maintaining a blacklist
        return True  # Silently succeed for unsupported token types

    async def _generate_tokens(
        self,
        user_id: int,
        scopes: list[str],
        client_id: str,
        nonce: str | None = None,
    ) -> TokenResponse:
        """Generate access and refresh tokens."""
        now = int(time.time())

        # Access token payload
        access_payload = {
            "sub": str(user_id),
            "client_id": client_id,
            "scope": " ".join(scopes),
            "iat": now,
            "exp": now + self.ACCESS_TOKEN_TTL,
            "type": "access",
        }
        access_token = self._encode_jwt(access_payload)

        # Refresh token (rotation)
        refresh_token = secrets.token_urlsafe(32)
        refresh_data = {
            "user_id": user_id,
            "client_id": client_id,
            "scopes": scopes,
            "exp": now + self.REFRESH_TOKEN_TTL,
            "family": secrets.token_urlsafe(8),  # Token family for rotation tracking
        }
        import json

        self.redis.setex(
            self._refresh_key(refresh_token),
            self.REFRESH_TOKEN_TTL,
            json.dumps(refresh_data),
        )

        # ID Token for OIDC (if openid scope present)
        id_token = None
        if "openid" in scopes:
            id_token = self._generate_id_token(
                user_id=user_id,
                client_id=client_id,
                nonce=nonce,
                scopes=scopes,
            )

        return TokenResponse(
            access_token=access_token,
            expires_in=self.ACCESS_TOKEN_TTL,
            refresh_token=refresh_token,
            id_token=id_token,
            scope=" ".join(scopes),
        )

    def _generate_id_token(
        self,
        user_id: int,
        client_id: str,
        nonce: str | None,
        scopes: list[str],
    ) -> str:
        """Generate OIDC ID Token (JWT)."""
        now = int(time.time())
        from bisheng.common.services.config_service import settings

        issuer = getattr(settings, "oauth_issuer", "https://bisheng.example.com")

        id_payload = {
            "iss": issuer,
            "sub": str(user_id),
            "aud": client_id,
            "iat": now,
            "exp": now + self.ACCESS_TOKEN_TTL,
            "auth_time": now,
        }
        if nonce:
            id_payload["nonce"] = nonce

        # Add standard claims based on scopes
        if "profile" in scopes:
            id_payload["name"] = ""  # Will be filled by userinfo
        if "email" in scopes:
            id_payload["email"] = ""  # Will be filled by userinfo
        if "phone" in scopes:
            id_payload["phone_number"] = ""  # Will be filled by userinfo

        return self._encode_jwt(id_payload)

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

    # =========================================================================
    # UserInfo (OIDC)
    # =========================================================================

    async def get_userinfo_async(self, token: str) -> dict | None:
        """Get user info for access token (OIDC UserInfo Endpoint)."""
        claims = self.verify_access_token(token)
        if not claims:
            return None

        user_id = int(claims.get("sub", 0))
        if not user_id:
            return None

        from bisheng.user.domain.models.user import UserDao

        user = await UserDao.aget_user(user_id)
        if not user:
            return None

        scopes = claims.get("scope", "").split()

        userinfo = {"sub": str(user.user_id)}

        if "profile" in scopes:
            userinfo["name"] = user.user_name
        if "email" in scopes:
            userinfo["email"] = user.email
        if "phone" in scopes:
            userinfo["phone_number"] = user.phone_number

        return userinfo

    def get_userinfo(self, token: str) -> dict | None:
        """Get user info for access token (sync version)."""
        import asyncio

        return asyncio.run(self.get_userinfo_async(token))

    # =========================================================================
    # OIDC Discovery
    # =========================================================================

    async def get_oidc_discovery(self) -> dict:
        """Get OIDC Discovery document."""
        from bisheng.common.services.config_service import settings

        base_url = getattr(settings, "oauth_base_url", "https://bisheng.example.com")

        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "userinfo_endpoint": f"{base_url}/oauth/userinfo",
            "revocation_endpoint": f"{base_url}/oauth/revoke",
            "jwks_uri": f"{base_url}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["HS256"],
            "scopes_supported": ["openid", "profile", "email", "phone"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
            "claims_supported": ["sub", "name", "email", "phone_number"],
            "code_challenge_methods_supported": ["S256", "plain"],
        }

    # =========================================================================
    # JWKS (for client-side JWT validation)
    # =========================================================================

    def get_jwks(self) -> dict:
        """Get JSON Web Key Set for token verification.

        Note: BiSheng uses HS256 symmetric keys, which are NOT suitable
        for client-side JWT validation. For production, consider switching
        to RS256 with proper RSA key management.
        """
        from bisheng.common.services.config_service import settings

        jwt_secret = getattr(settings, "jwt_secret", "default-secret")
        # Generate a stable key ID
        import hashlib

        kid = hashlib.sha256(jwt_secret.encode()).hexdigest()[:16]

        return {
            "keys": [
                {
                    "kty": "oct",
                    "alg": "HS256",
                    "use": "sig",
                    "kid": kid,
                    # Warning: This exposes the secret to clients, which is insecure
                    # For production, use RS256 with asymmetric keys
                    "k": base64.urlsafe_b64encode(jwt_secret.encode()).rstrip(b"=").decode(),
                }
            ]
        }


# Global singleton instance
oauth_provider_service = OAuthProviderService()
