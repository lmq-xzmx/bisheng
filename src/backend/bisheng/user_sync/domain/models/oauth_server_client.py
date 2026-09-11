"""OAuth Server Client model - BiSheng as OAuth Authorization Server."""

import secrets
import time
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, UniqueConstraint, text
from sqlmodel import Field

from bisheng.common.models.base import SQLModelSerializable
from bisheng.core.database.dialect_helpers import JsonType


class OAuthServerClient(SQLModelSerializable, table=True):
    """OAuth Server Client application (third-party apps using BiSheng as Auth Server).

    Implements RFC 6749 Client Registration and RFC 7636 PKCE support.
    """

    __tablename__ = "oauth_server_client"
    __table_args__ = (UniqueConstraint("client_id"),)

    id: int | None = Field(default=None, primary_key=True)
    client_id: str = Field(max_length=64, unique=True)
    client_id_issued_at: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    client_secret: str | None = Field(default=None, max_length=256)  # NULL = public client
    client_secret_expires_at: int | None = Field(
        default=0, sa_column=Column(Integer, nullable=True)
    )  # 0 = never expires
    redirect_uris: list[str] = Field(default=[], sa_column=Column(JsonType, nullable=False))
    grant_types: list[str] = Field(default=["authorization_code"], sa_column=Column(JsonType, nullable=False))
    response_types: list[str] = Field(default=["code"], sa_column=Column(JsonType, nullable=False))
    token_endpoint_auth_method: str = Field(default="client_secret_basic", max_length=32)
    allowed_scopes: list[str] = Field(
        default=["openid", "profile", "email"], sa_column=Column(JsonType, nullable=False)
    )
    client_name: str | None = Field(default=None, max_length=128)
    client_uri: str | None = Field(default=None, max_length=512)
    logo_uri: str | None = Field(default=None, max_length=512)
    tos_uri: str | None = Field(default=None, max_length=512)
    policy_uri: str | None = Field(default=None, max_length=512)
    jwks_uri: str | None = Field(default=None, max_length=512)
    jwks: dict | None = Field(default=None, sa_column=Column(JsonType, nullable=True))
    enabled: bool = Field(default=True)
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


class OAuthServerClientDao:
    """DAO for OAuthServerClient."""

    @classmethod
    async def aget_by_client_id(cls, client_id: str) -> OAuthServerClient | None:
        """Get client by client_id."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(OAuthServerClient).where(OAuthServerClient.client_id == client_id)
            result = await session.exec(stmt)
            return result.first()

    @classmethod
    async def aget_enabled_by_client_id(cls, client_id: str) -> OAuthServerClient | None:
        """Get enabled client by client_id."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(OAuthServerClient).where(
                OAuthServerClient.client_id == client_id,
                OAuthServerClient.enabled == True,  # noqa: E712
            )
            result = await session.exec(stmt)
            return result.first()

    @classmethod
    async def alist_enabled(cls) -> list[OAuthServerClient]:
        """List all enabled clients."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(OAuthServerClient).where(OAuthServerClient.enabled == True)  # noqa: E712
            result = await session.exec(stmt)
            return list(result.all())

    @classmethod
    async def acreate(
        cls,
        client_name: str | None,
        redirect_uris: list[str],
        grant_types: list[str] | None = None,
        allowed_scopes: list[str] | None = None,
        token_endpoint_auth_method: str = "client_secret_basic",
    ) -> OAuthServerClient:
        """Create a new OAuth client with auto-generated credentials."""
        from bisheng.core.database import get_async_db_session

        now = int(time.time())
        client = OAuthServerClient(
            client_id=secrets.token_urlsafe(16),
            client_id_issued_at=now,
            redirect_uris=redirect_uris,
            grant_types=grant_types or ["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method=token_endpoint_auth_method,
            allowed_scopes=allowed_scopes or ["openid", "profile", "email"],
            client_name=client_name,
        )

        # Generate client_secret only for confidential clients
        if token_endpoint_auth_method != "none":
            client.client_secret = secrets.token_urlsafe(32)
            client.client_secret_expires_at = 0  # Never expires by default

        async with get_async_db_session() as session:
            session.add(client)
            await session.commit()
            await session.refresh(client)
            return client

    @classmethod
    async def aupdate(cls, client: OAuthServerClient) -> OAuthServerClient:
        """Update an existing client."""
        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            session.add(client)
            await session.commit()
            await session.refresh(client)
            return client

    @classmethod
    async def adelete(cls, client_id: str) -> bool:
        """Delete a client by client_id."""
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(OAuthServerClient).where(OAuthServerClient.client_id == client_id)
            result = await session.exec(stmt)
            client = result.first()
            if client:
                await session.delete(client)
                await session.commit()
                return True
            return False

    @classmethod
    async def aregister_client(
        cls,
        client_name: str | None,
        redirect_uris: list[str],
        grant_types: list[str] | None = None,
        allowed_scopes: list[str] | None = None,
        token_endpoint_auth_method: str = "client_secret_basic",
        client_uri: str | None = None,
        logo_uri: str | None = None,
        jwks_uri: str | None = None,
        jwks: dict | None = None,
    ) -> OAuthServerClient:
        """Register a new OAuth client application.

        Returns the created client with plain-text client_secret (one-time display).
        """
        from bisheng.core.database import get_async_db_session

        client = OAuthServerClient(
            client_id=secrets.token_urlsafe(16),
            client_id_issued_at=int(time.time()),
            redirect_uris=redirect_uris,
            grant_types=grant_types or ["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method=token_endpoint_auth_method,
            allowed_scopes=allowed_scopes or ["openid", "profile", "email"],
            client_name=client_name,
            client_uri=client_uri,
            logo_uri=logo_uri,
            jwks_uri=jwks_uri,
            jwks=jwks,
        )

        # Generate client_secret only for confidential clients
        if token_endpoint_auth_method not in ("none", "none"):
            client.client_secret = secrets.token_urlsafe(32)
            client.client_secret_expires_at = 0

        async with get_async_db_session() as session:
            session.add(client)
            await session.commit()
            await session.refresh(client)
            return client
