# include/pipeline.py

import logging
import time
from typing import Dict, List

from fastapi import HTTPException

from .config import (
    LM_STUDIO_URL,
    EMBED_MODEL,
    RERANK_MODEL,
    VECTOR_DB_HOST,
    VECTOR_DB_PORT,
    VECTOR_DB_COLLECTION,
    BM25_INDEX_PATH,
    REQUEST_TIMEOUT,
)
from .http_client import HTTPClient
from .embeddings import EmbeddingService
from .vectordb import VectorDBService
from .bm25 import BM25Service
from .reranker import RerankerService

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self):
        http_lm = HTTPClient(LM_STUDIO_URL, REQUEST_TIMEOUT)

        self.embedder = EmbeddingService(http_lm, EMBED_MODEL)
        self.vdb = VectorDBService(VECTOR_DB_HOST, VECTOR_DB_PORT, VECTOR_DB_COLLECTION)
        self.reranker = RerankerService(http_lm, RERANK_MODEL)
        self.bm25 = BM25Service(BM25_INDEX_PATH)

    def run(
        self,
        query: str,
        top_k: int = 20,
        final_k: int = 5,
        use_bm25: bool = True,
    ) -> List[Dict]:
        t0 = time.time()

        # 1) Embedding
        emb = self.embedder.embed(query)

        # 2) Vector search
        vec_hits = self.vdb.search(emb, top_k)

        # 3) BM25 (optionnel)
        if use_bm25 and self.bm25.is_ready():
            bm_hits = self.bm25.search(query, top_k)
        else:
            bm_hits = []

        passages = vec_hits + bm_hits

        # 4) Unicité par texte
        passages = list({p["text"]: p for p in passages}.values())

        if not passages:
            logger.info(f"No passages found for query='{query[:50]}...'")
            return []

        # 5) Reranking avec fallback
        try:
            ranked = self.reranker.rerank(query, passages)
        except HTTPException as e:
            if 500 <= e.status_code < 600:
                logger.warning(
                    f"Reranker failed, falling back to original passages (status={e.status_code})"
                )
                ranked = passages
            else:
                raise

        # 6) Top final_k
        final = ranked[:final_k]

        logger.info(
            f"RAG finished in {round(time.time() - t0, 3)}s "
            f"(n={len(passages)}, returned={len(final)})"
        )

        return final

    def ready_status(self) -> Dict[str, bool]:
        status = {
            "qdrant": self.vdb.is_ready(),
            "bm25": self.bm25.is_ready(),
        }
        try:
            self.embedder.embed("ping")
            status["lm_studio"] = True
        except HTTPException:
            status["lm_studio"] = False
        return status
