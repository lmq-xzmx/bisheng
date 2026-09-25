"""Magic Link service - passwordless email authentication."""

import secrets
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger


class MagicLinkService:
    """Service for Magic Link (passwordless email) authentication."""

    TOKEN_TTL = 900  # 15 minutes
    TOKEN_LENGTH = 32

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(cls.TOKEN_LENGTH)

    @classmethod
    def create_magic_link(cls, token: str, base_url: str) -> str:
        """Create the full magic link URL."""
        return f"{base_url.rstrip('/')}/magic-link/verify?token={token}"

    @classmethod
    async def send_magic_link(
        cls,
        email: str,
        token: str,
        base_url: str,
        smtp_config: dict,
    ) -> bool:
        """
        Send magic link email via SMTP.

        Args:
            email: Recipient email address
            token: The magic link token
            base_url: Base URL of the application
            smtp_config: SMTP configuration dict with keys:
                - smtp_server: SMTP server address
                - smtp_port: SMTP port (587 for TLS, 465 for SSL)
                - smtp_username: SMTP username
                - smtp_password: SMTP password
                - smtp_from: From address (e.g., "BiSheng <noreply@example.com>")
                - use_tls: Use TLS (default True)

        Returns:
            True if email sent successfully
        """
        magic_link = cls.create_magic_link(token, base_url)

        subject = "Your BiSheng Login Link"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">Login to BiSheng</h2>
            <p>Click the button below to sign in to your account:</p>
            <p style="margin: 30px 0;">
                <a href="{magic_link}"
                   style="background-color: #4CAF50; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 4px; display: inline-block;">
                    Sign In to BiSheng
                </a>
            </p>
            <p style="color: #666; font-size: 14px;">
                This link will expire in 15 minutes.<br>
                If you didn't request this email, you can safely ignore it.
            </p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #999; font-size: 12px;">
                BiSheng - Enterprise LLM Application Platform
            </p>
        </body>
        </html>
        """

        text_body = f"""
        Login to BiSheng

        Click this link to sign in: {magic_link}

        This link will expire in 15 minutes.
        If you didn't request this email, you can safely ignore it.
        """

        try:
            cls._send_email(
                to_email=email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                smtp_config=smtp_config,
            )
            logger.info("Magic link email sent to %s", email)
            return True
        except Exception as e:
            logger.exception("Failed to send magic link email to %s: %s", email, e)
            return False

    @classmethod
    def _send_email(
        cls,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        smtp_config: dict,
    ) -> None:
        """Send email via SMTP."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_config.get("smtp_from", smtp_config.get("smtp_username"))
        msg["To"] = to_email

        # Attach both plain text and HTML versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)

        smtp_server = smtp_config["smtp_server"]
        smtp_port = smtp_config.get("smtp_port", 587)
        smtp_username = smtp_config["smtp_username"]
        smtp_password = smtp_config["smtp_password"]
        use_tls = smtp_config.get("use_tls", True)

        if smtp_config.get("use_ssl"):
            # SSL connection (port 465)
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_username, smtp_password)
                server.sendmail(msg["From"], [to_email], msg.as_string())
        elif use_tls:
            # TLS connection (port 587)
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_username, smtp_password)
                server.sendmail(msg["From"], [to_email], msg.as_string())
        else:
            # Plain connection (not recommended)
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.login(smtp_username, smtp_password)
                server.sendmail(msg["From"], [to_email], msg.as_string())

    @classmethod
    def get_smtp_config_from_settings(cls) -> dict | None:
        """Get SMTP config from application settings."""
        try:
            from bisheng.common.services.config_service import settings

            # Try to get email config from settings
            email_config = getattr(settings, "email", None)
            if not email_config:
                return None

            return {
                "smtp_server": getattr(email_config, "smtp_server", None),
                "smtp_port": getattr(email_config, "smtp_port", 587),
                "smtp_username": getattr(email_config, "smtp_username", None),
                "smtp_password": getattr(email_config, "smtp_password", None),
                "smtp_from": getattr(email_config, "smtp_from", None),
                "use_tls": getattr(email_config, "use_tls", True),
                "use_ssl": getattr(email_config, "use_ssl", False),
            }
        except Exception as e:
            logger.warning("Could not load SMTP config: %s", e)
            return None
