"""Tests for UserUpsertService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUserUpsertService:
    """Test UserUpsertService user upsert logic."""

    @pytest.fixture
    def mock_user_dao(self):
        """Mock UserDao."""
        with patch('bisheng.user_sync.domain.services.user_upsert_service.UserDao') as mock:
            yield mock

    @pytest.fixture
    def mock_legacy_rbac(self):
        """Mock LegacyRBACSyncService."""
        with patch('bisheng.user_sync.domain.services.user_upsert_service.LegacyRBACSyncService') as mock:
            mock.sync_user_auth_created = AsyncMock()
            yield mock

    @pytest.fixture
    def mock_user_tenant_dao(self):
        """Mock UserTenantDao."""
        with patch('bisheng.user_sync.domain.services.user_upsert_service.UserTenantDao') as mock:
            mock.aactivate_user_tenant = AsyncMock(return_value=MagicMock(tenant_id=1))
            yield mock

    @pytest.mark.asyncio
    async def test_upsert_user_new_user(self, mock_user_dao, mock_legacy_rbac, mock_user_tenant_dao):
        """Test creating a new user via upsert."""
        from bisheng.user_sync.domain.providers.base import SyncOptions, UserAttrs
        from bisheng.user_sync.domain.services.user_upsert_service import UserUpsertService

        # Mock user not found
        mock_user_dao.aget_by_source_external_id = AsyncMock(return_value=None)
        mock_user_dao.aget_by_external_id = AsyncMock(return_value=None)
        mock_user_dao.add_user_and_default_role = AsyncMock(return_value=MagicMock(
            user_id=1,
            user_name='test_user',
            email='test@example.com',
            source='google',
            external_id='ext123',
            delete=0,
        ))
        mock_user_dao.aupdate_user = AsyncMock()

        user_attrs = UserAttrs(
            external_id='ext123',
            name='test_user',
            email='test@example.com',
        )
        options = SyncOptions(auto_register=True)

        result = await UserUpsertService.upsert_user(
            source='google',
            external_id='ext123',
            user_attrs=user_attrs,
            tenant_id=1,
            options=options,
        )

        assert result.user_name == 'test_user'
        mock_user_dao.add_user_and_default_role.assert_called_once()
        mock_legacy_rbac.sync_user_auth_created.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_user_existing(self, mock_user_dao):
        """Test updating an existing user via upsert."""
        from bisheng.user_sync.domain.providers.base import SyncOptions, UserAttrs
        from bisheng.user_sync.domain.services.user_upsert_service import UserUpsertService

        # Mock existing user
        existing_user = MagicMock(
            user_id=1,
            user_name='existing_user',
            email='old@example.com',
            source='google',
            external_id='ext123',
            delete=0,
        )
        mock_user_dao.aget_by_source_external_id = AsyncMock(return_value=existing_user)
        mock_user_dao.aupdate_user = AsyncMock()

        user_attrs = UserAttrs(
            external_id='ext123',
            name='updated_user',
            email='new@example.com',
        )
        options = SyncOptions(auto_register=True)

        result = await UserUpsertService.upsert_user(
            source='google',
            external_id='ext123',
            user_attrs=user_attrs,
            tenant_id=1,
            options=options,
        )

        assert result.user_name == 'updated_user'
        mock_user_dao.aupdate_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_user_auto_register_disabled(self, mock_user_dao):
        """Test upsert with auto_register=False raises error."""
        from bisheng.common.errcode.user import UserForbiddenError
        from bisheng.user_sync.domain.providers.base import SyncOptions, UserAttrs
        from bisheng.user_sync.domain.services.user_upsert_service import UserUpsertService

        # Mock user not found
        mock_user_dao.aget_by_source_external_id = AsyncMock(return_value=None)
        mock_user_dao.aget_by_external_id = AsyncMock(return_value=None)

        user_attrs = UserAttrs(external_id='ext123', name='test')
        options = SyncOptions(auto_register=False)

        with pytest.raises(UserForbiddenError):
            await UserUpsertService.upsert_user(
                source='google',
                external_id='ext123',
                user_attrs=user_attrs,
                tenant_id=1,
                options=options,
            )

    def test_normalize_contact_field(self):
        """Test contact field normalization."""
        from bisheng.user_sync.domain.services.user_upsert_service import UserUpsertService

        # Test None -> None
        assert UserUpsertService._normalize_contact_field(None) is None

        # Test empty string -> None
        assert UserUpsertService._normalize_contact_field('') is None
        assert UserUpsertService._normalize_contact_field('   ') is None

        # Test valid value
        assert UserUpsertService._normalize_contact_field('  test@example.com  ') == 'test@example.com'
