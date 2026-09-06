"""OAuth Provider configuration model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, text
from sqlmodel import Field

from bisheng.common.models.base import SQLModelSerializable
from bisheng.core.database.dialect_helpers import JsonType


class OAuthProviderConfig(SQLModelSerializable, table=True):
    """OAuth Provider configuration per tenant.

    tenant_id=NULL means global config (fallback when no tenant-specific config).
    """

    __tablename__ = "oauth_provider_config"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uk_oauth_tenant_provider"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, index=True)
    provider: str = Field(max_length=32, index=True)  # google/github/wechat/alipay
    enabled: bool = Field(default=False)
    client_id: str = Field(max_length=256)
    client_secret_encrypted: str = Field(max_length=512)
    redirect_uri: str = Field(max_length=512)
    scopes: str = Field(default="openid email profile")
    config_json: dict = Field(default={}, sa_column=Column(JsonType, nullable=True))
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


class OAuthProviderConfigDao:
    """DAO for OAuthProviderConfig."""

    @classmethod
    async def aget_by_provider(cls, provider: str, tenant_id: int) -> OAuthProviderConfig | None:
        """Get config by provider and tenant_id (tenant config takes precedence)."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            # Try tenant-specific config first
            stmt = select(OAuthProviderConfig).where(
                OAuthProviderConfig.provider == provider,
                OAuthProviderConfig.tenant_id == tenant_id,
            )
            result = await session.exec(stmt)
            config = result.first()

            if config:
                return config

            # Fallback to global config
            stmt = select(OAuthProviderConfig).where(
                OAuthProviderConfig.provider == provider,
                OAuthProviderConfig.tenant_id.is_(None),
            )
            result = await session.exec(stmt)
            return result.first()

    @classmethod
    async def alist_enabled_for_tenant(cls, tenant_id: int) -> list[OAuthProviderConfig]:
        """List all enabled providers for a tenant (including global)."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = (
                select(OAuthProviderConfig)
                .where(
                    OAuthProviderConfig.enabled,
                )
                .where((OAuthProviderConfig.tenant_id == tenant_id) | (OAuthProviderConfig.tenant_id.is_(None)))
            )
            result = await session.exec(stmt)
            return list(result.all())

    @classmethod
    async def acreate(cls, config: OAuthProviderConfig) -> OAuthProviderConfig:
        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            session.add(config)
            await session.commit()
            await session.refresh(config)
            return config

    @classmethod
    async def aupdate(cls, config: OAuthProviderConfig) -> OAuthProviderConfig:
        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            session.add(config)
            await session.commit()
            await session.refresh(config)
            return config

    @classmethod
    async def adelete(cls, config_id: int) -> bool:
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(OAuthProviderConfig).where(OAuthProviderConfig.id == config_id)
            result = await session.exec(stmt)
            config = result.first()
            if config:
                await session.delete(config)
                await session.commit()
                return True
            return False
