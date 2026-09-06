"""OAuth state management service - Redis-based state validation with HMAC signature."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from loguru import logger

from bisheng.common.errcode.user_sync import OAuthErrorCode
from bisheng.core.cache.redis_manager import get_redis_client


@dataclass
class OAuthStateData:
    """OAuth state payload."""

    provider: str
    redirect_uri: str | None
    tenant_id: int
    exp: float  # Expiration timestamp


class OAuthStateService:
    """Manages OAuth state tokens with Redis storage and HMAC signature verification."""

    STATE_TTL = 300  # 5 minutes
    STATE_PREFIX = "oauth:state:"

    @classmethod
    def _compute_signature(cls, state_data: dict, secret: str) -> str:
        """Compute HMAC-SHA256 signature for state data."""
        # Create a copy without sig field for signing
        data_to_sign = {k: v for k, v in state_data.items() if k != "sig"}
        message = json.dumps(data_to_sign, sort_keys=True)
        return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    @classmethod
    async def create(cls, provider: str, redirect_uri: str | None, tenant_id: int) -> str:
        """
        Create a new OAuth state token.

        Returns a base64url-encoded state string with HMAC signature.
        """
        from bisheng.common.services.config_service import settings

        secret = (
            getattr(settings.sso_sync, "gateway_hmac_secret", "default-secret")
            if hasattr(settings, "sso_sync")
            else "default-secret"
        )

        state_data = {
            "provider": provider,
            "redirect_uri": redirect_uri,
            "tenant_id": tenant_id,
            "exp": time.time() + cls.STATE_TTL,
        }

        # Add signature
        state_data["sig"] = cls._compute_signature(state_data, secret)

        # Encode to base64url
        state_json = json.dumps(state_data)
        state = base64.urlsafe_b64encode(state_json.encode()).decode()

        # Store in Redis
        redis = await get_redis_client()
        await redis.aset(
            f"{cls.STATE_PREFIX}{state}",
            state_json,
            expiration=cls.STATE_TTL,
        )

        logger.debug("Created OAuth state for provider=%s tenant_id=%s", provider, tenant_id)
        return state

    @classmethod
    async def verify_and_delete(cls, state: str, provider: str) -> OAuthStateData:
        """
        Verify OAuth state token and delete it (prevent replay).

        Raises OAuthErrorCode.OAUTH_STATE_INVALID if verification fails.
        """
        from bisheng.common.services.config_service import settings

        secret = (
            getattr(settings.sso_sync, "gateway_hmac_secret", "default-secret")
            if hasattr(settings, "sso_sync")
            else "default-secret"
        )

        # Get from Redis
        redis = await get_redis_client()
        state_json = await redis.aget(f"{cls.STATE_PREFIX}{state}")

        if state_json is None:
            logger.warning("OAuth state not found or expired: state=%s", state[:20])
            raise OAuthErrorCode.OAUTH_STATE_EXPIRED.http_exception()

        try:
            state_data = json.loads(state_json)
        except json.JSONDecodeError:
            logger.warning("OAuth state JSON decode error: %s", state[:20])
            raise OAuthErrorCode.OAUTH_STATE_INVALID.http_exception()

        # Verify signature
        expected_sig = cls._compute_signature(state_data, secret)
        if not hmac.compare_digest(expected_sig, state_data.get("sig", "")):
            logger.warning("OAuth state signature mismatch")
            raise OAuthErrorCode.OAUTH_STATE_INVALID.http_exception()

        # Verify provider matches
        if state_data.get("provider") != provider:
            logger.warning("OAuth state provider mismatch: expected=%s got=%s", provider, state_data.get("provider"))
            raise OAuthErrorCode.OAUTH_STATE_INVALID.http_exception()

        # Verify expiration
        if time.time() > state_data.get("exp", 0):
            logger.warning("OAuth state expired")
            raise OAuthErrorCode.OAUTH_STATE_EXPIRED.http_exception()

        # Delete to prevent replay
        await redis.delete(f"{cls.STATE_PREFIX}{state}")

        return OAuthStateData(
            provider=state_data["provider"],
            redirect_uri=state_data.get("redirect_uri"),
            tenant_id=state_data["tenant_id"],
            exp=state_data["exp"],
        )
