"""OAuth Provider base class."""

from abc import abstractmethod
from typing import TYPE_CHECKING

from bisheng.common.errcode.user_sync import OAuthErrorCode
from bisheng.user_sync.domain.models import OAuthProviderConfig, OAuthProviderConfigDao
from bisheng.user_sync.domain.providers.base import AuthResult, UserAttrs, UserSyncProvider

if TYPE_CHECKING:
    from fastapi import Request


class OAuthProvider(UserSyncProvider):
    """Base class for OAuth providers (Google, GitHub, etc.)."""

    def __init__(self, tenant_id: int, provider: str):
        super().__init__(tenant_id)
        self.provider = provider
        self.config = None

    @property
    def source(self) -> str:
        return self.provider

    async def _load_config(self) -> "OAuthProviderConfig":
        """Load OAuth config for this provider with tenant precedence."""
        if self.config is not None:
            return self.config

        config = await OAuthProviderConfigDao.aget_by_provider(self.provider, self.tenant_id)
        if config is None or not config.enabled:
            raise OAuthErrorCode.OAUTH_CONFIG_NOT_FOUND.http_exception()

        self.config = config
        return config

    @abstractmethod
    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Generate OAuth authorization URL."""

    @abstractmethod
    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""

    @abstractmethod
    async def get_user_info(self, access_token: str) -> UserAttrs:
        """Get user info from OAuth provider."""

    async def authenticate_callback(self, code: str) -> AuthResult:
        """
        Authenticate via OAuth callback.

        Exchange code for tokens and fetch user info.
        """
        # Exchange code for tokens
        tokens = await self.exchange_code(code)

        access_token = tokens.get("access_token")
        if not access_token:
            raise OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.http_exception()

        # Get user info
        user_attrs = await self.get_user_info(access_token)

        return AuthResult(
            external_id=user_attrs.external_id,
            name=user_attrs.name,
            email=user_attrs.email,
            phone=user_attrs.phone,
        )

    async def authenticate(self, request: "Request") -> AuthResult:
        """Not used for OAuth - authenticate_callback is used instead."""
        raise NotImplementedError("OAuth uses authenticate_callback instead")

    async def get_user_attrs(self, auth_result: AuthResult) -> UserAttrs:
        """Extract user attributes from auth result."""
        return auth_result.to_user_attrs()
