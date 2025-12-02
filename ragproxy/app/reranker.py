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
            "input": [{"query": query, "text": p.get("text", "")} for p in passages],
        }

        res = self.http.post("/v1/rerank", payload)
        scores = res.get("results", [])

        if len(scores) != len(passages):
            logger.warning(
                "Reranker returned mismatched results: %d scores for %d passages",
                len(scores),
                len(passages),
            )
            # Fallback : garder l'ordre d'entrée et les scores existants
            return passages

        enriched: List[Dict] = []
        for passage, score_obj in zip(passages, scores):
            score_val = float(score_obj.get("score", 0.0))

            # Copier le passage pour ne pas modifier l'objet original in-place
            new_p = dict(passage)
            meta = dict(new_p.get("metadata") or {})
            # Stocker le score de rerank dans les métadonnées
            meta["rerank_score"] = score_val
            new_p["metadata"] = meta

            # 'score' reste le score principal exposé à l'extérieur
            # (alias du score de rerank)
            new_p["score"] = score_val

            enriched.append(new_p)

        ranked = sorted(
            enriched,
            key=lambda x: float(x.get("score", 0.0)),
            reverse=True,
        )

        return ranked
