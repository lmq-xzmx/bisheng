"""OAuth Provider admin configuration API."""

from fastapi import APIRouter, Depends

from bisheng.common.dependencies.user_deps import UserPayload
from bisheng.common.schemas.api import resp_200, resp_500
from bisheng.user_sync.domain.models import OAuthProviderConfig, OAuthProviderConfigDao

router = APIRouter(prefix="/admin/oauth-providers", tags=["admin-oauth"])


@router.get("")
async def list_oauth_providers(
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """List all OAuth provider configurations."""
    try:
        # TODO: Filter by tenant if multi-tenant
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(OAuthProviderConfig)
            result = await session.exec(stmt)
            configs = list(result.all())

        return resp_200({"configs": [c.model_dump() for c in configs]})
    except Exception as e:
        return resp_500(500, str(e))


@router.post("")
async def create_oauth_provider(
    config: OAuthProviderConfig,
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Create OAuth provider configuration."""
    try:
        created = await OAuthProviderConfigDao.acreate(config)
        return resp_200({"config": created.model_dump()})
    except Exception as e:
        return resp_500(500, str(e))


@router.put("/{config_id}")
async def update_oauth_provider(
    config_id: int,
    config: OAuthProviderConfig,
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Update OAuth provider configuration."""
    try:
        from sqlmodel import select

        from bisheng.core.database import get_async_db_session

        async with get_async_db_session() as session:
            stmt = select(OAuthProviderConfig).where(OAuthProviderConfig.id == config_id)
            result = await session.exec(stmt)
            existing = result.first()

            if not existing:
                return resp_500(404, "Configuration not found")

            for key, value in config.model_dump(exclude={"id"}).items():
                setattr(existing, key, value)

            session.add(existing)
            await session.commit()
            await session.refresh(existing)

        return resp_200({"config": existing.model_dump()})
    except Exception as e:
        return resp_500(500, str(e))


@router.delete("/{config_id}")
async def delete_oauth_provider(
    config_id: int,
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Delete OAuth provider configuration."""
    try:
        deleted = await OAuthProviderConfigDao.adelete(config_id)
        if deleted:
            return resp_200({"success": True})
        return resp_500(404, "Configuration not found")
    except Exception as e:
        return resp_500(500, str(e))
