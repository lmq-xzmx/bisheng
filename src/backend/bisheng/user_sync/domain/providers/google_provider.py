"""Google OAuth Provider implementation."""

import urllib.parse

import httpx

from bisheng.common.errcode.user_sync import OAuthErrorCode
from bisheng.user_sync.domain.providers.base import UserAttrs
from bisheng.user_sync.domain.providers.oauth_provider import OAuthProvider


class GoogleProvider(OAuthProvider):
    """Google OAuth2 provider."""

    source = "google"

    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Generate Google OAuth authorization URL."""
        config = await self._load_config()

        params = {
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config.scopes or "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }

        return f"{self.AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        config = await self._load_config()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": config.client_id,
                        "client_secret": config.client_secret_encrypted,
                        "redirect_uri": config.redirect_uri,
                        "grant_type": "authorization_code",
                    },
                    timeout=30.0,
                )

                if response.status_code != 200:
                    raise OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.http_exception(
                        f"Google token exchange failed: {response.status_code}"
                    )

                return response.json()

        except OAuthErrorCode:
            raise
        except Exception as e:
            raise OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.http_exception(str(e))

    async def get_user_info(self, access_token: str) -> UserAttrs:
        """Get user info from Google."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code != 200:
                    raise OAuthErrorCode.OAUTH_USER_INFO_FAILED.http_exception(
                        f"Google userinfo failed: {response.status_code}"
                    )

                data = response.json()

                return UserAttrs(
                    external_id=data.get("id") or data.get("email", ""),
                    name=data.get("name"),
                    email=data.get("email"),
                    phone=None,  # Google doesn't provide phone
                )

        except OAuthErrorCode:
            raise
        except Exception as e:
            raise OAuthErrorCode.OAUTH_USER_INFO_FAILED.http_exception(str(e))
