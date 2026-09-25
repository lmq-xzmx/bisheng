"""LDAP configuration admin API."""

from fastapi import APIRouter, Depends

from bisheng.common.dependencies.user_deps import UserPayload
from bisheng.common.schemas.api import resp_200, resp_500
from bisheng.user_sync.domain.models import LdapConfig, LdapConfigDao

router = APIRouter(prefix="/admin/ldap-config", tags=["admin-ldap"])


@router.get("")
async def get_ldap_config(
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Get LDAP configuration."""
    try:
        # TODO: Get tenant_id from user context
        config = await LdapConfigDao.aget_for_tenant(tenant_id=1)
        if config:
            return resp_200({"config": config.model_dump()})
        return resp_200({"config": None})
    except Exception as e:
        return resp_500(500, str(e))


@router.put("")
async def update_ldap_config(
    config: LdapConfig,
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Create or update LDAP configuration."""
    try:
        # TODO: Get tenant_id from user context
        config.tenant_id = 1
        updated = await LdapConfigDao.aupsert(config)
        return resp_200({"config": updated.model_dump()})
    except Exception as e:
        return resp_500(500, str(e))
