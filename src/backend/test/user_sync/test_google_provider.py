"""Tests for GoogleProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGoogleProvider:
    """Test Google OAuth provider."""

    @pytest.fixture
    def mock_oauth_config_dao(self):
        """Mock OAuthProviderConfigDao."""
        with patch('bisheng.user_sync.domain.providers.google_provider.OAuthProviderConfigDao') as mock:
            yield mock

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx AsyncClient."""
        with patch('bisheng.user_sync.domain.providers.google_provider.httpx.AsyncClient') as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_get_authorization_url(self, mock_oauth_config_dao):
        """Test generating Google authorization URL."""
        from bisheng.user_sync.domain.providers.google_provider import GoogleProvider

        mock_config = MagicMock()
        mock_config.client_id = 'test_client_id'
        mock_config.enabled = True
        mock_oauth_config_dao.aget_by_provider = AsyncMock(return_value=mock_config)

        provider = GoogleProvider(tenant_id=1)

        auth_url = await provider.get_authorization_url(
            state='test_state',
            redirect_uri='http://localhost/api/v1/oauth/google/callback',
        )

        assert 'accounts.google.com' in auth_url
        assert 'client_id=test_client_id' in auth_url
        assert 'state=test_state' in auth_url
        assert 'scope=openid+email+profile' in auth_url

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, mock_oauth_config_dao, mock_httpx_client):
        """Test exchanging authorization code for tokens."""
        from bisheng.user_sync.domain.providers.google_provider import GoogleProvider

        mock_config = MagicMock()
        mock_config.client_id = 'test_client_id'
        mock_config.client_secret_encrypted = 'test_secret'
        mock_config.redirect_uri = 'http://localhost/api/v1/oauth/google/callback'
        mock_oauth_config_dao.aget_by_provider = AsyncMock(return_value=mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            'access_token': 'test_access_token',
            'token_type': 'Bearer',
        })
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_httpx_client.return_value = mock_client

        provider = GoogleProvider(tenant_id=1)
        tokens = await provider.exchange_code('test_auth_code')

        assert tokens['access_token'] == 'test_access_token'

    @pytest.mark.asyncio
    async def test_get_user_info_success(self, mock_httpx_client):
        """Test fetching user info from Google."""
        from bisheng.user_sync.domain.providers.google_provider import GoogleProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            'id': '123456789',
            'name': 'Test User',
            'email': 'test@example.com',
            'picture': 'https://example.com/photo.jpg',
        })
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_httpx_client.return_value = mock_client

        provider = GoogleProvider(tenant_id=1)
        user_attrs = await provider.get_user_info('test_access_token')

        assert user_attrs.external_id == '123456789'
        assert user_attrs.name == 'Test User'
        assert user_attrs.email == 'test@example.com'


class TestOAuthErrorCode:
    """Test OAuth error codes."""

    def test_error_codes_defined(self):
        """Test all OAuth error codes are properly defined."""
        from bisheng.common.errcode.user_sync import OAuthErrorCode

        assert OAuthErrorCode.OAUTH_PROVIDER_DISABLED.Code == 19201
        assert OAuthErrorCode.OAUTH_AUTH_FAILED.Code == 19202
        assert OAuthErrorCode.OAUTH_STATE_INVALID.Code == 19203
        assert OAuthErrorCode.OAUTH_STATE_EXPIRED.Code == 19204
        assert OAuthErrorCode.OAUTH_TOKEN_EXCHANGE_FAILED.Code == 19205
        assert OAuthErrorCode.OAUTH_USER_INFO_FAILED.Code == 19206
        assert OAuthErrorCode.OAUTH_PROVIDER_NOT_FOUND.Code == 19207
        assert OAuthErrorCode.OAUTH_CONFIG_NOT_FOUND.Code == 19208
