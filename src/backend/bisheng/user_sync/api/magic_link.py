"""Magic Link API endpoints - passwordless email authentication."""

import time
from typing import Optional

from fastapi import APIRouter, Query

from bisheng.common.dependencies.user_deps import UserPayload
from bisheng.common.schemas.api import resp_200, resp_500
from bisheng.user_sync.domain.services.magic_link_service import MagicLinkService

router = APIRouter(prefix="/user/magic-link", tags=["magic-link"])

# In-memory token store for demo (use Redis in production)
# Format: {token: {"email": email, "exp": timestamp, "user_id": user_id}}
_token_store: dict = {}


@router.post("/send")
async def send_magic_link(
    email: str = Query(..., description="Email address to send magic link"),
    user: UserPayload = UserPayload.get_login_user,
):
    """
    Send a magic link to the user's email.

    The user must be logged in first (to verify their email).
    """
    try:
        # Get user's email from database
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user.user_id)
        if not db_user:
            return resp_500(404, "User not found")

        # Generate token
        token = MagicLinkService.generate_token()
        exp = time.time() + MagicLinkService.TOKEN_TTL

        # Store token (in production, use Redis with TTL)
        _token_store[token] = {
            "email": db_user.email or email,
            "exp": exp,
            "user_id": db_user.user_id,
        }

        # Get SMTP config
        smtp_config = MagicLinkService.get_smtp_config_from_settings()
        if not smtp_config or not smtp_config.get("smtp_server"):
            # Demo mode: return token directly (for testing)
            base_url = "http://localhost:4001"
            magic_link = MagicLinkService.create_magic_link(token, base_url)
            logger.info("Magic link (demo mode): %s", magic_link)
            return resp_200({
                "message": "Magic link sent (demo mode - check logs for link)",
                "demo_link": magic_link,
                "email": db_user.email or email,
            })

        # Send email
        base_url = getattr(__import__('bisheng'), 'common').services.config_service.settings.get("bisheng", {}).get("server_url", "http://localhost:7860")
        success = await MagicLinkService.send_magic_link(
            email=db_user.email or email,
            token=token,
            base_url=base_url,
            smtp_config=smtp_config,
        )

        if success:
            return resp_200({
                "message": "Magic link sent successfully",
                "email": db_user.email or email,
            })
        else:
            return resp_500(500, "Failed to send email")

    except Exception as e:
        return resp_500(500, str(e))


@router.post("/verify")
async def verify_magic_link(
    token: str = Query(..., description="Magic link token"),
):
    """
    Verify a magic link token and log in the user.

    Returns JWT token on success.
    """
    try:
        # Look up token
        token_data = _token_store.get(token)

        if not token_data:
            return resp_500(404, "Invalid or expired token")

        # Check expiration
        if time.time() > token_data["exp"]:
            del _token_store[token]
            return resp_500(404, "Token has expired")

        user_id = token_data["user_id"]

        # Get user
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user_id)
        if not db_user:
            return resp_500(404, "User not found")

        # Delete token (one-time use)
        del _token_store[token]

        # Generate JWT
        from bisheng.user.domain.services.auth import AuthJwt

        auth_jwt = AuthJwt()
        token_version = await UserDao.aget_token_version(db_user.user_id)

        # Get user's primary tenant
        from bisheng.database.models.tenant import UserTenantDao
        leaf_tenant = await UserTenantDao.aget_user_primary_tenant(db_user.user_id)
        tenant_id = leaf_tenant.tenant_id if leaf_tenant else 1

        access_token = AuthJwt.create_access_token(
            db_user,
            auth_jwt,
            tenant_id=tenant_id,
            token_version=token_version,
        )

        return resp_200({
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": db_user.user_id,
            "user_name": db_user.user_name,
            "email": db_user.email,
        })

    except Exception as e:
        return resp_500(500, str(e))


@router.post("/request")
async def request_magic_link(
    email: str = Query(..., description="Email address to send magic link"),
):
    """
    Request a magic link without being logged in.

    Looks up user by email and sends magic link.
    """
    try:
        # Find user by email
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user_by_username(email)
        if not db_user:
            # User not found - don't reveal this to prevent enumeration
            return resp_200({
                "message": "If an account exists with this email, a magic link has been sent",
            })

        # Generate token
        token = MagicLinkService.generate_token()
        exp = time.time() + MagicLinkService.TOKEN_TTL

        # Store token
        _token_store[token] = {
            "email": db_user.email or email,
            "exp": exp,
            "user_id": db_user.user_id,
        }

        # Get SMTP config
        smtp_config = MagicLinkService.get_smtp_config_from_settings()
        if not smtp_config or not smtp_config.get("smtp_server"):
            # Demo mode: return token directly
            base_url = "http://localhost:4001"
            magic_link = MagicLinkService.create_magic_link(token, base_url)
            logger.info("Magic link (demo mode): %s", magic_link)
            return resp_200({
                "message": "Magic link sent (demo mode - check logs for link)",
                "demo_link": magic_link,
                "email": db_user.email or email,
            })

        # Send email
        base_url = "http://localhost:4001"  # Frontend URL
        success = await MagicLinkService.send_magic_link(
            email=db_user.email or email,
            token=token,
            base_url=base_url,
            smtp_config=smtp_config,
        )

        if success:
            return resp_200({
                "message": "If an account exists with this email, a magic link has been sent",
            })
        else:
            return resp_500(500, "Failed to send email")

    except Exception as e:
        # Don't reveal internal errors
        return resp_200({
            "message": "If an account exists with this email, a magic link has been sent",
        })
