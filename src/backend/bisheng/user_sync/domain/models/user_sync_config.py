"""User sync behavior configuration model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, text
from sqlmodel import Field

from bisheng.common.models.base import SQLModelSerializable
from bisheng.user_sync.domain.constants import SyncStrategy


class UserSyncConfig(SQLModelSerializable, table=True):
    """User sync behavior configuration per tenant per source."""

    __tablename__ = "user_sync_config"
    __table_args__ = (UniqueConstraint("tenant_id", "source", name="uk_usersync_tenant_source"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    source: str = Field(max_length=32, index=True)  # ldap / google / ...
    auto_register: bool = Field(default=True)
    sync_email: SyncStrategy = Field(default=SyncStrategy.FIRST_ONLY)
    sync_phone: SyncStrategy = Field(default=SyncStrategy.FIRST_ONLY)
    sync_name: SyncStrategy = Field(default=SyncStrategy.NEVER)
    sync_department: bool = Field(default=False)
    logout_redirect_oauth: bool = Field(default=False)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
        ),
    )


class UserSyncConfigDao:
    """DAO for UserSyncConfig."""

    @classmethod
    async def aget_for_tenant_source(cls, tenant_id: int, source: str) -> UserSyncConfig | None:
        """Get sync config for tenant + source."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(UserSyncConfig).where(
                UserSyncConfig.tenant_id == tenant_id,
                UserSyncConfig.source == source,
            )
            result = await session.exec(stmt)
            return result.first()

    @classmethod
    async def aupsert(cls, config: UserSyncConfig) -> UserSyncConfig:
        """Create or update sync config."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(UserSyncConfig).where(
                UserSyncConfig.tenant_id == config.tenant_id,
                UserSyncConfig.source == config.source,
            )
            result = await session.exec(stmt)
            existing = result.first()

            if existing:
                for key, value in config.model_dump(exclude={"id"}).items():
                    setattr(existing, key, value)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return existing
            else:
                session.add(config)
                await session.commit()
                await session.refresh(config)
                return config
