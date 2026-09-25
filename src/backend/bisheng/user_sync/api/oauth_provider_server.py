"""OAuth Provider endpoints - BiSheng as Authorization Server.

Implements OAuth 2.0 + OIDC Endpoints:
- GET /oauth/authorize (Authorization Endpoint)
- GET /oauth/authorize/form (Authorization Form Handler)
- POST /oauth/token (Token Endpoint)
- GET /oauth/userinfo (UserInfo Endpoint)
- POST /oauth/revoke (Token Revocation)
- GET /oauth/register (Dynamic Client Registration)
- GET /.well-known/openid-configuration (OIDC Discovery)
- GET /.well-known/jwks.json (JWKS)
"""

from fastapi import APIRouter, Form, HTTPException, Query
from pydantic import BaseModel

from bisheng.common.schemas.api import resp_200

router = APIRouter(prefix="/oauth", tags=["oauth-provider"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ClientRegistrationRequest(BaseModel):
    """OAuth Client Registration Request (RFC 7591)."""

    client_name: str | None = None
    redirect_uris: list[str]
    grant_types: list[str] | None = None
    allowed_scopes: list[str] | None = None
    token_endpoint_auth_method: str = "client_secret_basic"
    client_uri: str | None = None
    logo_uri: str | None = None
    jwks_uri: str | None = None
    jwks: dict | None = None


class ClientRegistrationResponse(BaseModel):
    """OAuth Client Registration Response."""

    client_id: str
    client_secret: str | None = None  # Only returned once at registration
    client_id_issued_at: int
    client_secret_expires_at: int
    redirect_uris: list[str]
    grant_types: list[str]
    allowed_scopes: list[str]
    token_endpoint_auth_method: str
    client_name: str | None = None


# =============================================================================
# Helper
# =============================================================================


def get_provider_service():
    """Lazy import to avoid circular imports."""
    from bisheng.user_sync.domain.services.oauth_provider_service import oauth_provider_service

    return oauth_provider_service


# =============================================================================
# OIDC Discovery & JWKS
# =============================================================================


@router.get("/.well-known/openid-configuration")
async def get_openid_configuration():
    """OIDC Discovery Endpoint (RFC 8414)."""
    provider = get_provider_service()
    return await provider.get_oidc_discovery()


@router.get("/.well-known/jwks.json")
async def get_jwks():
    """JSON Web Key Set Endpoint (RFC 7517)."""
    provider = get_provider_service()
    return provider.get_jwks()


# =============================================================================
# Authorization Endpoint (RFC 6749 §4.1)
# =============================================================================


@router.get("/authorize")
async def authorize(
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query("openid profile email"),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    nonce: str | None = Query(None),
):
    """
    OAuth 2.0 Authorization Endpoint.

    Returns authorization form URL for user authentication.
    Supports PKCE (RFC 7636) via code_challenge and code_challenge_method.
    """
    provider = get_provider_service()

    # Validate response_type
    if response_type != "code":
        raise HTTPException(400, "Only 'code' response_type is supported")

    # Validate client
    client = await provider.get_client(client_id)
    if not client:
        raise HTTPException(400, "Invalid client_id")

    # Validate redirect_uri
    if not provider.validate_redirect_uri(client, redirect_uri):
        raise HTTPException(400, "Invalid redirect_uri")

    # Build authorization form URL
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
    }
    if state:
        params["state"] = state
    if code_challenge:
        params["code_challenge"] = code_challenge
    if code_challenge_method:
        params["code_challenge_method"] = code_challenge_method
    if nonce:
        params["nonce"] = nonce

    authorize_url = f"/oauth/authorize/form?{urlencode(params)}"

    return resp_200(
        {
            "authorization_url": authorize_url,
            "instructions": "Redirect user to this URL after authentication",
        }
    )


@router.get("/authorize/form")
async def authorize_form(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query(...),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    nonce: str | None = Query(None),
    user_id: int = Query(...),
):
    """
    Process authorization after user login.

    Creates authorization code and redirects back to client.
    """
    provider = get_provider_service()

    client = await provider.get_client(client_id)
    if not client:
        raise HTTPException(400, "Invalid client")

    # Validate redirect_uri
    if not provider.validate_redirect_uri(client, redirect_uri):
        raise HTTPException(400, "Invalid redirect_uri")

    scopes = scope.split()
    valid_scopes = provider.validate_scopes(client, scopes)

    # Create authorization code (stored in Redis)
    code = await provider.create_authorization_code(
        client_id=client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        scopes=valid_scopes,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
    )

    # Build redirect URL
    from urllib.parse import urlencode

    params = {"code": code}
    if state:
        params["state"] = state

    redirect_url = f"{redirect_uri}?{urlencode(params)}"

    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=redirect_url)


# =============================================================================
# Token Endpoint (RFC 6749 §4.3)
# =============================================================================


@router.post("/token")
async def token_endpoint(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str | None = Form(None),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    refresh_token: str | None = Form(None),
    scope: str | None = Form(None),
    code_verifier: str | None = Form(None),
):
    """
    OAuth 2.0 Token Endpoint.

    Supports:
    - grant_type=authorization_code: Exchange code for tokens
    - grant_type=refresh_token: Refresh access token
    """
    provider = get_provider_service()

    if grant_type == "authorization_code":
        if not code or not redirect_uri:
            raise HTTPException(400, "code and redirect_uri required for authorization_code grant")

        tokens = await provider.exchange_code(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        return resp_200(
            {
                "access_token": tokens.access_token,
                "token_type": tokens.token_type,
                "expires_in": tokens.expires_in,
                "refresh_token": tokens.refresh_token,
                "id_token": tokens.id_token,
                "scope": tokens.scope,
            }
        )

    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(400, "refresh_token required for refresh_token grant")

        tokens = await provider.exchange_refresh_token(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scope,
        )
        return resp_200(
            {
                "access_token": tokens.access_token,
                "token_type": tokens.token_type,
                "expires_in": tokens.expires_in,
                "refresh_token": tokens.refresh_token,
                "id_token": tokens.id_token,
                "scope": tokens.scope,
            }
        )

    else:
        raise HTTPException(400, f"Unsupported grant_type: {grant_type}")


# =============================================================================
# UserInfo Endpoint (OIDC)
# =============================================================================


@router.get("/userinfo")
async def userinfo(
    authorization: str = Query(..., description="Bearer token"),
):
    """
    OIDC UserInfo Endpoint.

    Returns claims about the authenticated user.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")

    token = authorization[7:]
    provider = get_provider_service()

    userinfo = await provider.get_userinfo_async(token)
    if not userinfo:
        raise HTTPException(401, "Invalid or expired token")

    return resp_200(userinfo)


# =============================================================================
# Token Revocation (RFC 7009)
# =============================================================================


@router.post("/revoke")
async def revoke_token(
    token: str = Form(...),
    token_type_hint: str | None = Form(None),
):
    """OAuth 2.0 Token Revocation Endpoint."""
    provider = get_provider_service()
    await provider.revoke_token(token, token_type_hint)
    # Always return 200 (RFC 7009 §2.3)
    return resp_200({"revoked": True})


# =============================================================================
# Dynamic Client Registration (RFC 7591)
# =============================================================================


@router.post("/register")
async def register_client(
    body: ClientRegistrationRequest,
):
    """Dynamic Client Registration Endpoint (RFC 7591)."""
    # Validate redirect_uris
    if not body.redirect_uris:
        raise HTTPException(400, "redirect_uris is required")

    # Validate grant_types
    grant_types = body.grant_types or ["authorization_code", "refresh_token"]
    if "authorization_code" not in grant_types and "refresh_token" not in grant_types:
        raise HTTPException(400, "At least authorization_code or refresh_token grant must be allowed")

    # Validate token_endpoint_auth_method
    valid_auth_methods = ["client_secret_basic", "client_secret_post", "none"]
    if body.token_endpoint_auth_method not in valid_auth_methods:
        raise HTTPException(400, f"token_endpoint_auth_method must be one of {valid_auth_methods}")

    # Create client
    from bisheng.user_sync.domain.models import OAuthServerClientDao

    client = await OAuthServerClientDao.aregister_client(
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        grant_types=grant_types,
        allowed_scopes=body.allowed_scopes or ["openid", "profile", "email"],
        token_endpoint_auth_method=body.token_endpoint_auth_method,
        client_uri=body.client_uri,
        logo_uri=body.logo_uri,
        jwks_uri=body.jwks_uri,
        jwks=body.jwks,
    )

    return resp_200(
        ClientRegistrationResponse(
            client_id=client.client_id,
            client_secret=client.client_secret,  # Only returned once!
            client_id_issued_at=client.client_id_issued_at,
            client_secret_expires_at=client.client_secret_expires_at or 0,
            redirect_uris=client.redirect_uris,
            grant_types=client.grant_types,
            allowed_scopes=client.allowed_scopes,
            token_endpoint_auth_method=client.token_endpoint_auth_method,
            client_name=client.client_name,
        )
    )


@router.get("/register/{client_id}")
async def get_registered_client(
    client_id: str,
):
    """Get registered client information (RFC 7591)."""
    from bisheng.user_sync.domain.models import OAuthServerClientDao

    client = await OAuthServerClientDao.aget_by_client_id(client_id)
    if not client:
        raise HTTPException(404, "Client not found")

    # Don't expose client_secret
    return resp_200(
        {
            "client_id": client.client_id,
            "client_id_issued_at": client.client_id_issued_at,
            "redirect_uris": client.redirect_uris,
            "grant_types": client.grant_types,
            "allowed_scopes": client.allowed_scopes,
            "token_endpoint_auth_method": client.token_endpoint_auth_method,
            "client_name": client.client_name,
            "client_uri": client.client_uri,
            "logo_uri": client.logo_uri,
        }
    )


@router.delete("/register/{client_id}")
async def delete_registered_client(
    client_id: str,
    authorization: str | None = None,
):
    """Delete registered client (disable it)."""
    from bisheng.user_sync.domain.models import OAuthServerClientDao

    client = await OAuthServerClientDao.aget_by_client_id(client_id)
    if not client:
        raise HTTPException(404, "Client not found")

    # Disable instead of delete (to preserve audit trail)
    client.enabled = False
    await OAuthServerClientDao.aupdate(client)

    return resp_200({"disabled": True})
