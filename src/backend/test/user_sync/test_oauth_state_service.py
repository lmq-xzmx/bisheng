"""Tests for OAuthStateService."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOAuthStateService:
    """Test OAuthStateService state management."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        with patch('bisheng.user_sync.domain.services.oauth_state_service.get_redis_client') as mock:
            redis_client = AsyncMock()
            redis_client.aset = AsyncMock()
            redis_client.aget = AsyncMock()
            redis_client.delete = AsyncMock()
            mock.return_value = redis_client
            yield redis_client

    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        with patch('bisheng.user_sync.domain.services.oauth_state_service.settings') as mock:
            mock.sso_sync = MagicMock()
            mock.sso_sync.gateway_hmac_secret = 'test-secret-key'
            yield mock

    @pytest.mark.asyncio
    async def test_create_state(self, mock_redis, mock_settings):
        """Test creating an OAuth state token."""
        from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

        state = await OAuthStateService.create(
            provider='google',
            redirect_uri='/workspace',
            tenant_id=1,
        )

        assert state is not None
        assert isinstance(state, str)
        mock_redis.aset.assert_called_once()

        # Verify stored data
        call_args = mock_redis.aset.call_args
        key = call_args[0][0]
        assert key.startswith('oauth:state:')

    @pytest.mark.asyncio
    async def test_verify_and_delete_valid_state(self, mock_redis, mock_settings):
        """Test verifying a valid state token."""
        from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

        # Mock Redis to return valid state data
        state_data = {
            'provider': 'google',
            'redirect_uri': '/workspace',
            'tenant_id': 1,
            'exp': time.time() + 300,
            'sig': 'dummy_sig',  # Will be validated by _compute_signature
        }

        with patch.object(OAuthStateService, '_compute_signature', return_value='valid_sig'):
            # Update state_data with valid signature
            state_data['sig'] = 'valid_sig'
            import json
            mock_redis.aget = AsyncMock(return_value=json.dumps(state_data))

            result = await OAuthStateService.verify_and_delete(state='test_state', provider='google')

            assert result.provider == 'google'
            assert result.tenant_id == 1
            mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_and_delete_expired_state(self, mock_redis, mock_settings):
        """Test verifying an expired state token."""
        from bisheng.common.errcode.user_sync import OAuthErrorCode
        from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

        # Mock Redis to return expired state data
        state_data = {
            'provider': 'google',
            'redirect_uri': '/workspace',
            'tenant_id': 1,
            'exp': time.time() - 100,  # Expired
            'sig': 'dummy_sig',
        }

        with patch.object(OAuthStateService, '_compute_signature', return_value='valid_sig'):
            state_data['sig'] = 'valid_sig'
            import json
            mock_redis.aget = AsyncMock(return_value=json.dumps(state_data))

            with pytest.raises(OAuthErrorCode.OAUTH_STATE_EXPIRED):
                await OAuthStateService.verify_and_delete(state='test_state', provider='google')

    @pytest.mark.asyncio
    async def test_verify_and_delete_missing_state(self, mock_redis):
        """Test verifying a non-existent state token."""
        from bisheng.common.errcode.user_sync import OAuthErrorCode
        from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

        mock_redis.aget = AsyncMock(return_value=None)

        with pytest.raises(OAuthErrorCode.OAUTH_STATE_EXPIRED):
            await OAuthStateService.verify_and_delete(state='nonexistent', provider='google')

    def test_compute_signature(self, mock_settings):
        """Test HMAC signature computation."""
        from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

        state_data = {
            'provider': 'google',
            'tenant_id': 1,
            'exp': 1234567890.0,
        }

        sig1 = OAuthStateService._compute_signature(state_data, 'secret')
        sig2 = OAuthStateService._compute_signature(state_data, 'secret')

        assert sig1 == sig2  # Deterministic
        assert len(sig1) == 64  # SHA256 hex length

        # Different data produces different signature
        state_data2 = {**state_data, 'provider': 'github'}
        sig3 = OAuthStateService._compute_signature(state_data2, 'secret')
        assert sig3 != sig1
