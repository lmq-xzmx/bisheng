"""User Sync API router."""

from fastapi import APIRouter

from bisheng.user_sync.api import admin_ldap, admin_oauth, ldap, oauth, oidc, providers

router = APIRouter(prefix="/user-sync", tags=["user-sync"])

router.include_router(ldap.router)
router.include_router(oauth.router)
router.include_router(providers.router)
router.include_router(admin_oauth.router)
router.include_router(admin_ldap.router)
router.include_router(oidc.router)
