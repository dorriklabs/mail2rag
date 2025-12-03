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
)
from .http_client import HTTPClient
from .embeddings import EmbeddingService
from .vectordb import VectorDBService
from .bm25 import BM25Service, MultiBM25Service
from .reranker import RerankerService

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self):
        http_lm = HTTPClient(LM_STUDIO_URL, REQUEST_TIMEOUT)

        self.embedder = EmbeddingService(http_lm, EMBED_MODEL)
        self.vdb = VectorDBService(VECTOR_DB_HOST, VECTOR_DB_PORT, VECTOR_DB_COLLECTION)
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
        workspace: str = None,
    ) -> List[Dict]:
        t0 = time.time()

        # 1) Embedding
        emb = self.embedder.embed(query)

        # 2) Vector search
        vec_hits = self.vdb.search(emb, top_k)
        for p in vec_hits:
            meta = p.get("metadata") or {}
            # Conserver le score de similarité vectorielle dans les métadonnées
            meta["vector_score"] = float(p.get("score", 0.0))
            p["metadata"] = meta

        # 3) BM25 (optionnel)
        bm_hits = []
        if use_bm25:
            if self.multi_collection_mode and self.bm25_multi:
                # Mode multi-collection : utiliser le workspace spécifié
                if workspace and self.bm25_multi.is_ready(workspace):
                    bm_hits = self.bm25_multi.search(query, workspace, top_k)
                else:
                    logger.debug(f"BM25 not ready for workspace '{workspace}'")
            elif self.bm25 and self.bm25.is_ready():
                # Mode mono-collection (legacy)
                bm_hits = self.bm25.search(query, top_k)
        
        for p in bm_hits:
            meta = p.get("metadata") or {}
            # Conserver le score BM25 dans les métadonnées
            meta["bm25_score"] = float(p.get("score", 0.0))
            p["metadata"] = meta

        passages = vec_hits + bm_hits

        # 4) Unicité par texte :
        #    pour chaque texte, on garde le passage avec le meilleur score actuel
        unique: Dict[str, Dict] = {}
        for p in passages:
            text = p.get("text", "")
            if not text:
                continue
            prev = unique.get(text)
            if prev is None or float(p.get("score", 0.0)) > float(prev.get("score", 0.0)):
                unique[text] = p
        passages = list(unique.values())

        if not passages:
            logger.info("No passages found for query='%s...'", query[:50])
            return []

        # 5) Limiter le nombre de passages envoyés au reranker
        #    pour maîtriser la taille du payload vers LM Studio
        if len(passages) > MAX_RERANK_PASSAGES:
            logger.warning(
                "Too many passages (%d), limiting to top %d for reranking",
                len(passages),
                MAX_RERANK_PASSAGES,
            )
            passages_for_rerank = sorted(
                passages,
                key=lambda x: float(x.get("score", 0.0)),
                reverse=True,
            )[:MAX_RERANK_PASSAGES]
        else:
            passages_for_rerank = passages

        # 6) Reranking avec fallback
        try:
            ranked = self.reranker.rerank(query, passages_for_rerank)
        except HTTPException as e:
            if 500 <= e.status_code < 600:
                logger.warning(
                    "Reranker failed, falling back to original passages (status=%s)",
                    e.status_code,
                )
                ranked = passages_for_rerank
            else:
                raise

        # 7) Top final_k
        final = ranked[:final_k]

        logger.info(
            "RAG finished in %ss (n=%d, returned=%d)",
            round(time.time() - t0, 3),
            len(passages),
            len(final),
        )

        return final

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
        
        return result
