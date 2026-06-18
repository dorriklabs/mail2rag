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

    def _extract_metadata_filters(self, query: str) -> dict:
        import json
        from app.config import LLM_CHAT_MODEL
        prompt = "Tu es un extracteur de métadonnées pour un moteur de recherche. Si la question de l'utilisateur mentionne explicitement une année (ex: 2023, 2024), extrais-la. Sinon, renvoie null. Renvoie UNIQUEMENT un JSON valide de cette forme stricte : {\"year\": \"2023\"} ou {\"year\": null}."
        payload = {"model": LLM_CHAT_MODEL, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": query}], "temperature": 0.0, "max_tokens": 50}
        try:
            resp = self.embedder.http.post("/v1/chat/completions", payload)
            c = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if c.startswith("```json"): c = c.replace("```json", "", 1)
            if c.startswith("```"): c = c.replace("```", "", 1)
            if c.endswith("```"): c = c[:c.rfind("```")]
            c = c.strip()
            d = json.loads(c)
            y = d.get("year") or d.get("annee")
            if y: return {"year": str(y)}
        except Exception as e:
            logger.error(f"Soft Filter extraction error: {e} | response: {c if 'c' in locals() else 'None'}")
            pass
        return {}

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

        # 0. Soft Filtering
        filters = self._extract_metadata_filters(query)
        if filters:
            logger.info(f"Filtres dynamiques extraits : {filters}")
            debug_info["extracted_filters"] = filters

        # 1. Embeddings (Dense)
        t0 = time.time()
        query_vector = self.embedder.embed(query)
        debug_info["timings"]["embedding"] = round(time.time() - t0, 3)

        # 2. Recherche Hybride (Qdrant) Multi-Collection
        t0 = time.time()
        merged_candidates = []
        
        if workspace and "," in workspace:
            collections = [w.strip() for w in workspace.split(",") if w.strip()]
        else:
            collections = [workspace] if workspace else []
            
        final_collections = []
        for coll in collections:
            if coll == "*":
                try:
                    all_colls = self.vdb.list_collections()
                    final_collections.extend(all_colls)
                except Exception as e:
                    logger.error(f"Failed to list collections for wildcard search: {e}")
            else:
                final_collections.append(coll)
                
        # Remove duplicates
        final_collections = list(dict.fromkeys(final_collections))
        
        # -----------------------------------------------------------------
        # Optimisation : Limite dynamique & Multi-Threading
        # -----------------------------------------------------------------
        import concurrent.futures
        
        # Limite de sécurité absolue pour le Reranker (ex: 150 docs max)
        MAX_TOTAL_DOCS = 150
        num_colls = len(final_collections)
        
        if num_colls > 0:
            # Si beaucoup de collections, on réduit le top_k par collection
            dynamic_top_k = max(3, min(top_k, MAX_TOTAL_DOCS // num_colls))
        else:
            dynamic_top_k = top_k
            
        merged_candidates = []
        
        # Parallélisation des appels Qdrant (Max 20 threads)
        max_threads = max(1, min(20, num_colls))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_coll = {
                executor.submit(
                    self.vdb.search,
                    query_text=query,
                    query_vector=query_vector,
                    limit=dynamic_top_k,
                    collection_name=coll,
                ): coll for coll in final_collections
            }
            
            for future in concurrent.futures.as_completed(future_to_coll):
                coll = future_to_coll[future]
                try:
                    candidates = future.result()
                    for candidate in candidates:
                        candidate["metadata"]["collection"] = coll
                    merged_candidates.extend(candidates)
                except Exception as e:
                    logger.error(f"Concurrent search failed for collection {coll}: {e}")
            
        debug_info["timings"]["hybrid_search"] = round(time.time() - t0, 3)
        debug_info["counts"]["merged_candidates"] = len(merged_candidates)

        # 3. Reranking
        t0 = time.time()
        reranked_results = self.reranker.rerank(
            query=query,
            passages=merged_candidates,
            filters=filters
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
                "bm25": self.vdb.is_ready(), # BM25 is now native in Qdrant
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
