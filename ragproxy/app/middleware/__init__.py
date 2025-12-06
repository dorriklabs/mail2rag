"""
Middleware package for RAG Proxy.
"""

from .auth import APIKeyMiddleware

__all__ = ["APIKeyMiddleware"]
