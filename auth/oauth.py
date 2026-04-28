"""GitHub OAuth handler with PKCE support"""

import os
import secrets
import hashlib
import base64
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from models import User


class GitHubOAuthHandler:
    """Handle GitHub OAuth flow with PKCE"""

    GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_USER_URL = "https://api.github.com/user"

    def __init__(self):
        self.client_id = os.getenv("GITHUB_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET")
        self.backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set in environment"
            )

    @staticmethod
    def generate_state() -> str:
        """Generate a random state string for CSRF protection"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
       """Generate PKCE code_verifier and code_challenge pair"""
    
    # Verifier: 43-128 chars (URL-safe, NO padding)
       code_verifier_bytes = secrets.token_bytes(32)  # 32 bytes → ~43 chars
       code_verifier = base64.urlsafe_b64encode(code_verifier_bytes).decode('utf-8').rstrip('=')
    
   
       challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
       code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
    
    # DEBUG: Print lengths
    # print(f"Verifier len: {len(code_verifier)}")  # 43
    # print(f"Challenge len: {len(code_challenge)}") # MUST = 43
    
       assert len(code_challenge) == 43, f"Challenge wrong length: {len(code_challenge)}"
    
       return code_verifier, code_challenge
    # @staticmethod
    # def generate_pkce_pair() -> tuple[str, str]:
    #     """
    #     Generate PKCE code_verifier and code_challenge pair
        
    #     Returns:
    #         (code_verifier, code_challenge)
    #     """
    #     # Generate random code_verifier (43-128 characters)
    #     code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8")
    #     code_verifier = code_verifier.rstrip("=")  # Remove padding

    #     # Generate code_challenge from code_verifier
    #     code_challenge = (
    #         base64.urlsafe_b64encode(
    #             hashlib.sha256(code_verifier.encode("utf-8")).digest()
    #         )
    #         .decode("utf-8")
    #         .rstrip("=")
    #     )

    #     return code_verifier, code_challenge

    def get_authorization_url(self, state: str, code_challenge: str) -> str:
        """
        Get GitHub OAuth authorization URL
        
        Args:
            state: CSRF protection state
            code_challenge: PKCE code challenge
            
        Returns:
            Full GitHub OAuth URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": f"{self.backend_url}/auth/github/callback",
            "scope": "user:email",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.GITHUB_AUTHORIZE_URL}?{query_string}"

    async def exchange_code_for_token(self, code: str, code_verifier: str) -> dict:
        """
        Exchange authorization code for access token with GitHub
        
        Args:
            code: Authorization code from GitHub
            code_verifier: PKCE code verifier
            
        Returns:
            Dictionary with access_token and other info
        """
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "code_verifier": code_verifier,
        }

        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GITHUB_ACCESS_TOKEN_URL, data=payload, headers=headers
            )

        response.raise_for_status()
        return response.json()

    async def get_user_info(self, access_token: str) -> dict:
        """
        Get user information from GitHub
        
        Args:
            access_token: GitHub access token
            
        Returns:
            Dictionary with user info: id, login, email, avatar_url, name
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(self.GITHUB_USER_URL, headers=headers)

        response.raise_for_status()
        return response.json()

    @staticmethod
    async def create_or_update_user(
        github_user: dict, db: Session
    ) -> tuple[User, bool]:
        """
        Create or update user in database from GitHub user data
        
        Args:
            github_user: GitHub API user response
            db: Database session
            
        Returns:
            (user, is_new) - User object and whether it was newly created
        """
        github_id = str(github_user["id"])

        # Try to find existing user
        existing_user = db.query(User).filter(User.github_id == github_id).first()

        if existing_user:
            # Update existing user
            existing_user.username = github_user.get("login", existing_user.username)
            existing_user.email = github_user.get("email", existing_user.email)
            existing_user.avatar_url = github_user.get(
                "avatar_url", existing_user.avatar_url
            )
            existing_user.last_login_at = datetime.utcnow()
            db.commit()
            return existing_user, False

        # Create new user
        new_user = User(
            github_id=github_id,
            username=github_user.get("login", f"user_{github_id}"),
            email=github_user.get("email"),
            avatar_url=github_user.get("avatar_url"),
            role="analyst",  # Default role
            is_active=True,
            last_login_at=datetime.utcnow(),
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user, True
