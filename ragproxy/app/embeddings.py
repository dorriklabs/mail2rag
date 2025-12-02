# include/embeddings.py

import logging
from functools import lru_cache

from fastapi import HTTPException

from .http_client import HTTPClient

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, http_client: HTTPClient, model: str):
        self.http = http_client
        self.model = model

    @lru_cache(maxsize=5000)
    def embed_cached(self, text: str):
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
        return self.embed_cached(text)
