"""
Authentication middleware for RAG Proxy.
"""

import logging

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import API_KEY

logger = logging.getLogger(__name__)

# Endpoints that don't require authentication
PUBLIC_ENDPOINTS = {
    "/healthz",
    "/health", 
    "/readyz",
    "/docs",
    "/openapi.json",
}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate X-API-Key header on protected endpoints.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for public endpoints
        if request.url.path in PUBLIC_ENDPOINTS:
            return await call_next(request)
        
        # Check API key
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            logger.warning(f"Missing API key for {request.url.path}")
            raise HTTPException(
                status_code=401,
                detail="Missing X-API-Key header"
            )
        
        if api_key != API_KEY:
            logger.warning(f"Invalid API key for {request.url.path}")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        return await call_next(request)
