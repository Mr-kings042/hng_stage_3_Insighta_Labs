"""Phase 1 Authentication System Tests"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
import jwt
import json
from unittest.mock import patch, AsyncMock

from main import app
from database import get_db
from models import User, Session as SessionModel
from auth.oauth import GitHubOAuthHandler
from auth.tokens import TokenManager
from sqlalchemy.orm import Session


client = TestClient(app)


class TestGitHubOAuthHandler:
    """Test GitHub OAuth with PKCE"""

    def test_generate_state(self):
        """Test state generation for CSRF protection"""
        state = GitHubOAuthHandler.generate_state()
        assert isinstance(state, str)
        assert len(state) > 0

    def test_generate_pkce_pair(self):
        """Test PKCE pair generation"""
        code_verifier, code_challenge = GitHubOAuthHandler.generate_pkce_pair()
        assert isinstance(code_verifier, str)
        assert isinstance(code_challenge, str)
        assert len(code_verifier) >= 43
        assert len(code_challenge) > 0

    def test_get_authorization_url(self):
        """Test OAuth authorization URL generation"""
        with patch.dict("os.environ", {
            "GITHUB_CLIENT_ID": "test_client_id",
            "GITHUB_CLIENT_SECRET": "test_secret",
        }):
            handler = GitHubOAuthHandler()
            state = "test_state"
            code_challenge = "test_challenge"
            
            url = handler.get_authorization_url(state, code_challenge)
            
            assert "github.com" in url
            assert "client_id=test_client_id" in url
            assert "state=test_state" in url
            assert "code_challenge=test_challenge" in url


class TestTokenManager:
    """Test JWT token generation and validation"""

    def test_generate_access_token(self):
        """Test access token generation"""
        token_manager = TokenManager()
        token = token_manager.generate_access_token("test_user_id", "analyst")
        
        assert isinstance(token, str)
        
        # Decode and verify
        payload = jwt.decode(token, token_manager.secret_key, algorithms=[token_manager.algorithm])
        assert payload["user_id"] == "test_user_id"
        assert payload["role"] == "analyst"
        assert payload["type"] == "access"

    def test_generate_refresh_token(self):
        """Test refresh token generation"""
        token_manager = TokenManager()
        token = token_manager.generate_refresh_token("test_user_id")
        
        assert isinstance(token, str)
        
        # Decode and verify
        payload = jwt.decode(token, token_manager.secret_key, algorithms=[token_manager.algorithm])
        assert payload["user_id"] == "test_user_id"
        assert payload["type"] == "refresh"

    def test_validate_access_token(self):
        """Test access token validation"""
        token_manager = TokenManager()
        token = token_manager.generate_access_token("test_user_id", "admin")
        
        payload = token_manager.validate_access_token(token)
        assert payload["user_id"] == "test_user_id"
        assert payload["role"] == "admin"

    def test_validate_expired_access_token(self):
        """Test that expired tokens are rejected"""
        token_manager = TokenManager()
        
        # Create an expired token manually
        payload = {
            "user_id": "test_user",
            "role": "analyst",
            "jti": "test_jti",
            "type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=1),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = jwt.encode(payload, token_manager.secret_key, algorithm=token_manager.algorithm)
        
        with pytest.raises(jwt.ExpiredSignatureError):
            token_manager.validate_access_token(expired_token)

    def test_hash_token(self):
        """Test token hashing"""
        token = "test_token_value"
        hash1 = TokenManager.hash_token(token)
        hash2 = TokenManager.hash_token(token)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length


class TestRBACPermissions:
    """Test role-based access control"""

    def test_admin_role(self):
        """Test admin role identification"""
        token_manager = TokenManager()
        token = token_manager.generate_access_token("admin_user_id", "admin")
        
        payload = token_manager.validate_access_token(token)
        assert payload["role"] == "admin"

    def test_analyst_role(self):
        """Test analyst role identification"""
        token_manager = TokenManager()
        token = token_manager.generate_access_token("analyst_user_id", "analyst")
        
        payload = token_manager.validate_access_token(token)
        assert payload["role"] == "analyst"


class TestAuthEndpoints:
    """Test authentication endpoints"""

    @patch.dict("os.environ", {
        "GITHUB_CLIENT_ID": "test_client_id",
        "GITHUB_CLIENT_SECRET": "test_secret",
        "BACKEND_URL": "http://localhost:8000",
    })
    def test_github_oauth_start_endpoint(self):
        """Test GET /auth/github endpoint"""
        response = client.get("/auth/github?client_type=web")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "authorization_url" in data
        assert "state" in data
        assert "code_verifier" in data

    def test_whoami_unauthorized(self):
        """Test that /auth/whoami requires authentication"""
        response = client.get("/auth/whoami")
        
        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"

    def test_logout_unauthorized(self):
        """Test that /auth/logout requires authentication"""
        response = client.post("/auth/logout")
        
        assert response.status_code == 401


class TestAPIVersioning:
    """Test API versioning requirement"""

    def test_missing_api_version_header(self):
        """Test that missing X-API-Version header is rejected"""
        response = client.get("/api/profiles")
        
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "API version header required" in data["message"]

    def test_invalid_api_version(self):
        """Test that invalid X-API-Version is rejected"""
        response = client.get("/api/profiles", headers={"X-API-Version": "2"})
        
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"

    def test_correct_api_version_without_auth(self):
        """Test that correct API version but missing auth is rejected with 401"""
        response = client.get("/api/profiles", headers={"X-API-Version": "1"})
        
        # Should fail on auth, not API version
        assert response.status_code == 401


class TestErrorEnvelope:
    """Test consistent error response format"""

    def test_error_envelope_format(self):
        """Test that errors follow standard format: {status: error, message: string}"""
        # Missing API version
        response = client.get("/api/profiles")
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert isinstance(data["message"], str)


class TestHealthEndpoints:
    """Test health check endpoints"""

    def test_root_endpoint(self):
        """Test GET / endpoint"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "version" in data

    def test_health_endpoint(self):
        """Test GET /health endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# Summary
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Phase 1 - Backend Foundation Tests")
    print("="*60)
    print("\nTo run all tests:")
    print("  pytest test_phase1_auth.py -v")
    print("\nTo run specific test class:")
    print("  pytest test_phase1_auth.py::TestTokenManager -v")
    print("\n" + "="*60)
