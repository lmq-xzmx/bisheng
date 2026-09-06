"""OAuth Provider endpoints - BiSheng as Authorization Server.

These endpoints implement BiSheng as an OAuth 2.0 / OIDC Provider.
Prefix: /oauth (registered in main router)
"""

from fastapi import APIRouter, Form, Query

from bisheng.common.schemas.api import resp_200, resp_500

router = APIRouter(prefix="/oauth", tags=["oauth-provider"])


def get_provider_service():
    """Lazy import to avoid circular imports."""
    from bisheng.user_sync.domain.services.oauth_provider_service import oauth_provider_service
    return oauth_provider_service


@router.get("/.well-known/jwks.json")
async def get_jwks():
    """Get JSON Web Key Set for token verification."""
    return resp_200({
        "keys": [
            {
                "kty": "oct",
                "alg": "HS256",
                "use": "sig",
                "description": "HS256 symmetric key - secret not exposed",
            }
        ]
    })


@router.get("/authorize")
async def authorize(
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query("openid profile email"),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
):
    """
    OAuth 2.0 Authorization Endpoint.

    Returns authorization code after user login.
    """
    provider = get_provider_service()

    # Validate client
    client = provider.get_client(client_id)
    if not client:
        return resp_500(400, "Invalid client_id")

    # Validate redirect URI
    if not provider.validate_redirect_uri(client, redirect_uri):
        return resp_500(400, "Invalid redirect_uri")

    # Return authorization form URL (frontend would handle actual login)
    from urllib.parse import urlencode

    authorize_url = f"/oauth/authorize/form?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}"
    if state:
        authorize_url += f"&state={state}"

    return resp_200({
        "authorization_url": authorize_url,
        "instructions": "Redirect user to this URL after authentication",
    })


@router.get("/authorize/form")
async def authorize_form(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query(...),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    user_id: int = Query(...),
):
    """Process authorization after user login."""
    provider = get_provider_service()

    client = provider.get_client(client_id)
    if not client:
        return resp_500(400, "Invalid client")

    scopes = scope.split()
    valid_scopes = provider.validate_scopes(client, scopes)

    code = provider.create_authorization_code(
        client_id=client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        scopes=valid_scopes,
        code_challenge=code_challenge,
    )

    # Build redirect URL
    from urllib.parse import urlencode
    params = {"code": code}
    if state:
        params["state"] = state

    from urllib.parse import quote
    redirect_url = f"{redirect_uri}?{urlencode(params)}"

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=redirect_url)


@router.post("/token")
async def token_endpoint(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    refresh_token: str | None = Form(None),
    scope: str | None = Form(None),
):
    """OAuth 2.0 Token Endpoint."""
    provider = get_provider_service()

    if grant_type == "authorization_code":
        if not code or not redirect_uri:
            from fastapi import HTTPException
            raise HTTPException(400, "code and redirect_uri required")

        try:
            tokens = provider.exchange_code(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
            return resp_200({
                "access_token": tokens.access_token,
                "token_type": tokens.token_type,
                "expires_in": tokens.expires_in,
                "refresh_token": tokens.refresh_token,
                "scope": tokens.scope,
            })
        except Exception as e:
            from fastapi import HTTPException
            raise HTTPException(400, str(e))

    elif grant_type == "refresh_token":
        from fastapi import HTTPException
        raise HTTPException(501, "Refresh token not implemented")

    else:
        from fastapi import HTTPException
        raise HTTPException(400, "Unsupported grant_type")


@router.get("/userinfo")
async def userinfo(
    authorization: str = Query(..., description="Bearer token"),
):
    """OAuth UserInfo Endpoint."""
    if not authorization.startswith("Bearer "):
        from fastapi import HTTPException
        raise HTTPException(401, "Invalid authorization header")

    token = authorization[7:]
    provider = get_provider_service()

    userinfo = provider.get_userinfo(token)
    if not userinfo:
        from fastapi import HTTPException
        raise HTTPException(401, "Invalid or expired token")

    return resp_200(userinfo)
