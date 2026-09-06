"""OAuth providers list endpoint for frontend dynamic rendering."""

from fastapi import APIRouter, Query

from bisheng.common.schemas.api import resp_200
from bisheng.user_sync.domain.constants import OAUTH_PROVIDER_NAMES
from bisheng.user_sync.domain.models import OAuthProviderConfigDao

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/providers")
async def list_providers(
    tenant_id: int = Query(..., description="Tenant ID"),
):
    """
    Get list of enabled OAuth providers for the tenant.

    This endpoint is used by the frontend to dynamically render
    social login buttons based on configuration.
    """
    configs = await OAuthProviderConfigDao.alist_enabled_for_tenant(tenant_id)

    providers = []
    for config in configs:
        providers.append(
            {
                "id": config.provider,
                "name": OAUTH_PROVIDER_NAMES.get(config.provider, config.provider.title()),
                "icon": f"{config.provider}.svg",
                "enabled": config.enabled,
            }
        )

    return resp_200({"providers": providers})
