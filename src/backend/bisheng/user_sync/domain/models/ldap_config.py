"""LDAP configuration model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, text
from sqlmodel import Field

from bisheng.common.models.base import SQLModelSerializable
from bisheng.core.database.dialect_helpers import JsonType


class LdapConfig(SQLModelSerializable, table=True):
    """LDAP configuration per tenant.

    tenant_id=NULL means global config (fallback when no tenant-specific config).
    """

    __tablename__ = "ldap_config"
    __table_args__ = (UniqueConstraint("tenant_id", name="uk_ldap_tenant"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, index=True)
    enabled: bool = Field(default=False)
    server_url: str = Field(max_length=512)  # ldap:// or ldaps://
    base_dn: str = Field(max_length=256)
    bind_dn: str = Field(max_length=256)
    bind_password_encrypted: str = Field(max_length=512)
    user_filter: str = Field(max_length=512, default="(uid={username})")
    use_ssl: bool = Field(default=True)
    timeout: int = Field(default=30)
    auto_register: bool = Field(default=True)
    sync_strategies: dict = Field(
        default={"email": "first_only", "phone": "first_only", "name": "never"},
        sa_column=Column(JsonType, nullable=True),
    )
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


class LdapConfigDao:
    """DAO for LdapConfig."""

    @classmethod
    async def aget_for_tenant(cls, tenant_id: int) -> LdapConfig | None:
        """Get LDAP config for tenant (tenant config takes precedence over global)."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            # Try tenant-specific config first
            stmt = select(LdapConfig).where(LdapConfig.tenant_id == tenant_id)
            result = await session.exec(stmt)
            config = result.first()

            if config:
                return config

            # Fallback to global config
            stmt = select(LdapConfig).where(LdapConfig.tenant_id.is_(None))
            result = await session.exec(stmt)
            return result.first()

    @classmethod
    async def aupsert(cls, config: LdapConfig) -> LdapConfig:
        """Create or update LDAP config."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            # Check existing
            stmt = select(LdapConfig).where(
                LdapConfig.tenant_id == config.tenant_id
                if config.tenant_id is not None
                else LdapConfig.tenant_id.is_(None)
            )
            result = await session.exec(stmt)
            existing = result.first()

            if existing:
                # Update
                for key, value in config.model_dump(exclude={"id"}).items():
                    setattr(existing, key, value)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return existing
            else:
                # Create
                session.add(config)
                await session.commit()
                await session.refresh(config)
                return config
