"""User API module - combines user, role, and two_factor routers."""

from fastapi import APIRouter

from bisheng.user.api import role, two_factor, user

# Combined router with all user-related endpoints
router = APIRouter(prefix="", tags=["User"])

# Include all sub-routers
router.include_router(user.router)
router.include_router(role.router)
router.include_router(two_factor.router)
