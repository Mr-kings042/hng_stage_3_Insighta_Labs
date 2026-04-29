"""Authentication endpoints"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
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
    
    For web clients: Redirects to GitHub authorization endpoint (HTTP 302)
    For CLI clients: Returns JSON with authorization URL and PKCE data
    """
    try:
        oauth_handler = GitHubOAuthHandler()
        
        # Generate PKCE pair
        code_verifier, code_challenge = oauth_handler.generate_pkce_pair()
        
        # Generate state for CSRF protection
        state = oauth_handler.generate_state()
        
        # Get authorization URL
        auth_url = oauth_handler.get_authorization_url(state, code_challenge)
        
        # For web clients, perform HTTP redirect to GitHub
        if client_type.lower() == "web":
            response = RedirectResponse(url=auth_url, status_code=302)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        
        # For CLI clients, return JSON
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
    code: Optional[str] = Query(None, description="Authorization code"),
    state: Optional[str] = Query(None, description="State parameter"),
    error: Optional[str] = Query(None, description="Error from GitHub"),
    error_description: Optional[str] = Query(None, description="Error description"),
    code_verifier: Optional[str] = Query(None, description="PKCE code verifier"),
    role: Optional[str] = Query(None, description="Role for test_code: admin or analyst"),
    db: Session = Depends(get_db),
):
    """
    Handle GitHub OAuth callback with proper error validation.
    
    Supports:
    - Real GitHub OAuth codes
    - test_code for automated testing
    
    Rejects requests with missing code, state, or invalid code_verifier.
    """
    try:
        # Check for OAuth errors from GitHub
        if error:
            error_msg = error_description or error
            raise HTTPException(status_code=400, detail=f"OAuth error: {error_msg}")
        
        # MUST have code parameter - reject if missing
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")
        
        # MUST have state parameter - reject if missing
        if not state:
            raise HTTPException(status_code=400, detail="Missing state parameter")
        
        # TESTING SUPPORT: Handle test_code for automated testing
        if code == "test_code":
            # For testing, create or get test user with specified role
            test_role = role if role in ["admin", "analyst"] else "analyst"
            test_github_id = f"test_{test_role}_{state}_{code}"
            
            # Try to find existing test user
            existing_user = db.query(User).filter(User.github_id == test_github_id).first()
            
            if existing_user:
                user = existing_user
                is_new = False
            else:
                # Create new test user
                user = User(
                    github_id=test_github_id,
                    username=f"test_{test_role}",
                    email=f"{test_role}_test@local",
                    role=test_role,
                    is_active=True,
                    last_login_at=datetime.now(),
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                is_new = True
        else:
            # For real GitHub codes, code_verifier is required
            if not code_verifier:
                raise HTTPException(status_code=400, detail="Missing code_verifier")
            
            # Attempt GitHub token exchange
            oauth_handler = GitHubOAuthHandler()
            try:
                github_token_response = await oauth_handler.exchange_code_for_token(code, code_verifier)
            except Exception:
                # Invalid code or code_verifier
                raise HTTPException(status_code=400, detail="Invalid authorization code or code_verifier")
            
            github_access_token = github_token_response.get("access_token")
            if not github_access_token:
                raise HTTPException(status_code=400, detail="Failed to get GitHub access token")
            
            # Get user info from GitHub
            try:
                github_user = await oauth_handler.get_user_info(github_access_token)
            except Exception:
                raise HTTPException(status_code=400, detail="Failed to retrieve user info from GitHub")
            
            # Create or update user
            user, is_new = await oauth_handler.create_or_update_user(github_user, db)
        
        # Generate tokens for user
        token_manager = TokenManager()
        access_token = token_manager.generate_access_token(str(user.id), user.role)
        refresh_token = token_manager.generate_refresh_token(str(user.id))
        
        # Extract JTI from access token
        access_payload = jwt.decode(
            access_token,
            token_manager.secret_key,
            algorithms=[token_manager.algorithm],
        )
        access_token_jti = access_payload.get("jti")
        
        # Create session record
        await TokenManager.create_session(
            str(user.id),
            refresh_token,
            access_token_jti,
            "web",
            db,
        )
        
        # Return tokens
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
    Complete GitHub OAuth exchange via POST.
    
    Request body: {"code": "...", "state": "...", "code_verifier": "...", "role": "admin|analyst"}
    """
    try:
        code = request_body.get("code")
        state = request_body.get("state")
        code_verifier = request_body.get("code_verifier")
        role = request_body.get("role")

        if not code or not state:
            raise HTTPException(status_code=400, detail="code and state are required")

        if not code_verifier:
            raise HTTPException(status_code=400, detail="code_verifier is required")
        
        # Delegate to callback handler
        return await github_oauth_callback(
            code=code,
            state=state,
            code_verifier=code_verifier,
            role=role,
            db=db,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def refresh_tokens(
    refresh_token: Optional[str] = Query(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Refresh access token using refresh token (POST only)
    
    Accepts refresh_token via:
    - Query parameter: ?refresh_token=...
    - Request body JSON: {"refresh_token": "..."}
    """
    try:
        # Try to get token from query first
        token = refresh_token
        
        # If not in query, try body
        if not token and request:
            try:
                body = await request.json()
                token = body.get("refresh_token")
            except:
                pass
        
        if not token:
            raise HTTPException(status_code=400, detail="refresh_token is required")
        
        token_manager = TokenManager()
        
        # Validate refresh token
        try:
            payload = token_manager.validate_refresh_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Refresh token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Verify session is still valid
        if not TokenManager.verify_session_valid(token, db):
            raise HTTPException(status_code=401, detail="Session has been revoked")
        
        # Get user
        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")
        
        # Revoke old refresh token
        TokenManager.revoke_refresh_token(token, db)
        
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
    """Logout user by revoking refresh token"""
    try:
        # Get refresh token from cookies if available
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
    """Get current user information"""
    return {
        "status": "success",
        "user": current_user.to_dict(),
    }
