"""TOTP-based Two-Factor Authentication service."""

import hashlib
import secrets
from dataclasses import dataclass

import pyotp


@dataclass
class TwoFactorSetup:
    """2FA setup result."""

    secret: str  # Base32 encoded TOTP secret
    otpauth_uri: str  # OTP Auth URI for QR code
    backup_codes: list[str]  # One-time backup codes


@dataclass
class TwoFactorVerifyResult:
    """2FA verification result."""

    success: bool
    requires_2fa: bool = False
    temp_token: str | None = None
    error_message: str | None = None


class TOTPService:
    """Service for TOTP-based two-factor authentication."""

    # TOTP parameters
    ISSUER_NAME = "BiSheng"
    DIGITS = 6
    INTERVAL = 30  # seconds
    BACKUP_CODE_COUNT = 8
    BACKUP_CODE_LENGTH = 8

    @classmethod
    def generate_secret(cls) -> str:
        """Generate a new TOTP secret."""
        return pyotp.random_base32()

    @classmethod
    def generate_otpauth_uri(cls, secret: str, user_email: str) -> str:
        """Generate OTP Auth URI for QR code scanning."""
        totp = pyotp.TOTP(
            secret,
            digits=cls.DIGITS,
            interval=cls.INTERVAL,
        )
        return totp.provisioning_uri(
            name=user_email,
            issuer_name=cls.ISSUER_NAME,
        )

    @classmethod
    def verify_token(cls, secret: str, token: str, valid_window: int = 1) -> bool:
        """
        Verify a TOTP token.

        Args:
            secret: Base32 encoded TOTP secret
            token: 6-digit token from authenticator app
            valid_window: Number of intervals before/after current time to accept

        Returns:
            True if token is valid
        """
        try:
            totp = pyotp.TOTP(
                secret,
                digits=cls.DIGITS,
                interval=cls.INTERVAL,
            )
            return totp.verify(token, valid_window=valid_window)
        except Exception:
            return False

    @classmethod
    def generate_backup_codes(cls) -> tuple[list[str], list[str]]:
        """
        Generate backup codes.

        Returns:
            Tuple of (plain_codes, hashed_codes).
            Plain codes are shown to user once, hashed codes are stored in DB.
        """
        plain_codes = []
        hashed_codes = []

        for _ in range(cls.BACKUP_CODE_COUNT):
            # Generate random backup code
            code = secrets.token_urlsafe(cls.BACKUP_CODE_LENGTH)[:cls.BACKUP_CODE_LENGTH].upper()
            # Replace URL-safe chars with alphanumeric only
            code = ''.join(c for c in code if c.isalnum())
            # Ensure minimum length
            while len(code) < cls.BACKUP_CODE_LENGTH:
                code += secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

            plain_codes.append(code)
            hashed_codes.append(cls._hash_backup_code(code))

        return plain_codes, hashed_codes

    @staticmethod
    def _hash_backup_code(code: str) -> str:
        """Hash a backup code for storage."""
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def verify_backup_code(cls, code: str, hashed_codes: list[str]) -> bool:
        """Verify a backup code against stored hashes."""
        code = code.upper().strip()
        hashed_input = cls._hash_backup_code(code)

        for stored_hash in hashed_codes:
            if secrets.compare_digest(hashed_input, stored_hash):
                return True
        return False

    @classmethod
    def remove_used_backup_code(cls, code: str, hashed_codes: list[str]) -> list[str]:
        """Remove a used backup code from the list."""
        code = code.upper().strip()
        hashed_input = cls._hash_backup_code(code)
        return [h for h in hashed_codes if not secrets.compare_digest(h, hashed_input)]

    @classmethod
    def create_setup(cls, user_email: str) -> TwoFactorSetup:
        """Create a new 2FA setup."""
        secret = cls.generate_secret()
        otpauth_uri = cls.generate_otpauth_uri(secret, user_email)
        plain_codes, _hashed_codes = cls.generate_backup_codes()

        return TwoFactorSetup(
            secret=secret,
            otpauth_uri=otpauth_uri,
            backup_codes=plain_codes,  # Return plain codes to show user once
        )

    @classmethod
    def get_hashed_backup_codes(cls) -> tuple[list[str], list[str]]:
        """Get hashed backup codes for storage (used during setup confirmation)."""
        return cls.generate_backup_codes()
