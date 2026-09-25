"""User Sync constants and enums."""

from enum import StrEnum


class SyncStrategy(StrEnum):
    """User attribute sync strategy."""

    ALWAYS = "always"  # 每次登录同步
    FIRST_ONLY = "first_only"  # 仅首次同步
    MANUAL = "manual"  # 手动同步
    NEVER = "never"  # 从不同步


class UserSyncSource(StrEnum):
    """User sync authentication source."""

    LDAP = "ldap"
    GOOGLE = "google"
    GITHUB = "github"
    WECHAT = "wechat"
    ALIPAY = "alipay"


# Default sync strategies per source
DEFAULT_SYNC_STRATEGIES = {
    "email": SyncStrategy.FIRST_ONLY,
    "phone": SyncStrategy.FIRST_ONLY,
    "name": SyncStrategy.NEVER,
    "department": False,  # bool, not sync strategy
}

# OAuth provider display names
OAUTH_PROVIDER_NAMES = {
    "google": "Google",
    "github": "GitHub",
    "wechat": "微信",
    "alipay": "支付宝",
}

# OAuth scopes by provider
OAUTH_SCOPES = {
    "google": "openid email profile",
    "github": "user:email read:user",
}
