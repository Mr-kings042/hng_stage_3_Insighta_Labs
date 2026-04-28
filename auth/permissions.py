"""Role-based access control decorators"""

from functools import wraps
from fastapi import HTTPException, Depends, Request
from sqlalchemy.orm import Session
from database import get_db
from models import User
from auth.tokens import TokenManager
import jwt


class CurrentUser:
    """Dependency to get current authenticated user"""

    @staticmethod
    async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
        """
        Extract and validate current user from JWT token
        
        Args:
            request: FastAPI request object
            db: Database session
            
        Returns:
            User object
            
        Raises:
            HTTPException: If not authenticated or token invalid
        """
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            token_manager = TokenManager()
            payload = token_manager.validate_access_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Access token expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail="Invalid access token")

        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="User account is inactive")

        return user


def admin_only(func):
    """
    Decorator to restrict endpoint to admin users only
    
    Usage:
        @router.post("/profiles")
        @admin_only
        async def create_profile(current_user: User = Depends(CurrentUser.get_current_user)):
            ...
    """

    @wraps(func)
    async def wrapper(*args, current_user: User = None, **kwargs):
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Admin access required",
            )

        return await func(*args, current_user=current_user, **kwargs)

    return wrapper


def analyst_only(func):
    """
    Decorator to restrict endpoint to analyst users (and admins)
    
    Usage:
        @router.get("/profiles")
        @analyst_only
        async def get_profiles(current_user: User = Depends(CurrentUser.get_current_user)):
            ...
    """

    @wraps(func)
    async def wrapper(*args, current_user: User = None, **kwargs):
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if current_user.role not in ["analyst", "admin"]:
            raise HTTPException(
                status_code=403,
                detail="Analyst access required",
            )

        return await func(*args, current_user=current_user, **kwargs)

    return wrapper


def authenticated(func):
    """
    Decorator to restrict endpoint to authenticated users only
    
    Usage:
        @router.get("/users/me")
        @authenticated
        async def get_current_user_info(current_user: User = Depends(CurrentUser.get_current_user)):
            ...
    """

    @wraps(func)
    async def wrapper(*args, current_user: User = None, **kwargs):
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")

        return await func(*args, current_user=current_user, **kwargs)

    return wrapper
