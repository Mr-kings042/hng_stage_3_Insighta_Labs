"""JWT token generation and validation"""

import os
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from sqlalchemy.orm import Session
from models import Session as SessionModel


class TokenManager:
    """Handle JWT token generation and validation"""

    def __init__(self):
        self.secret_key = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.access_token_expiry = int(os.getenv("ACCESS_TOKEN_EXPIRY", 180))  # 3 minutes
        self.refresh_token_expiry = int(os.getenv("REFRESH_TOKEN_EXPIRY", 300))  # 5 minutes

    def generate_access_token(self, user_id: str, user_role: str) -> str:
        """
        Generate JWT access token
        
        Args:
            user_id: UUID of user
            user_role: User role (admin or analyst)
            
        Returns:
            JWT access token
        """
        jti = str(uuid.uuid4())
        payload = {
            "user_id": user_id,
            "role": user_role,
            "jti": jti,
            "type": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=self.access_token_expiry),
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def generate_refresh_token(self, user_id: str) -> str:
        """
        Generate JWT refresh token
        
        Args:
            user_id: UUID of user
            
        Returns:
            JWT refresh token
        """
        payload = {
            "user_id": user_id,
            "type": "refresh",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=self.refresh_token_expiry),
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def validate_access_token(self, token: str) -> dict:
        """
        Validate and decode JWT access token
        
        Args:
            token: JWT access token
            
        Returns:
            Decoded token payload
            
        Raises:
            jwt.ExpiredSignatureError: If token is expired
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Check token type
            if payload.get("type") != "access":
                raise jwt.InvalidTokenError("Invalid token type")

            return payload
        except jwt.ExpiredSignatureError:
            raise
        except jwt.InvalidTokenError:
            raise

    def validate_refresh_token(self, token: str) -> dict:
        """
        Validate and decode JWT refresh token
        
        Args:
            token: JWT refresh token
            
        Returns:
            Decoded token payload
            
        Raises:
            jwt.ExpiredSignatureError: If token is expired
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Check token type
            if payload.get("type") != "refresh":
                raise jwt.InvalidTokenError("Invalid token type")

            return payload
        except jwt.ExpiredSignatureError:
            raise
        except jwt.InvalidTokenError:
            raise

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash a token for database storage (for refresh tokens)
        
        Args:
            token: Raw token
            
        Returns:
            Hashed token
        """
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    async def create_session(
        user_id: str,
        refresh_token: str,
        access_token_jti: str,
        client_type: str,
        db: Session,
    ) -> SessionModel:
        """
        Create session record in database
        
        Args:
            user_id: UUID of user
            refresh_token: Refresh token (will be hashed)
            access_token_jti: JTI from access token
            client_type: web or cli
            db: Database session
            
        Returns:
            Session model instance
        """
        token_hash = TokenManager.hash_token(refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(os.getenv("REFRESH_TOKEN_EXPIRY", 300)))

        session = SessionModel(
            user_id=user_id,
            refresh_token_hash=token_hash,
            access_token_jti=access_token_jti,
            expires_at=expires_at,
            is_revoked=False,
            client_type=client_type,
        )

        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def revoke_refresh_token(token: str, db: Session) -> bool:
        """
        Revoke a refresh token by marking session as revoked
        
        Args:
            token: Refresh token
            db: Database session
            
        Returns:
            True if successfully revoked, False if not found
        """
        token_hash = TokenManager.hash_token(token)
        session = (
            db.query(SessionModel)
            .filter(
                SessionModel.refresh_token_hash == token_hash,
                SessionModel.is_revoked == False,
            )
            .first()
        )

        if session:
            session.is_revoked = True
            db.commit()
            return True

        return False

    @staticmethod
    def verify_session_valid(token: str, db: Session) -> bool:
        """
        Check if session is still valid (not revoked, not expired)
        
        Args:
            token: Refresh token
            db: Database session
            
        Returns:
            True if session is valid, False otherwise
        """
        token_hash = TokenManager.hash_token(token)
        session = (
            db.query(SessionModel)
            .filter(
                SessionModel.refresh_token_hash == token_hash,
                SessionModel.is_revoked == False,
                SessionModel.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )

        return session is not None
