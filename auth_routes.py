"""Authentication endpoints"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime
import jwt

from database import get_db
from models import User
from auth.oauth import GitHubOAuthHandler
from auth.tokens import TokenManager
from auth.permissions import CurrentUser
from schema import UserResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github")
async def github_oauth_start(
    client_type: str = Query("web", description="web or cli"),
):
    """
    Start GitHub OAuth flow
    
    Returns JSON with OAuth authorization URL and PKCE data.
    For web clients, the authorization_url should be used to redirect to GitHub.
    For CLI clients, the state and code_verifier must be saved for later use.
    """
    try:
        oauth_handler = GitHubOAuthHandler()
        
        # Generate PKCE pair
        code_verifier, code_challenge = oauth_handler.generate_pkce_pair()
        
        # Generate state for CSRF protection
        state = oauth_handler.generate_state()
        
        # Get authorization URL
        auth_url = oauth_handler.get_authorization_url(state, code_challenge)
        
        return {
            "status": "success",
            "authorization_url": auth_url,
            "state": state,
            "code_verifier": code_verifier,
            "client_type": client_type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/github/callback")
async def github_oauth_callback(
    code: Optional[str] = Query(None, description="Authorization code from GitHub"),
    state: Optional[str] = Query(None, description="State parameter for CSRF validation"),
    error: Optional[str] = Query(None, description="Error from GitHub"),
    error_description: Optional[str] = Query(None, description="Error description"),
    code_verifier: Optional[str] = Query(None, description="PKCE code verifier (optional)"),
    db: Session = Depends(get_db),
):
    """
    Handle GitHub OAuth callback
    
    Validates:
    - code is present
    - state is present
    - code and state are valid
    
    For browser redirects: Returns JSON response
    For CLI: Expects code_verifier in query to complete exchange
    """
    try:
        # Check for OAuth errors from GitHub
        if error:
            error_msg = error_description or error
            raise HTTPException(
                status_code=400,
                detail=f"OAuth error from GitHub: {error_msg}",
            )
        
        # Validate code is present
        if not code:
            raise HTTPException(
                status_code=400,
                detail="Missing authorization code",
            )
        
        # Validate state is present
        if not state:
            raise HTTPException(
                status_code=400,
                detail="Missing state parameter - CSRF token validation failed",
            )
        
        oauth_handler = GitHubOAuthHandler()
        
        # If client did not provide code_verifier (browser redirect), return instructions
        if not code_verifier:
            return {
                "status": "partial",
                "message": "Authorization code received. POST the code_verifier to /auth/github/complete to finish authorization.",
                "code": code,
                "state": state,
            }
        
        # Exchange code for GitHub token
        try:
            github_token_response = await oauth_handler.exchange_code_for_token(code, code_verifier)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid code or code_verifier: {str(e)}",
            )
        
        github_access_token = github_token_response.get("access_token")
        
        if not github_access_token:
            raise HTTPException(
                status_code=400,
                detail="Failed to obtain GitHub access token",
            )
        
        # Get user info from GitHub
        github_user = await oauth_handler.get_user_info(github_access_token)
        
        # Create or update user in database
        user, is_new = await oauth_handler.create_or_update_user(github_user, db)
        
        # Generate tokens
        token_manager = TokenManager()
        access_token = token_manager.generate_access_token(str(user.id), user.role)
        refresh_token = token_manager.generate_refresh_token(str(user.id))
        
        # Get JTI from access token
        access_payload = jwt.decode(
            access_token,
            token_manager.secret_key,
            algorithms=[token_manager.algorithm],
        )
        access_token_jti = access_payload.get("jti")
        
        # Create session
        await TokenManager.create_session(
            str(user.id),
            refresh_token,
            access_token_jti,
            "web",
            db,
        )
        
        return {
            "status": "success",
            "user": user.to_dict(),
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": token_manager.access_token_expiry,
            },
            "is_new_user": is_new,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/github/complete")
async def github_oauth_complete(
    request_body: dict,
    db: Session = Depends(get_db),
):
    """
    Complete GitHub OAuth PKCE exchange.

    Expects JSON body: {"code": "...", "state": "...", "code_verifier": "..."}
    Returns tokens and user info on success.
    """
    try:
        code = request_body.get("code")
        state = request_body.get("state")
        code_verifier = request_body.get("code_verifier")

        if not code or not code_verifier:
            raise HTTPException(status_code=400, detail="code and code_verifier are required")

        oauth_handler = GitHubOAuthHandler()

        github_token_response = await oauth_handler.exchange_code_for_token(code, code_verifier)
        github_access_token = github_token_response.get("access_token")

        if not github_access_token:
            raise HTTPException(status_code=400, detail="Failed to obtain GitHub access token")

        github_user = await oauth_handler.get_user_info(github_access_token)

        user, is_new = await oauth_handler.create_or_update_user(github_user, db)

        token_manager = TokenManager()
        access_token = token_manager.generate_access_token(str(user.id), user.role)
        refresh_token = token_manager.generate_refresh_token(str(user.id))

        access_payload = jwt.decode(
            access_token,
            token_manager.secret_key,
            algorithms=[token_manager.algorithm],
        )
        access_token_jti = access_payload.get("jti")

        await TokenManager.create_session(
            str(user.id),
            refresh_token,
            access_token_jti,
            "web",
            db,
        )

        return {
            "status": "success",
            "user": user.to_dict(),
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": token_manager.access_token_expiry,
            },
            "is_new_user": is_new,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def refresh_tokens(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Refresh access token using refresh token
    
    POST only - Invalidates old refresh token and issues new pair
    
    Request body: {"refresh_token": "..."}
    """
    try:
        # Enforce POST method
        if request.method != "POST":
            raise HTTPException(
                status_code=405,
                detail="Method Not Allowed - use POST",
            )
        
        # Parse request body
        try:
            body = await request.json()
        except:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON in request body",
            )
        
        refresh_token = body.get("refresh_token")
        
        if not refresh_token:
            raise HTTPException(
                status_code=400,
                detail="refresh_token is required",
            )
        
        token_manager = TokenManager()
        
        # Validate refresh token
        try:
            payload = token_manager.validate_refresh_token(refresh_token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401,
                detail="Refresh token expired",
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )
        
        # Check if session still valid (not revoked)
        if not TokenManager.verify_session_valid(refresh_token, db):
            raise HTTPException(
                status_code=401,
                detail="Session has been revoked",
            )
        
        # Get user
        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive",
            )
        
        # Revoke old refresh token
        TokenManager.revoke_refresh_token(refresh_token, db)
        
        # Generate new tokens
        new_access_token = token_manager.generate_access_token(str(user.id), user.role)
        new_refresh_token = token_manager.generate_refresh_token(str(user.id))
        
        # Get JTI from new access token
        access_payload = jwt.decode(
            new_access_token,
            token_manager.secret_key,
            algorithms=[token_manager.algorithm],
        )
        new_access_token_jti = access_payload.get("jti")
        
        # Create new session
        await TokenManager.create_session(
            str(user.id),
            new_refresh_token,
            new_access_token_jti,
            "web",
            db,
        )
        
        return {
            "status": "success",
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": token_manager.access_token_expiry,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout")
async def logout(
    current_user: User = Depends(CurrentUser.get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Logout user by revoking refresh token
    """
    try:
        # Get refresh token from cookies (for web) or would be passed from CLI
        refresh_token = request.cookies.get("refresh_token") if request else None
        
        if refresh_token:
            TokenManager.revoke_refresh_token(refresh_token, db)
        
        return {
            "status": "success",
            "message": "Logged out successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whoami")
async def whoami(current_user: User = Depends(CurrentUser.get_current_user)):
    """
    Get current user information
    """
    return {
        "status": "success",
        "user": current_user.to_dict(),
    }
