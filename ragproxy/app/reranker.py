# include/reranker.py

import logging
from typing import List, Dict

from .http_client import HTTPClient

logger = logging.getLogger(__name__)


class RerankerService:
    def __init__(self, http_client: HTTPClient, model: str):
        self.http = http_client
        self.model = model

    def rerank(self, query: str, passages: List[Dict]) -> List[Dict]:
        if not passages:
            return []

        payload = {
            "model": self.model,
            "input": [{"query": query, "text": p["text"]} for p in passages],
        }

        res = self.http.post("/v1/rerank", payload)
        scores = res.get("results", [])

        if len(scores) != len(passages):
            logger.warning(f"Reranker returned mismatched results: {len(scores)} scores for {len(passages)} passages")
            return passages  # fallback : garder l'ordre d'entrée

        ranked = sorted(
            [
                {
                    "text": p["text"],
                    "metadata": p["metadata"],
                    "score": float(scores[i].get("score", 0.0)),
                }
                for i, p in enumerate(passages)
            ],
            key=lambda x: x["score"],
            reverse=True,
        )

        return ranked
