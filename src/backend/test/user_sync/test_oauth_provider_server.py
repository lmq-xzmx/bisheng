"""Tests for OAuth Provider Server (BiSheng as Authorization Server)."""

import base64
import hashlib
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bisheng.main import app


class TestOAuthProviderService:
    """Unit tests for OAuthProviderService."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        mock = MagicMock()
        mock.setex = MagicMock()
        mock.get = MagicMock(return_value=None)
        mock.getdel = MagicMock(return_value=None)
        mock.delete = MagicMock()
        return mock

    @pytest.fixture
    def mock_oauth_server_client_dao(self):
        """Mock OAuthServerClientDao."""
        with patch("bisheng.user_sync.domain.services.oauth_provider_service.OAuthServerClientDao") as mock:
            yield mock

    def create_code_challenge(self, verifier: str, method: str = "S256") -> str:
        """Create PKCE code challenge."""
        if method == "S256":
            digest = hashlib.sha256(verifier.encode()).digest()
            return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return verifier

    def test_pkce_verify_s256(self, mock_redis):
        """Test PKCE S256 verification."""
        with patch(
            "bisheng.user_sync.domain.services.oauth_provider_service.get_redis_client", return_value=mock_redis
        ):
            from bisheng.user_sync.domain.services.oauth_provider_service import OAuthProviderService

            service = OAuthProviderService()
            service._redis_client = mock_redis

            verifier = "this_is_a_secure_verifier_string_12345"
            challenge = self.create_code_challenge(verifier, "S256")

            from bisheng.user_sync.domain.services.oauth_provider_service import AuthorizationCode

            auth_code = AuthorizationCode(
                code="test_code",
                client_id="test_client",
                user_id=1,
                redirect_uri="https://example.com/callback",
                scopes=["openid", "profile"],
                expires_at=0,
                code_challenge=challenge,
                code_challenge_method="S256",
            )

            assert service._verify_pkce(verifier, auth_code) is True

    def test_pkce_verify_plain(self, mock_redis):
        """Test PKCE plain verification."""
        with patch(
            "bisheng.user_sync.domain.services.oauth_provider_service.get_redis_client", return_value=mock_redis
        ):
            from bisheng.user_sync.domain.services.oauth_provider_service import OAuthProviderService

            service = OAuthProviderService()
            service._redis_client = mock_redis

            verifier = "plain_verifier"
            auth_code = MagicMock()
            auth_code.code_challenge = verifier
            auth_code.code_challenge_method = "plain"

            assert service._verify_pkce(verifier, auth_code) is True

    def test_pkce_verify_invalid(self, mock_redis):
        """Test PKCE verification with wrong verifier."""
        with patch(
            "bisheng.user_sync.domain.services.oauth_provider_service.get_redis_client", return_value=mock_redis
        ):
            from bisheng.user_sync.domain.services.oauth_provider_service import OAuthProviderService

            service = OAuthProviderService()
            service._redis_client = mock_redis

            verifier = "correct_verifier"
            wrong_verifier = "wrong_verifier"
            challenge = self.create_code_challenge(verifier, "S256")

            auth_code = MagicMock()
            auth_code.code_challenge = challenge
            auth_code.code_challenge_method = "S256"

            assert service._verify_pkce(wrong_verifier, auth_code) is False

    def test_validate_scopes(self):
        """Test scope validation."""
        with patch("bisheng.user_sync.domain.services.oauth_provider_service.get_redis_client"):
            from bisheng.user_sync.domain.services.oauth_provider_service import OAuthProviderService

            service = OAuthProviderService()

            client = {
                "allowed_scopes": ["openid", "profile", "email"],
            }

            # Valid scopes
            valid = service.validate_scopes(client, ["openid", "profile"])
            assert set(valid) == {"openid", "profile"}

            # With unknown scope
            valid = service.validate_scopes(client, ["openid", "profile", "unknown"])
            assert set(valid) == {"openid", "profile"}

            # Empty request uses all allowed
            valid = service.validate_scopes(client, [])
            assert valid == []

    def test_validate_redirect_uri(self):
        """Test redirect URI validation."""
        with patch("bisheng.user_sync.domain.services.oauth_provider_service.get_redis_client"):
            from bisheng.user_sync.domain.services.oauth_provider_service import OAuthProviderService

            service = OAuthProviderService()

            client = {
                "redirect_uris": ["https://example.com/callback", "https://app.example.com/callback"],
            }

            assert service.validate_redirect_uri(client, "https://example.com/callback") is True
            assert service.validate_redirect_uri(client, "https://evil.com/callback") is False


class TestOAuthProviderAPI:
    """Integration tests for OAuth Provider API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_service(self):
        """Mock OAuthProviderService."""
        with patch("bisheng.user_sync.api.oauth_provider_server.get_provider_service") as mock:
            yield mock

    def test_wellknown_openid_configuration(self, client):
        """Test OIDC Discovery endpoint."""
        with patch("bisheng.user_sync.api.oauth_provider_server.get_provider_service") as mock:
            mock_service = MagicMock()
            mock_service.get_oidc_discovery = AsyncMock(
                return_value={
                    "issuer": "https://example.com",
                    "authorization_endpoint": "https://example.com/oauth/authorize",
                    "token_endpoint": "https://example.com/oauth/token",
                }
            )
            mock.return_value = mock_service

            response = client.get("/oauth/.well-known/openid-configuration")
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200
            assert "issuer" in data["data"]

    def test_wellknown_jwks(self, client):
        """Test JWKS endpoint."""
        with patch("bisheng.user_sync.api.oauth_provider_server.get_provider_service") as mock:
            mock_service = MagicMock()
            mock_service.get_jwks = MagicMock(
                return_value={
                    "keys": [
                        {
                            "kty": "oct",
                            "alg": "HS256",
                            "use": "sig",
                            "kid": "test_key_id",
                        }
                    ]
                }
            )
            mock.return_value = mock_service

            response = client.get("/oauth/.well-known/jwks.json")
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200
            assert "keys" in data["data"]

    def test_authorize_missing_params(self, client):
        """Test authorize endpoint with missing parameters."""
        response = client.get("/oauth/authorize")
        assert response.status_code == 422  # Validation error

    def test_authorize_invalid_client(self, client):
        """Test authorize endpoint with invalid client."""
        with patch("bisheng.user_sync.api.oauth_provider_server.get_provider_service") as mock:
            mock_service = MagicMock()
            mock_service.get_client = AsyncMock(return_value=None)
            mock.return_value = mock_service

            response = client.get(
                "/oauth/authorize",
                params={
                    "response_type": "code",
                    "client_id": "nonexistent",
                    "redirect_uri": "https://example.com/callback",
                },
            )
            assert response.status_code == 400

    def test_token_missing_grant_type(self, client):
        """Test token endpoint with missing grant_type."""
        response = client.post(
            "/oauth/token",
            data={},
        )
        assert response.status_code == 422

    def test_token_unsupported_grant_type(self, client):
        """Test token endpoint with unsupported grant_type."""
        with patch("bisheng.user_sync.api.oauth_provider_server.get_provider_service") as mock:
            mock_service = MagicMock()
            mock.return_value = mock_service

            response = client.post(
                "/oauth/token",
                data={
                    "grant_type": "unsupported",
                    "client_id": "test",
                    "client_secret": "test",
                },
            )
            assert response.status_code == 400
            assert "Unsupported" in response.json()["detail"][0]["msg"]

    def test_register_client_validation(self, client):
        """Test client registration validation."""
        # Missing redirect_uris
        response = client.post(
            "/oauth/register",
            json={},
        )
        assert response.status_code == 400

        # Invalid grant_types
        response = client.post(
            "/oauth/register",
            json={
                "redirect_uris": ["https://example.com/callback"],
                "grant_types": ["invalid"],
            },
        )
        assert response.status_code == 400

    def test_register_client_success(self, client):
        """Test successful client registration."""
        with patch("bisheng.user_sync.api.oauth_provider_server.get_provider_service"):
            with patch("bisheng.user_sync.api.oauth_provider_server.OAuthServerClientDao") as mock_dao:
                mock_client = MagicMock()
                mock_client.client_id = "test_client_id"
                mock_client.client_secret = "test_secret"
                mock_client.client_id_issued_at = 1234567890
                mock_client.client_secret_expires_at = 0
                mock_client.redirect_uris = ["https://example.com/callback"]
                mock_client.grant_types = ["authorization_code", "refresh_token"]
                mock_client.allowed_scopes = ["openid", "profile", "email"]
                mock_client.token_endpoint_auth_method = "client_secret_basic"
                mock_client.client_name = "Test App"
                mock_dao.aregister_client = AsyncMock(return_value=mock_client)

                response = client.post(
                    "/oauth/register",
                    json={
                        "client_name": "Test App",
                        "redirect_uris": ["https://example.com/callback"],
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 200
                assert data["data"]["client_secret"] == "test_secret"


class TestClientRegistrationRequest:
    """Tests for ClientRegistrationRequest model."""

    def test_valid_request(self):
        """Test valid client registration request."""
        from bisheng.user_sync.api.oauth_provider_server import ClientRegistrationRequest

        request = ClientRegistrationRequest(
            client_name="Test App",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code"],
            allowed_scopes=["openid", "profile"],
        )
        assert request.client_name == "Test App"
        assert request.redirect_uris == ["https://example.com/callback"]

    def test_default_values(self):
        """Test default values."""
        from bisheng.user_sync.api.oauth_provider_server import ClientRegistrationRequest

        request = ClientRegistrationRequest(
            redirect_uris=["https://example.com/callback"],
        )
        assert request.grant_types is None
        assert request.allowed_scopes is None
        assert request.token_endpoint_auth_method == "client_secret_basic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
