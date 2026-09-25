"""LDAP login endpoint."""

from fastapi import APIRouter, Request

from bisheng.common.errcode.user_sync import LdapErrorCode
from bisheng.common.schemas.api import resp_200
from bisheng.user_sync.domain.providers.ldap_provider import LdapProvider

router = APIRouter(prefix="/user", tags=["ldap"])


@router.post("/ldap/login")
async def ldap_login(request: Request):
    """
    LDAP user login endpoint.

    Expected body:
    {
        "username": str,
        "password": str,  # RSA encrypted
        "tenant_id": int,
        "captcha_key": str (optional),
        "captcha": str (optional)
    }
    """
    from bisheng.common.schemas.api import resp_500
    from bisheng.user_sync.domain.providers.base import SyncOptions

    try:
        body = await request.json()
        tenant_id = body.get("tenant_id")
        if not tenant_id:
            return resp_500(LdapErrorCode.LDAP_INVALID_CONFIG.Code, "tenant_id is required")

        # Create LDAP provider
        provider = LdapProvider(tenant_id=tenant_id)

        # Authenticate
        auth_result = await provider.authenticate(request)

        # Get sync options
        options = await SyncOptions.from_config(tenant_id, "ldap")

        # Sync user and get token
        user, token = await provider.sync_user(
            external_id=auth_result.external_id,
            user_attrs=auth_result.to_user_attrs(),
            options=options,
        )

        return resp_200(
            {
                "user_id": user.user_id,
                "user_name": user.user_name,
                "access_token": token,
                "token_type": "bearer",
                "email": user.email,
                "phone_number": user.phone_number,
            }
        )

    except LdapErrorCode as e:
        return resp_500(e.Code, e.message)
    except Exception as e:
        return resp_500(LdapErrorCode.LDAP_CONNECTION_FAILED.Code, str(e))
