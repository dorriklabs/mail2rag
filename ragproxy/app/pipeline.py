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

    def query_router(self, query: str) -> dict:
        """
        Classifie la requête (Factuelle vs Exploratoire) et extrait les filtres.
        """
        import json
        from app.config import LLM_CHAT_MODEL, RAG_ALLOWED_FILTERS, RAG_QUERY_ROUTER_EXTRA_PROMPT
        
        prompt = f"""Tu es un Query Router pour un moteur RAG d'entreprise.
Analyse la requête de l'utilisateur et détermine :
1. L'intention : "factual" (recherche précise, chiffre, date, référence) ou "exploratory" (explication, procédure, comment faire).
2. Les métadonnées : extrais les années, expéditeurs, {RAG_QUERY_ROUTER_EXTRA_PROMPT}.
3. La confiance ("confidence") : "high" (mention claire/explicite), "probable" (déduite), "ambiguous" (vague ou contradictoire).
4. La requête nettoyée ("clean_query") : Corrige impérativement les fautes d'orthographe (langage SMS, abréviations) et traduis la requête en français si elle est en anglais ou dans une autre langue.

Renvoie UNIQUEMENT un JSON valide de ce format strict :
{{
    "intent": "factual",
    "filters": {{"year": "2023", "doc_type": "procédure", "status": "validé"}},
    "confidence": "high",
    "clean_query": "Requête corrigée et en français"
}}
Si aucun filtre n'est trouvé, mets "filters": {{}}."""
        payload = {"model": LLM_CHAT_MODEL, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": query}], "temperature": 0.0, "max_tokens": 150}
        try:
            resp = self.embedder.http.post("/v1/chat/completions", payload)
            logger.info(f"Raw Query Router Response: {resp}")
            c = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if c.startswith("```json"): c = c.replace("```json", "", 1)
            if c.startswith("```"): c = c.replace("```", "", 1)
            if c.endswith("```"): c = c[:c.rfind("```")]
            d = json.loads(c.strip())
            
            intent = d.get("intent", "exploratory")
            filters = d.get("filters", {})
            confidence = d.get("confidence", "ambiguous")
            clean_query = d.get("clean_query", query)
            
            clean_filters = {}
            y = filters.get("year") or filters.get("annee")
            if y: clean_filters["year"] = str(y)
            
            # Application de la configuration dynamique pour les filtres autorisés
            for key in RAG_ALLOWED_FILTERS:
                if filters.get(key):
                    clean_filters[key] = str(filters.get(key)).lower()
                
            return {"intent": intent, "filters": clean_filters, "confidence": confidence, "clean_query": clean_query}
        except Exception as e:
            logger.error(f"Query Router error: {e}")
            return {"intent": "exploratory", "filters": {}, "confidence": "ambiguous"}

    def run(
        self,
        query: str,
        routing_info: dict,
        top_k: int = 20,
        final_k: int = 5,
        use_bm25: bool = True,
        workspace: str | None = None,
        acl_groups: list[str] | None = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Exécute le pipeline RAG complet.
        Retourne (chunks, debug_info).
        """
        start_time = time.time()
        debug_info = {
            "query": query,
            "timings": {},
            "counts": {},
            "intermediate_results": {}
        }

        # 0. Query Routing info
        intent = routing_info.get("intent", "exploratory")
        filters = routing_info.get("filters", {})
        confidence = routing_info.get("confidence", "ambiguous")
        clean_query = routing_info.get("clean_query", query)
        
        strict_filter = None
        if confidence == "high" and filters:
            strict_filter = filters
            logger.info(f"Application de filtres stricts : {strict_filter}")
            debug_info["strict_filters"] = strict_filter
        elif filters:
            logger.info(f"Boost de métadonnées (confiance {confidence}) : {filters}")
            debug_info["boost_filters"] = filters

        logger.info(f"Using Query: '{clean_query}' (Original: '{query}')")
        debug_info["clean_query"] = clean_query

        # 1. Embeddings (Dense)
        t0 = time.time()
        query_vector = self.embedder.embed(clean_query)
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
                    query_text=clean_query,
                    query_vector=query_vector,
                    limit=dynamic_top_k,
                    collection_name=coll,
                    metadata_filter=strict_filter,
                    acl_groups=acl_groups,
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
            query=clean_query,
            passages=merged_candidates,
            filters=filters
        )
        debug_info["timings"]["reranking"] = round(time.time() - t0, 3)
        
        # Tracking intermédiaire pour benchmark
        debug_info["intermediate_results"]["pre_reranking_uids"] = [c.get("metadata", {}).get("uid") for c in merged_candidates]
        debug_info["intermediate_results"]["post_reranking_uids"] = [c.get("metadata", {}).get("uid") for c in reranked_results]
        
        # 4. Parent-Child Expansion & final_k
        t0 = time.time()
        expanded_results = []
        for chunk in reranked_results[:final_k]:
            meta = chunk.get("metadata", {})
            attachment_id = meta.get("attachment_id")
            uid = meta.get("uid")
            
            # Si le chunk provient d'une pièce jointe, on cherche le corps de l'email (le parent)
            if attachment_id and attachment_id != "body" and uid:
                coll = meta.get("collection", workspace.split(",")[0] if workspace else None)
                if coll:
                    try:
                        parent_docs = self.vdb.search_by_metadata(
                            collection_name=coll,
                            metadata_filter={"uid": uid, "attachment_id": "body"},
                            limit=1
                        )
                        if parent_docs:
                            parent_text = parent_docs[0].get("text", "")
                            # On enrichit le chunk avec le contexte de l'email parent
                            chunk["metadata"]["extended_text"] = f"[Contexte Email Parent]\n{parent_text}\n\n[Extrait Pièce Jointe '{attachment_id}']\n{chunk.get('text', '')}"
                            logger.info(f"Parent-Child Expansion réussie pour l'UID {uid} (enfant: {attachment_id})")
                    except Exception as e:
                        logger.error(f"Erreur lors de l'expansion Parent-Child pour l'UID {uid}: {e}")
            
            expanded_results.append(chunk)
            
        debug_info["timings"]["parent_child_expansion"] = round(time.time() - t0, 3)
        final_results = expanded_results
        
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
