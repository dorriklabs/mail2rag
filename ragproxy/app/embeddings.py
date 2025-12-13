# include/embeddings.py
"""
Embedding Service with LiteLLM Gateway support.

Provides backward-compatible interface while supporting:
- LM Studio (default, via HTTP client)
- OpenAI, Anthropic, etc. (via LiteLLM Gateway)
"""

import logging
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException

from .http_client import HTTPClient
from .config import LLM_PROVIDER

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Embedding service with multi-provider support.
    
    Uses LiteLLM Gateway for cloud providers (openai, anthropic),
    falls back to direct HTTP for LM Studio for efficiency.
    """
    
    def __init__(self, http_client: HTTPClient, model: str):
        """
        Initialize embedding service.
        
        Args:
            http_client: HTTP client for LM Studio
            model: Model name for embeddings
        """
        self.http = http_client
        self.model = model
        self.use_gateway = LLM_PROVIDER.lower() not in ("lmstudio", "")
        
        if self.use_gateway:
            from .llm_gateway import get_llm_gateway
            self.gateway = get_llm_gateway()
            logger.info(f"EmbeddingService using LiteLLM Gateway (provider: {LLM_PROVIDER})")
        else:
            self.gateway = None
            logger.info(f"EmbeddingService using direct HTTP (model: {model})")

    @lru_cache(maxsize=5000)
    def embed_cached(self, text: str):
        """
        Generate embedding with caching.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        if self.use_gateway and self.gateway:
            # Use LiteLLM Gateway for cloud providers
            try:
                return self.gateway.embed_single(text)
            except Exception as e:
                logger.error(f"Gateway embedding failed: {e}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Embedding service error: {str(e)}",
                )
        else:
            # Direct HTTP for LM Studio (more efficient)
            payload = {"model": self.model, "input": [text]}
            res = self.http.post("/v1/embeddings", payload)

            try:
                return res["data"][0]["embedding"]
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"Unexpected embeddings payload: {res} ({e})")
                raise HTTPException(
                    status_code=502,
                    detail="Embedding response malformed",
                )

    def embed(self, text: str):
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        return self.embed_cached(text)
