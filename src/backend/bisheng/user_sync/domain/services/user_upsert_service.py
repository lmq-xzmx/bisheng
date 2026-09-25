"""User upsert service - common logic extracted from sso_sync/LoginSyncService."""

from datetime import datetime

from loguru import logger

from bisheng.database.constants import DefaultRole
from bisheng.database.models.audit_log import AuditLogDao
from bisheng.database.models.tenant import UserTenantDao
from bisheng.database.models.user import User, UserDao
from bisheng.permission.domain.services.legacy_rbac_sync_service import LegacyRBACSyncService
from bisheng.tenant.domain.constants import TenantAuditAction
from bisheng.user_sync.domain.providers.base import SyncOptions, UserAttrs


class UserUpsertService:
    """Common user upsert logic for LDAP/OAuth providers."""

    @classmethod
    async def upsert_user(
        cls,
        source: str,
        external_id: str,
        user_attrs: UserAttrs,
        tenant_id: int,
        options: SyncOptions,
    ) -> User:
        """
        Upsert a user from LDAP/OAuth source.

        Args:
            source: Auth source (ldap, google, github, etc.)
            external_id: Unique identifier from auth source
            user_attrs: User attributes to apply
            tenant_id: Tenant ID
            options: Sync behavior options
        """
        # Try to find existing user by source + external_id
        user = await UserDao.aget_by_source_external_id(source, external_id)

        if user is None:
            # Try to find by external_id only (cross-source adoption)
            legacy = await UserDao.aget_by_external_id(external_id)
            if legacy is not None:
                # Adopt the legacy user
                user = await cls._adopt_legacy_user(legacy, source, user_attrs, tenant_id)
            else:
                # Create new user
                if not options.auto_register:
                    from bisheng.common.errcode.user import UserForbiddenError

                    raise UserForbiddenError.http_exception("Auto registration is disabled")
                user = await cls._create_new_user(source, external_id, user_attrs, tenant_id)
        else:
            # Update existing user
            user = await cls._update_existing_user(user, user_attrs, options)

        return user

    @classmethod
    async def _adopt_legacy_user(
        cls,
        legacy: User,
        source: str,
        user_attrs: UserAttrs,
        tenant_id: int,
    ) -> User:
        """Adopt a local user to this auth source."""
        old_source = legacy.source
        logger.info(
            "Adopting legacy user user_id=%s from source=%s to source=%s external_id=%s",
            legacy.user_id,
            old_source,
            source,
            legacy.external_id,
        )

        legacy.source = source
        cls._apply_user_attrs(legacy, user_attrs)
        cls._touch_user_sync_time(legacy)
        await UserDao.aupdate_user(legacy)

        # Write migration audit
        await AuditLogDao.ainsert_v2(
            tenant_id=tenant_id,
            operator_id=0,
            operator_tenant_id=tenant_id,
            action=TenantAuditAction.USER_SOURCE_MIGRATED.value,
            target_type="user",
            target_id=str(legacy.user_id),
            metadata={
                "old_source": old_source,
                "new_source": source,
                "external_id": legacy.external_id,
                "via": "user_sync_realtime",
            },
        )

        return legacy

    @classmethod
    async def _create_new_user(
        cls,
        source: str,
        external_id: str,
        user_attrs: UserAttrs,
        tenant_id: int,
    ) -> User:
        """Create a new user from auth source."""
        new_user = User(
            user_name=(user_attrs.name.strip() if user_attrs.name else "") or external_id,
            email=cls._normalize_contact_field(user_attrs.email),
            phone_number=cls._normalize_contact_field(user_attrs.phone),
            external_id=external_id,
            source=source,
            password="",  # No password for SSO/OAuth users
            delete=0,
        )
        try:
            user = await UserDao.add_user_and_default_role(new_user)
            await LegacyRBACSyncService.sync_user_auth_created(
                user.user_id,
                [DefaultRole],
            )
            # Pre-activate user_tenant for ROOT_TENANT_ID
            await UserTenantDao.aactivate_user_tenant(user.user_id, tenant_id)
            logger.info(
                "UserSync new user created: user_id=%s external_id=%s source=%s tenant_id=%s",
                user.user_id,
                external_id,
                source,
                tenant_id,
            )
            return user
        except Exception as e:
            logger.error("UserSync could not create user %s: %s", external_id, e)
            from bisheng.common.errcode.user_sync import OAuthErrorCode

            raise OAuthErrorCode.OAUTH_USER_INFO_FAILED.http_exception(f"failed to create user: {e}")

    @classmethod
    async def _update_existing_user(
        cls,
        user: User,
        user_attrs: UserAttrs,
        options: SyncOptions,
    ) -> User:
        """Update an existing user based on sync strategy."""
        cls._apply_user_attrs(user, user_attrs, options)
        cls._touch_user_sync_time(user)
        await UserDao.aupdate_user(user)
        return user

    @classmethod
    def _apply_user_attrs(cls, user: User, attrs: UserAttrs, options: SyncOptions | None = None) -> None:
        """Apply user attributes based on sync strategy."""
        if options is None:
            options = SyncOptions()

        # Name sync
        if attrs.name and options.sync_name != "never":
            nm = attrs.name.strip()
            if nm and user.user_name != nm:
                user.user_name = nm

        # Email sync
        if attrs.email is not None and options.sync_email != "never":
            ne = cls._normalize_contact_field(attrs.email)
            if user.email != ne:
                user.email = ne

        # Phone sync
        if attrs.phone is not None and options.sync_phone != "never":
            np = cls._normalize_contact_field(attrs.phone)
            if user.phone_number != np:
                user.phone_number = np

    @staticmethod
    def _normalize_contact_field(val: str | None) -> str | None:
        """Strip; empty string → None."""
        if val is None:
            return None
        s = val.strip()
        return s if s else None

    @classmethod
    def _touch_user_sync_time(cls, user: User) -> None:
        """Mark sync time."""
        user.update_time = datetime.now()
