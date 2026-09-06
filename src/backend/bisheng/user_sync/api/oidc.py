"""OIDC (Casdoor/Keycloak) endpoints."""

from fastapi import APIRouter, Query

from bisheng.common.schemas.api import resp_200, resp_500
from bisheng.user_sync.domain.providers.casdoor_provider import CasdoorProvider
from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

router = APIRouter(prefix="/user/oidc", tags=["oidc"])

# Provider registry
OIDC_PROVIDERS = {
    "casdoor": CasdoorProvider,
}


def get_oidc_provider(provider: str, tenant_id: int):
    """Get OIDC provider instance."""
    provider_cls = OIDC_PROVIDERS.get(provider.lower())
    if provider_cls is None:
        from bisheng.common.errcode.user_sync import OAuthErrorCode

        raise OAuthErrorCode.OAUTH_PROVIDER_NOT_FOUND.http_exception()
    return provider_cls(tenant_id)


@router.get("/{provider}/authorize")
async def get_authorization_url(
    provider: str,
    state: str = Query(..., description="CSRF state token"),
    redirect_uri: str | None = Query(None, description="Post-login redirect URI"),
    tenant_id: int = Query(..., description="Tenant ID"),
):
    """
    Get OIDC authorization URL.

    The frontend should redirect the user to this URL for IdP consent.
    """
    try:
        oidc_provider = get_oidc_provider(provider, tenant_id)

        # Create state token
        state = await OAuthStateService.create(
            provider=f"oidc_{provider}",
            redirect_uri=redirect_uri,
            tenant_id=tenant_id,
        )

        # Build callback URI
        callback_uri = f"/api/v1/user/oidc/{provider}/callback"
        if redirect_uri:
            callback_uri += f"?redirect_uri={redirect_uri}"

        # Get authorization URL
        auth_url = await oidc_provider.get_authorization_url(state, callback_uri)

        return resp_200({"authorization_url": auth_url})

    except Exception as e:
        return resp_500(500, str(e))


@router.get("/{provider}/callback")
async def oidc_callback(
    provider: str,
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State token"),
    redirect_uri: str | None = Query(None),
):
    """
    OIDC callback endpoint.

    Receives the authorization code from the IdP,
    exchanges it for tokens, and issues a JWT.
    """
    from fastapi.responses import RedirectResponse

    try:
        from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

        # Verify and consume state
        state_data = await OAuthStateService.verify_and_delete(state, f"oidc_{provider}")

        # Get provider and authenticate
        oidc_provider = get_oidc_provider(provider, state_data.tenant_id)

        # Authenticate via OIDC callback
        auth_result = await oidc_provider.authenticate_callback(code)

        # Get sync options
        from bisheng.user_sync.domain.providers.base import SyncOptions

        options = await SyncOptions.from_config(state_data.tenant_id, f"oidc_{provider}")

        # Sync user and get token
        user, token = await oidc_provider.sync_user(
            external_id=auth_result.external_id,
            user_attrs=auth_result.to_user_attrs(),
            options=options,
        )

        # Redirect to frontend with token
        frontend_redirect = state_data.redirect_uri or "/workspace"
        if token:
            frontend_redirect = f"{frontend_redirect}?token={token}"

        return RedirectResponse(url=frontend_redirect, status_code=302)

    except Exception as e:
        return resp_500(500, str(e))
