"""Tests for LdapProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLdapProvider:
    """Test LdapProvider authentication."""

    @pytest.fixture
    def mock_ldap_config_dao(self):
        """Mock LdapConfigDao."""
        with patch('bisheng.user_sync.domain.providers.ldap_provider.LdapConfigDao') as mock:
            yield mock

    @pytest.fixture
    def mock_sync_options(self):
        """Mock SyncOptions."""
        with patch('bisheng.user_sync.domain.providers.ldap_provider.SyncOptions') as mock:
            mock.from_config = AsyncMock(return_value=MagicMock(
                auto_register=True,
                sync_email='first_only',
                sync_phone='first_only',
                sync_name='never',
                sync_department=False,
            ))
            yield mock

    @pytest.mark.asyncio
    async def test_authenticate_no_config(self, mock_ldap_config_dao):
        """Test authenticate raises error when LDAP not configured."""
        from bisheng.common.errcode.user_sync import LdapErrorCode
        from bisheng.user_sync.domain.providers.ldap_provider import LdapProvider

        mock_ldap_config_dao.aget_for_tenant = AsyncMock(return_value=None)

        provider = LdapProvider(tenant_id=1)

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            'username': 'testuser',
            'password': 'encrypted_password',
        })

        with pytest.raises(LdapErrorCode.LDAP_CONFIG_NOT_FOUND):
            await provider.authenticate(mock_request)

    @pytest.mark.asyncio
    async def test_decrypt_password_no_key(self):
        """Test password decryption returns None when no RSA key configured."""
        from bisheng.user_sync.domain.providers.ldap_provider import LdapProvider

        provider = LdapProvider(tenant_id=1)

        with patch('bisheng.user_sync.domain.providers.ldap_provider.settings') as mock_settings:
            mock_settings.rsa_private_key = None

            result = provider._decrypt_password('encrypted_data')
            assert result is None

    def test_build_bind_dn_default(self):
        """Test building bind DN from username and config."""
        from bisheng.user_sync.domain.models.ldap_config import LdapConfig
        from bisheng.user_sync.domain.providers.ldap_provider import LdapProvider

        provider = LdapProvider(tenant_id=1)

        config = LdapConfig(
            bind_dn='ou=users,dc=example,dc=com',
            user_filter='(uid={username})',
        )

        bind_dn = provider._build_bind_dn('testuser', config)
        assert bind_dn == 'uid=testuser,ou=users,dc=example,dc=com'

    def test_build_bind_dn_custom_filter(self):
        """Test building bind DN with custom user filter."""
        from bisheng.user_sync.domain.models.ldap_config import LdapConfig
        from bisheng.user_sync.domain.providers.ldap_provider import LdapProvider

        provider = LdapProvider(tenant_id=1)

        config = LdapConfig(
            bind_dn='ou=users,dc=example,dc=com',
            user_filter='(sAMAccountName={username})',
        )

        bind_dn = provider._build_bind_dn('testuser', config)
        assert bind_dn == 'uid=testuser,ou=users,dc=example,dc=com'


class TestLdapErrorCode:
    """Test LDAP error codes."""

    def test_error_codes_defined(self):
        """Test all LDAP error codes are properly defined."""
        from bisheng.common.errcode.user_sync import LdapErrorCode

        assert LdapErrorCode.LDAP_CONNECTION_FAILED.Code == 19101
        assert LdapErrorCode.LDAP_AUTH_FAILED.Code == 19102
        assert LdapErrorCode.LDAP_USER_NOT_FOUND.Code == 19103
        assert LdapErrorCode.LDAP_USER_DISABLED.Code == 19104
        assert LdapErrorCode.LDAP_CONFIG_NOT_FOUND.Code == 19105
        assert LdapErrorCode.LDAP_TIMEOUT.Code == 19106
        assert LdapErrorCode.LDAP_INVALID_CONFIG.Code == 19107
