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
    BM25_INDEX_PATH,
    REQUEST_TIMEOUT,
    MAX_RERANK_PASSAGES,
    MULTI_COLLECTION_MODE,
    USE_LOCAL_RERANKER,
    LOCAL_RERANKER_MODEL,
)
from .http_client import HTTPClient
from .embeddings import EmbeddingService
from .vectordb import VectorDBService
from .bm25 import BM25Service, MultiBM25Service
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
        
        # Mode multi-collections ou mono-collection
        self.multi_collection_mode = MULTI_COLLECTION_MODE
        
        if MULTI_COLLECTION_MODE:
            logger.info("Initializing RAG Pipeline in MULTI-COLLECTION mode")
            self.bm25_multi = MultiBM25Service()
            self.bm25 = None  # Legacy, non utilisé en mode multi
        else:
            logger.info("Initializing RAG Pipeline in SINGLE-COLLECTION mode")
            self.bm25 = BM25Service(BM25_INDEX_PATH)
            self.bm25_multi = None

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

        # 1. Embeddings
        t0 = time.time()
        query_vector = self.embedder.embed(query)
        debug_info["timings"]["embedding"] = round(time.time() - t0, 3)

        # 2. Recherche Vectorielle (Qdrant)
        t0 = time.time()
        vector_results = self.vdb.search(
            query_vector=query_vector,
            limit=top_k,
            collection_name=workspace,  # None = default collection
        )
        debug_info["timings"]["vector_search"] = round(time.time() - t0, 3)
        debug_info["counts"]["vector_found"] = len(vector_results)

        # 3. Recherche Lexicale (BM25) - Optionnel
        bm25_results = []
        if use_bm25:
            t0 = time.time()
            if self.multi_collection_mode:
                # Mode multi-collection
                target_collection = workspace or self.vdb.collection_name
                if self.bm25_multi and self.bm25_multi.is_ready(target_collection):
                    bm25_results = self.bm25_multi.search(
                        query=query,
                        collection=target_collection,
                        top_k=top_k
                    )
                else:
                    logger.warning(f"BM25 not ready for collection '{target_collection}'")
            else:
                # Mode mono-collection
                if self.bm25.is_ready():
                    bm25_results = self.bm25.search(query, top_k=top_k)
            
            debug_info["timings"]["bm25_search"] = round(time.time() - t0, 3)
            debug_info["counts"]["bm25_found"] = len(bm25_results)

        # 4. Fusion (Reciprocal Rank Fusion)
        merged_candidates = self._fusion(vector_results, bm25_results)
        debug_info["counts"]["merged_candidates"] = len(merged_candidates)

        # 5. Reranking
        t0 = time.time()
        reranked_results = self.reranker.rerank(
            query=query,
            passages=merged_candidates,
        )
        debug_info["timings"]["reranking"] = round(time.time() - t0, 3)
        
        # 6. Limiter à final_k résultats
        final_results = reranked_results[:final_k]
        debug_info["counts"]["reranked_total"] = len(reranked_results)
        debug_info["counts"]["final_results"] = len(final_results)

        total_time = round(time.time() - start_time, 3)
        logger.info(f"RAG finished in {total_time}s (n={len(merged_candidates)}, reranked={len(reranked_results)}, returned={len(final_results)})")
        
        debug_info["total_time"] = total_time

        return final_results, debug_info

    def _fusion(self, vector_results: List[Dict], bm25_results: List[Dict]) -> List[Dict]:
        """Fusionne les résultats vectoriels et BM25 (déduplication simple)."""
        passages = vector_results + bm25_results
        unique: Dict[str, Dict] = {}
        for p in passages:
            text = p.get("text", "")
            if not text:
                continue
            prev = unique.get(text)
            # On garde le meilleur score (simplification)
            if prev is None or float(p.get("score", 0.0)) > float(prev.get("score", 0.0)):
                unique[text] = p
        return list(unique.values())

    def ready_status(self) -> Dict[str, Any]:
        """
        Retourne le statut de préparation du pipeline.
        
        Format de retour:
        {
            "deps": {
                "qdrant": bool,
                "bm25": bool,
                "lm_studio": bool
            },
            "bm25_collections": [...] (optionnel, en mode multi-collection)
        }
        """
        result = {
            "deps": {
                "qdrant": self.vdb.is_ready(),
            }
        }
        
        # BM25 status selon le mode
        if self.multi_collection_mode and self.bm25_multi:
            # En mode multi: montrer les collections avec index
            result["deps"]["bm25"] = self.bm25_multi.is_ready()
            result["bm25_collections"] = self.bm25_multi.list_collections()
        else:
            # Mode mono-collection (legacy)
            result["deps"]["bm25"] = self.bm25.is_ready() if self.bm25 else False
        
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
