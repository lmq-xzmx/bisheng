"""Two-Factor Authentication API endpoints."""

from fastapi import APIRouter, Body, Depends

from bisheng.common.dependencies.user_deps import UserPayload
from bisheng.common.schemas.api import resp_200, resp_500
from bisheng.user_sync.domain.services.two_factor.totp_service import TOTPService

router = APIRouter(prefix="/user/2fa", tags=["2fa"])


@router.get("/status")
async def get_2fa_status(
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Get current user's 2FA status."""
    try:
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user.user_id)
        if not db_user:
            return resp_500(404, "User not found")

        return resp_200({
            "enabled": bool(db_user.totp_secret and db_user.two_factor_enabled),
            "has_backup_codes": bool(db_user.backup_codes),
        })
    except Exception as e:
        return resp_500(500, str(e))


@router.post("/setup")
async def initiate_2fa_setup(
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """
    Initiate 2FA setup.

    Generates a TOTP secret and backup codes.
    The secret is stored temporarily until confirmed.
    """
    try:
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user.user_id)
        if not db_user:
            return resp_500(404, "User not found")

        if db_user.two_factor_enabled:
            return resp_500(400, "2FA is already enabled")

        # Generate 2FA setup
        setup = TOTPService.create_setup(db_user.email or db_user.user_name)

        # Store the secret temporarily (not confirmed yet)
        db_user.totp_secret = setup.secret
        # Store hashed backup codes
        _, hashed_codes = TOTPService.get_hashed_backup_codes()
        db_user.backup_codes = hashed_codes
        await UserDao.aupdate_user(db_user)

        return resp_200({
            "secret": setup.secret,
            "otpauth_uri": setup.otpauth_uri,
            "backup_codes": setup.backup_codes,
        })
    except Exception as e:
        return resp_500(500, str(e))


@router.post("/verify-and-enable")
async def verify_and_enable_2fa(
    token: str = Body(...),
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Verify TOTP token and enable 2FA."""
    try:
        from bisheng.common.errcode.user import UserTwoFactorVerifyFailedError
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user.user_id)
        if not db_user:
            return resp_500(404, "User not found")

        if not db_user.totp_secret:
            return resp_500(400, "2FA setup not initiated")

        if not TOTPService.verify_token(db_user.totp_secret, token):
            raise UserTwoFactorVerifyFailedError.http_exception()

        db_user.two_factor_enabled = True
        await UserDao.aupdate_user(db_user)

        return resp_200({
            "enabled": True,
            "message": "2FA has been enabled successfully",
        })
    except Exception as e:
        if hasattr(e, 'http_exception'):
            raise e.http_exception()
        return resp_500(500, str(e))


@router.post("/disable")
async def disable_2fa(
    token: str = Body(...),
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Disable 2FA."""
    try:
        from bisheng.common.errcode.user import UserTwoFactorVerifyFailedError
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user.user_id)
        if not db_user:
            return resp_500(404, "User not found")

        if not db_user.two_factor_enabled:
            return resp_500(400, "2FA is not enabled")

        if not TOTPService.verify_token(db_user.totp_secret or "", token):
            raise UserTwoFactorVerifyFailedError.http_exception()

        db_user.two_factor_enabled = False
        db_user.totp_secret = None
        db_user.backup_codes = None
        await UserDao.aupdate_user(db_user)

        return resp_200({
            "enabled": False,
            "message": "2FA has been disabled",
        })
    except Exception as e:
        if hasattr(e, 'http_exception'):
            raise e.http_exception()
        return resp_500(500, str(e))


@router.post("/verify")
async def verify_2fa(
    token: str = Body(...),
    user_id: int = Body(...),
):
    """Verify 2FA token during login."""
    try:
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user_id)
        if not db_user:
            return resp_500(404, "User not found")

        if not db_user.totp_secret or not db_user.two_factor_enabled:
            return resp_500(400, "2FA is not enabled for this user")

        # Check backup code first
        if len(token.replace("-", "").replace(" ", "")) == TOTPService.BACKUP_CODE_LENGTH and db_user.backup_codes:
            if TOTPService.verify_backup_code(token, db_user.backup_codes):
                db_user.backup_codes = TOTPService.remove_used_backup_code(token, db_user.backup_codes)
                await UserDao.aupdate_user(db_user)
                temp_token = _create_temp_token(db_user)
                return resp_200({
                    "success": True,
                    "temp_token": temp_token,
                })

        if not TOTPService.verify_token(db_user.totp_secret, token):
            return resp_500(401, "Invalid verification code")

        temp_token = _create_temp_token(db_user)
        return resp_200({
            "success": True,
            "temp_token": temp_token,
        })
    except Exception as e:
        return resp_500(500, str(e))


@router.post("/backup-codes/regenerate")
async def regenerate_backup_codes(
    user: UserPayload = Depends(UserPayload.get_login_user),
):
    """Regenerate backup codes."""
    try:
        from bisheng.user.domain.models.user import UserDao

        db_user = await UserDao.aget_user(user.user_id)
        if not db_user:
            return resp_500(404, "User not found")

        if not db_user.two_factor_enabled or not db_user.totp_secret:
            return resp_500(400, "2FA must be enabled to regenerate backup codes")

        plain_codes, hashed_codes = TOTPService.generate_backup_codes()
        db_user.backup_codes = hashed_codes
        await UserDao.aupdate_user(db_user)

        return resp_200({
            "backup_codes": plain_codes,
        })
    except Exception as e:
        return resp_500(500, str(e))


def _create_temp_token(user) -> str:
    """Create a temporary token for 2FA-verified sessions."""
    import time

    from common.services.config_service import settings

    payload = {
        "sub": str(user.user_id),
        "type": "2fa_temp",
        "exp": time.time() + 300,
    }
    import jwt

    jwt_secret = getattr(settings, "jwt_secret", "default-secret")
    return jwt.encode(payload, jwt_secret, algorithm="HS256")
