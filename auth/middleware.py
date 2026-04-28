"""Middleware for authentication, authorization, rate limiting, and logging"""

import time
import logging
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import jwt
from auth.tokens import TokenManager
from sqlalchemy.orm import Session
from database import get_db

# Configure logging
logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""

    def __init__(self, app, auth_limit=10, general_limit=60):
        super().__init__(app)
        self.auth_limit = auth_limit  # requests per minute for auth endpoints
        self.general_limit = general_limit  # requests per minute per user for other endpoints
        self.request_counts = defaultdict(list)  # {identifier: [timestamp, timestamp, ...]}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting in test mode
        if os.environ.get("TESTING"):
            response = await call_next(request)
            return response
        
        # Determine rate limit based on endpoint
        is_auth_endpoint = request.url.path.startswith("/auth/")
        limit = self.auth_limit if is_auth_endpoint else self.general_limit

        # Determine identifier (IP for auth, user_id for others)
        if is_auth_endpoint:
            identifier = request.client.host if request.client else "unknown"
        else:
            # Try to get user_id from JWT
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    token = auth_header[7:]
                    token_manager = TokenManager()
                    payload = token_manager.validate_access_token(token)
                    identifier = f"user_{payload.get('user_id')}"
                except:
                    identifier = request.client.host if request.client else "unknown"
            else:
                identifier = request.client.host if request.client else "unknown"

        # Check rate limit
        now = datetime.now(timezone.utc).timestamp()
        minute_ago = now - 60

        # Clean up old requests (older than 1 minute)
        self.request_counts[identifier] = [
            ts for ts in self.request_counts[identifier] if ts > minute_ago
        ]

        # Check if over limit
        if len(self.request_counts[identifier]) >= limit:
            return JSONResponse(
                status_code=429,
                content={"status": "error", "message": "Rate limit exceeded"},
            )

        # Add current request
        self.request_counts[identifier].append(now)

        response = await call_next(request)
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logging middleware for all requests"""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Start time
        start_time = time.time()

        # Get response
        response = await call_next(request)

        # Calculate duration
        process_time = time.time() - start_time

        # Log request
        logger.info(
            f"{request.method} {request.url.path} - Status: {response.status_code} - {process_time:.3f}s"
        )

        # Add timing header
        response.headers["X-Process-Time"] = str(process_time)

        return response


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Validate API version header for /api/* endpoints if provided"""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only check /api/* endpoints (but not /auth/*)
        if request.url.path.startswith("/api/") and not request.url.path.startswith(
            "/api/docs"
        ):
            api_version = request.headers.get("X-API-Version")

            # If version is provided, validate it
            if api_version and api_version != "1":
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": f"Unsupported API version: {api_version}. Supported: 1",
                    },
                )

        response = await call_next(request)
        return response
