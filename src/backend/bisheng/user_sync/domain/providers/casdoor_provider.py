"""Casdoor OIDC Provider implementation."""

import urllib.parse

import httpx

from bisheng.common.errcode.user_sync import OAuthErrorCode
from bisheng.user_sync.domain.providers.oidc_provider import OidcProvider


class CasdoorProvider(OidcProvider):
    """
    Casdoor OIDC Provider.

    Casdoor is an open-source Identity Provider with OIDC support.
    https://casdoor.org/
    """

    source = "casdoor"

    def __init__(self, tenant_id: int):
        super().__init__(tenant_id, "casdoor")
        self._discovery_cache: dict | None = None

    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Generate Casdoor authorization URL."""
        config = await self._load_config()

        discovery = await self.fetch_oidc_discovery()
        authorization_endpoint = discovery.get("authorization_endpoint")

        if not authorization_endpoint:
            raise OAuthErrorCode.OAUTH_CONFIG_NOT_FOUND.http_exception(
                "Casdoor authorization_endpoint not found"
            )

        params = {
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config.scopes or "openid email profile",
            "state": state,
        }

        return f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        config = await self._load_config()

        discovery = await self.fetch_oidc_discovery()
        token_endpoint = discovery.get("token_endpoint")

        if not token_endpoint:
            raise OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.http_exception(
                "Casdoor token_endpoint not found"
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_endpoint,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": config.client_id,
                        "client_secret": config.client_secret_encrypted,
                        "redirect_uri": config.redirect_uri,
                    },
                    timeout=30.0,
                )

                if response.status_code != 200:
                    raise OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.http_exception(
                        f"Casdoor token exchange failed: {response.status_code}"
                    )

                return response.json()

        except OAuthErrorCode:
            raise
        except Exception as e:
            raise OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.http_exception(str(e))

    async def get_userinfo(self, access_token: str) -> dict:
        """Get user info from Casdoor userinfo endpoint."""
        discovery = await self.fetch_oidc_discovery()
        userinfo_endpoint = discovery.get("userinfo_endpoint")

        if not userinfo_endpoint:
            return {}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return response.json()
                return {}

        except Exception as e:
            logger.warning("Casdoor userinfo failed: %s", e)
            return {}

    async def get_oidc_discovery_url(self) -> str:
        """Get Casdoor OIDC discovery URL."""
        config = await self._load_config()
        # Casdoor uses /.well-known/openid-configuration
        base_url = config.config_json.get("endpoint_base") if config.config_json else ""
        if not base_url:
            raise OAuthErrorCode.OAUTH_CONFIG_NOT_FOUND.http_exception(
                "Casdoor endpoint_base not configured"
            )
        return f"{base_url.rstrip('/')}/.well-known/openid-configuration"

    async def fetch_oidc_discovery(self) -> dict:
        """Fetch and cache OIDC discovery document."""
        if self._discovery_cache:
            return self._discovery_cache

        discovery_url = await self.get_oidc_discovery_url()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(discovery_url, timeout=30.0)

                if response.status_code != 200:
                    raise OAuthErrorCode.OAUTH_CONFIG_NOT_FOUND.http_exception(
                        f"Casdoor discovery failed: {response.status_code}"
                    )

                self._discovery_cache = response.json()
                return self._discovery_cache

        except OAuthErrorCode:
            raise
        except Exception as e:
            raise OAuthErrorCode.OAUTH_PROVIDER_DISABLED.http_exception(str(e))

    async def _validate_id_token(self, id_token: str) -> dict:
        """
        Validate Casdoor ID token.

        Casdoor uses JWT for ID tokens.
        We verify using Casdoor's public key from the JWKS endpoint.
        """
        import jwt

        config = await self._load_config()
        discovery = await self.fetch_oidc_discovery()
        jwks_uri = discovery.get("jwks_uri")

        if not jwks_uri:
            raise OAuthErrorCode.OAUTH_STATE_INVALID.http_exception(
                "Casdoor JWKS URI not found"
            )

        try:
            # Fetch JWKS
            async with httpx.AsyncClient() as client:
                jwks_response = await client.get(jwks_uri, timeout=30.0)
                jwks = jwks_response.json()

            # Find the key
            unverified_header = jwt.get_unverified_header(id_token)
            kid = unverified_header.get("kid")

            public_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    from jwt.algorithms import RSAAlgorithm

                    public_key = RSAAlgorithm.from_jwk(key)
                    break

            if not public_key:
                raise OAuthErrorCode.OAUTH_STATE_INVALID.http_exception(
                    "Key not found in JWKS"
                )

            # Verify and decode
            claims = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                audience=config.client_id,
                issuer=discovery.get("issuer"),
            )

            return claims

        except jwt.ExpiredSignatureError:
            raise OAuthErrorCode.OAUTH_STATE_EXPIRED.http_exception()
        except jwt.InvalidTokenError as e:
            raise OAuthErrorCode.OAUTH_STATE_INVALID.http_exception(str(e))
        except Exception as e:
            raise OAuthErrorCode.OAUTH_STATE_INVALID.http_exception(str(e))
