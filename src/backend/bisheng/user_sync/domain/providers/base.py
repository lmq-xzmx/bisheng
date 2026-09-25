"""UserSyncProvider ABC - unified authentication provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

    from bisheng.database.models.user import User


@dataclass
class AuthResult:
    """Authentication result from a provider."""

    external_id: str  # Unique identifier from the auth source
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    department: str | None = None  # Department name from auth source
    raw_attributes: dict | None = None  # Raw attributes from auth source

    def to_user_attrs(self) -> "UserAttrs":
        return UserAttrs(
            external_id=self.external_id,
            name=self.name,
            email=self.email,
            phone=self.phone,
            department=self.department,
        )


@dataclass
class UserAttrs:
    """User attributes for sync."""

    external_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    department: str | None = None


@dataclass
class SyncOptions:
    """Options for user sync behavior."""

    auto_register: bool = True
    sync_email: str = "first_only"  # SyncStrategy value
    sync_phone: str = "first_only"
    sync_name: str = "never"
    sync_department: bool = False
    logout_redirect_oauth: bool = False

    @classmethod
    async def from_config(cls, tenant_id: int, source: str) -> "SyncOptions":
        """Load sync options from database config."""
        from bisheng.user_sync.domain.models import UserSyncConfigDao

        config = await UserSyncConfigDao.aget_for_tenant_source(tenant_id, source)
        if config:
            return cls(
                auto_register=config.auto_register,
                sync_email=config.sync_email.value if hasattr(config.sync_email, "value") else config.sync_email,
                sync_phone=config.sync_phone.value if hasattr(config.sync_phone, "value") else config.sync_phone,
                sync_name=config.sync_name.value if hasattr(config.sync_name, "value") else config.sync_name,
                sync_department=config.sync_department,
                logout_redirect_oauth=config.logout_redirect_oauth,
            )
        # Default options
        return cls()


class UserSyncProvider(ABC):
    """Abstract base class for user sync providers (LDAP, OAuth, etc.)."""

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    @property
    @abstractmethod
    def source(self) -> str:
        """Authentication source identifier: ldap / google / github / wechat / alipay."""

    @abstractmethod
    async def authenticate(self, request: "Request") -> AuthResult:
        """
        Authenticate a user request.

        - LDAP: Bind the user credentials
        - OAuth: Exchange code for token and validate
        """

    async def sync_user(
        self,
        external_id: str,
        user_attrs: UserAttrs,
        options: SyncOptions | None = None,
    ) -> tuple["User", str]:
        """
        Sync user to local database and issue JWT.

        Returns: (User, access_token)
        """
        from bisheng.user.domain.services.auth import AuthJwt
        from bisheng.user_sync.domain.services.user_upsert_service import UserUpsertService

        if options is None:
            options = await SyncOptions.from_config(self.tenant_id, self.source)

        # Upsert user
        user = await UserUpsertService.upsert_user(
            source=self.source,
            external_id=external_id,
            user_attrs=user_attrs,
            tenant_id=self.tenant_id,
            options=options,
        )

        # Issue JWT
        token = AuthJwt.create_access_token(user)

        return user, token
