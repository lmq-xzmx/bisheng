"""Magic Link API endpoints - passwordless email authentication."""

import time

from bisheng.user_sync.domain.services.magic_link_service import MagicLinkService

# In-memory token store for demo (use Redis in production)
# Format: {token: {"email": email, "exp": timestamp, "user_id": user_id}}
_token_store: dict = {}


async def send_magic_link(
    email: str,
    user_id: int,
    user_email: str | None,
    base_url: str = "http://localhost:4001",
) -> dict:
    """Send a magic link to the user's email."""
    # Generate token
    token = MagicLinkService.generate_token()
    exp = time.time() + MagicLinkService.TOKEN_TTL

    # Store token (in production, use Redis with TTL)
    _token_store[token] = {
        "email": user_email or email,
        "exp": exp,
        "user_id": user_id,
    }

    # Get SMTP config
    smtp_config = MagicLinkService.get_smtp_config_from_settings()
    if not smtp_config or not smtp_config.get("smtp_server"):
        # Demo mode: return token directly
        magic_link = MagicLinkService.create_magic_link(token, base_url)
        return {
            "message": "Magic link sent (demo mode - check logs for link)",
            "demo_link": magic_link,
            "email": user_email or email,
        }

    # Send email
    success = await MagicLinkService.send_magic_link(
        email=user_email or email,
        token=token,
        base_url=base_url,
        smtp_config=smtp_config,
    )

    if success:
        return {
            "message": "Magic link sent successfully",
            "email": user_email or email,
        }
    else:
        return {"error": "Failed to send email"}


async def verify_magic_link(token: str) -> dict:
    """Verify a magic link token and return user info for JWT generation."""
    token_data = _token_store.get(token)

    if not token_data:
        return {"error": "Invalid or expired token"}

    if time.time() > token_data["exp"]:
        del _token_store[token]
        return {"error": "Token has expired"}

    user_id = token_data["user_id"]

    # Get user
    from bisheng.user.domain.models.user import UserDao

    db_user = await UserDao.aget_user(user_id)
    if not db_user:
        return {"error": "User not found"}

    # Delete token (one-time use)
    del _token_store[token]

    return {
        "user": db_user,
        "user_id": db_user.user_id,
        "user_name": db_user.user_name,
        "email": db_user.email,
    }
