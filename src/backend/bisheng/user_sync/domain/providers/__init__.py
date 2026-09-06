"""User Sync providers."""

from bisheng.user_sync.domain.providers.base import AuthResult, SyncOptions, UserAttrs, UserSyncProvider
from bisheng.user_sync.domain.providers.casdoor_provider import CasdoorProvider
from bisheng.user_sync.domain.providers.google_provider import GoogleProvider
from bisheng.user_sync.domain.providers.ldap_provider import LdapProvider
from bisheng.user_sync.domain.providers.oidc_provider import OidcProvider
from bisheng.user_sync.domain.providers.oauth_provider import OAuthProvider

__all__ = [
    "AuthResult",
    "CasdoorProvider",
    "GoogleProvider",
    "LdapProvider",
    "OAuthProvider",
    "OidcProvider",
    "SyncOptions",
    "UserAttrs",
    "UserSyncProvider",
]
