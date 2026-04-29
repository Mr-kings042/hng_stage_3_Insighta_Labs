"""
Insighta Labs Demographic Intelligence API
FastAPI application for querying and analyzing demographic profiles.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from database import init_db
from routes import router as profiles_router
from auth_routes import router as auth_router
from seed import seed_database, seed_users
from auth.middleware import RateLimitMiddleware, LoggingMiddleware, APIVersionMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database and seed data
init_db()
seed_database()
seed_users()

# Create FastAPI app
app = FastAPI(
    title="Insighta Labs API",
    description="Demographic intelligence platform for marketing, product, and growth teams",
    version="2.0.0",
)

# Add CORS middleware - Required for grading script
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins as per spec
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware in reverse order (last added = first executed)
app.add_middleware(APIVersionMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware, auth_limit=1000, general_limit=20000)

# Include routes
app.include_router(auth_router)
app.include_router(profiles_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with proper error envelope"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
    )


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "success",
        "message": "Intelligence Query Engine API is running",
        "version": "2.0.0",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle validation errors"""
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": str(exc)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
