"""User Sync error codes (19xxx)."""

from bisheng.common.errcode.base import BaseErrorCode


class LdapErrorCode(BaseErrorCode):
    """LDAP authentication errors (191xx)."""

    LDAP_CONNECTION_FAILED = 19101, "LDAP 服务器连接失败"
    LDAP_AUTH_FAILED = 19102, "用户名或密码错误"
    LDAP_USER_NOT_FOUND = 19103, "用户不存在"
    LDAP_USER_DISABLED = 19104, "账号已禁用"
    LDAP_CONFIG_NOT_FOUND = 19105, "LDAP 未配置"
    LDAP_TIMEOUT = 19106, "LDAP 连接超时"
    LDAP_INVALID_CONFIG = 19107, "LDAP 配置无效"


class OAuthErrorCode(BaseErrorCode):
    """OAuth authentication errors (192xx)."""

    OAUTH_PROVIDER_DISABLED = 19201, "OAuth Provider 未启用"
    OAUTH_AUTH_FAILED = 19202, "授权失败"
    OAUTH_STATE_INVALID = 19203, "State 验证失败，请重新登录"
    OAUTH_STATE_EXPIRED = 19204, "State 已过期，请重新登录"
    OAUTH_TOKEN_EXCHANGE_FAILED = 19205, "Token 交换失败"
    OAUTH_USER_INFO_FAILED = 19206, "获取用户信息失败"
    OAUTH_PROVIDER_NOT_FOUND = 19207, "OAuth Provider 不存在"
    OAUTH_CONFIG_NOT_FOUND = 19208, "OAuth Provider 未配置"
