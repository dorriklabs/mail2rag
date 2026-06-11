# include/pipeline.py

import logging
import time
from typing import Dict, List, Any

from fastapi import HTTPException

from .config import (
    LM_STUDIO_URL,
    EMBED_MODEL,
    RERANK_MODEL,
    VECTOR_DB_HOST,
    VECTOR_DB_PORT,
    VECTOR_DB_COLLECTION,
    REQUEST_TIMEOUT,
    MAX_RERANK_PASSAGES,
    USE_LOCAL_RERANKER,
    LOCAL_RERANKER_MODEL,
)
from .http_client import HTTPClient
from .embeddings import EmbeddingService
from .vectordb import VectorDBService
from .reranker import RerankerService
from .local_reranker import LocalReranker

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self):
        http_lm = HTTPClient(LM_STUDIO_URL, REQUEST_TIMEOUT)

        self.embedder = EmbeddingService(http_lm, EMBED_MODEL)
        self.vdb = VectorDBService(VECTOR_DB_HOST, VECTOR_DB_PORT, VECTOR_DB_COLLECTION)
        
        # Reranker : local (cross-encoder) ou LM Studio
        if USE_LOCAL_RERANKER:
            logger.info(f"Using LOCAL reranker: {LOCAL_RERANKER_MODEL}")
            self.reranker = LocalReranker(LOCAL_RERANKER_MODEL)
        else:
            logger.info(f"Using LM Studio reranker: {RERANK_MODEL}")
            self.reranker = RerankerService(http_lm, RERANK_MODEL)
        
        logger.info("Initializing RAG Pipeline with Qdrant Native Hybrid Search")

    def run(
        self,
        query: str,
        top_k: int = 20,
        final_k: int = 5,
        use_bm25: bool = True,
        workspace: str | None = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Exécute le pipeline RAG complet.
        Retourne (chunks, debug_info).
        """
        start_time = time.time()
        debug_info = {
            "steps": {},
            "counts": {},
            "timings": {}
        }

        # 1. Embeddings (Dense)
        t0 = time.time()
        query_vector = self.embedder.embed(query)
        debug_info["timings"]["embedding"] = round(time.time() - t0, 3)

        # 2. Recherche Hybride (Qdrant)
        t0 = time.time()
        merged_candidates = self.vdb.search(
            query_text=query,
            query_vector=query_vector,
            limit=top_k,
            collection_name=workspace,  # None = default collection
        )
        debug_info["timings"]["hybrid_search"] = round(time.time() - t0, 3)
        debug_info["counts"]["merged_candidates"] = len(merged_candidates)

        # 3. Reranking
        t0 = time.time()
        reranked_results = self.reranker.rerank(
            query=query,
            passages=merged_candidates,
        )
        debug_info["timings"]["reranking"] = round(time.time() - t0, 3)
        
        # 4. Limiter à final_k résultats
        final_results = reranked_results[:final_k]
        debug_info["counts"]["reranked_total"] = len(reranked_results)
        debug_info["counts"]["final_results"] = len(final_results)

        total_time = round(time.time() - start_time, 3)
        logger.info(f"RAG finished in {total_time}s (n={len(merged_candidates)}, reranked={len(reranked_results)}, returned={len(final_results)})")
        
        debug_info["total_time"] = total_time

        return final_results, debug_info

    def ready_status(self) -> Dict[str, Any]:
        """
        Retourne le statut de préparation du pipeline.
        """
        result = {
            "deps": {
                "qdrant": self.vdb.is_ready(),
            }
        }
        
        # LM Studio check
        try:
            self.embedder.embed("ping")
            result["deps"]["lm_studio"] = True
        except HTTPException:
            result["deps"]["lm_studio"] = False
        
        # Ajouter les infos des modèles pour le diagnostic
        result["models"] = {
            "embed_model": EMBED_MODEL,
            "rerank_model": LOCAL_RERANKER_MODEL if USE_LOCAL_RERANKER else RERANK_MODEL,
            "use_local_reranker": USE_LOCAL_RERANKER,
        }
        
        return result
