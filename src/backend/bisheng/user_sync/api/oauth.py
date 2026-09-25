"""OAuth endpoints."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from bisheng.common.errcode.user_sync import OAuthErrorCode
from bisheng.common.schemas.api import resp_200, resp_500
from bisheng.user_sync.domain.providers.google_provider import GoogleProvider
from bisheng.user_sync.domain.services.oauth_state_service import OAuthStateService

router = APIRouter(prefix="/oauth", tags=["oauth"])

# Provider registry
OAUTH_PROVIDERS = {
    "google": GoogleProvider,
}


def get_oauth_provider(provider: str, tenant_id: int):
    """Get OAuth provider instance by name."""
    provider_cls = OAUTH_PROVIDERS.get(provider.lower())
    if provider_cls is None:
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
    Get OAuth authorization URL for the specified provider.

    The frontend should redirect the user to this URL for OAuth consent.
    """
    try:
        oauth_provider = get_oauth_provider(provider, tenant_id)

        # Create state token
        state = await OAuthStateService.create(
            provider=provider,
            redirect_uri=redirect_uri,
            tenant_id=tenant_id,
        )

        # Build callback URI
        callback_uri = f"/api/v1/oauth/{provider}/callback"
        if redirect_uri:
            callback_uri += f"?redirect_uri={redirect_uri}"

        # Get authorization URL
        auth_url = await oauth_provider.get_authorization_url(state, callback_uri)

        return resp_200({"authorization_url": auth_url})

    except OAuthErrorCode as e:
        return resp_500(e.Code, e.message)
    except Exception as e:
        return resp_500(OAuthErrorCode.OAUTH_AUTH_FAILED.Code, str(e))


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State token"),
    redirect_uri: str | None = Query(None),
    request: Request = None,
):
    """
    OAuth callback endpoint.

    Receives the authorization code from the OAuth provider,
    exchanges it for tokens, and issues a JWT.
    """
    try:
        # Verify and consume state
        state_data = await OAuthStateService.verify_and_delete(state, provider)

        # Get provider
        oauth_provider = get_oauth_provider(provider, state_data.tenant_id)

        # Authenticate via callback
        auth_result = await oauth_provider.authenticate_callback(code)

        # Get sync options
        from bisheng.user_sync.domain.providers.base import SyncOptions

        options = await SyncOptions.from_config(state_data.tenant_id, provider)

        # Sync user and get token
        _user, token = await oauth_provider.sync_user(
            external_id=auth_result.external_id,
            user_attrs=auth_result.to_user_attrs(),
            options=options,
        )

        # Redirect to frontend with token
        frontend_redirect = state_data.redirect_uri or "/workspace"
        if token:
            frontend_redirect = f"{frontend_redirect}?token={token}"

        return RedirectResponse(url=frontend_redirect, status_code=302)

    except OAuthErrorCode as e:
        return resp_500(e.Code, e.message)
    except Exception as e:
        return resp_500(OAuthErrorCode.OAUTH_AUTH_FAILED.Code, str(e))
