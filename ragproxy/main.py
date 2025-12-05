# main.py

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import (
    USE_BM25_DEFAULT,
    MAX_QUERY_CHARS,
    MAX_TOP_K,
    BM25_INDEX_PATH,
    LOG_LEVEL,
)
from app.pipeline import RAGPipeline

# Configuration du logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class RequestModel(BaseModel):
    query: str
    top_k: int = 20
    final_k: int = 5
    use_bm25: Optional[bool] = None  # None -> USE_BM25_DEFAULT
    workspace: Optional[str] = None  # Pour le mode multi-collection


class Chunk(BaseModel):
    text: str
    score: float
    metadata: Dict


class ResponseModel(BaseModel):
    query: str
    chunks: List[Chunk]
    debug_info: Optional[Dict] = None


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    ready: bool
    deps: Dict[str, Any]
    bm25_collections: Optional[List[str]] = None


class IngestRequest(BaseModel):
    collection: str
    text: str
    metadata: Dict[str, Any] = {}
    chunk_size: int = 800
    chunk_overlap: int = 100


class IngestResponse(BaseModel):
    status: str
    collection: str
    chunks_created: int = 0
    message: Optional[str] = None


class ChatRequest(BaseModel):
    query: str
    collection: Optional[str] = None
    top_k: int = 20
    final_k: int = 5
    use_bm25: bool = True
    temperature: float = 0.1
    max_tokens: int = 1000


class ChatResponse(BaseModel):
    query: str
    answer: str
    sources: List[Dict[str, Any]] = []
    debug_info: Optional[Dict] = None


app = FastAPI()
pipeline = RAGPipeline()


@app.post("/rag", response_model=ResponseModel)
def rag_endpoint(req: RequestModel):
    # Validation longueur query (max configurable pour éviter DoS)
    if len(req.query) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Query too long (max {MAX_QUERY_CHARS} characters)",
        )

    if not req.query or not req.query.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")

    if req.top_k <= 0 or req.top_k > MAX_TOP_K:
        raise HTTPException(
            status_code=422,
            detail=f"top_k must be in (0, {MAX_TOP_K}]",
        )
    if req.final_k <= 0 or req.final_k > req.top_k:
        raise HTTPException(
            status_code=422,
            detail="final_k must be in (0, top_k]",
        )

    use_bm25 = req.use_bm25
    if use_bm25 is None:
        use_bm25 = USE_BM25_DEFAULT

    results, debug_info = pipeline.run(
        query=req.query,
        top_k=req.top_k,
        final_k=req.final_k,
        use_bm25=use_bm25,
        workspace=req.workspace,
    )

    return ResponseModel(
        query=req.query,
        chunks=[Chunk(**x) for x in results],
        debug_info=debug_info,
    )


@app.get("/healthz", response_model=HealthResponse)
def healthz():
    return HealthResponse(status="ok")


@app.get("/readyz")
def readyz():
    status = pipeline.ready_status()
    deps = status.get("deps", {})
    ready = all(deps.values())
    
    # Construire la réponse avec les métadonnées supplémentaires si disponibles
    response = {
        "ready": ready,
        "deps": deps
    }
    
    # Ajouter les collections BM25 si en mode multi-collection
    if "bm25_collections" in status:
        response["bm25_collections"] = status["bm25_collections"]
    
    return response


@app.get("/test")
def test_endpoint():
    """
    Endpoint de test complet du pipeline RAG.
    Affichage HTML élégant dans le navigateur.
    """

    results = {"timestamp": datetime.now().isoformat(), "tests": {}}

    # Test 1: Embeddings
    try:
        emb = pipeline.embedder.embed("test query")
        results["tests"]["embeddings"] = {
            "status": "ok",
            "dimension": len(emb),
            "error": None,
        }
    except Exception as e:
        results["tests"]["embeddings"] = {
            "status": "error",
            "dimension": 0,
            "error": str(e),
        }

    # Test 2: Qdrant
    try:
        qdrant_ok = pipeline.vdb.is_ready()
        results["tests"]["qdrant"] = {
            "status": "ok" if qdrant_ok else "error",
            "error": None if qdrant_ok else "Not ready",
        }
    except Exception as e:
        results["tests"]["qdrant"] = {
            "status": "error",
            "error": str(e),
        }

    # Test 3: BM25
    try:
        bm25_ready = pipeline.bm25.is_ready()
        results["tests"]["bm25"] = {
            "status": "ok" if bm25_ready else "not_configured",
            "docs_count": len(pipeline.bm25.docs) if bm25_ready else 0,
            "error": None,
        }
    except Exception as e:
        results["tests"]["bm25"] = {
            "status": "error",
            "docs_count": 0,
            "error": str(e),
        }

    # Test 4: Reranker
    try:
        mock_passages = [
            {"text": "Test document 1", "metadata": {"source": "test"}, "score": 0.9},
            {"text": "Test document 2", "metadata": {"source": "test"}, "score": 0.8},
        ]
        ranked = pipeline.reranker.rerank("test query", mock_passages)
        results["tests"]["reranker"] = {
            "status": "ok",
            "ranked_count": len(ranked),
            "error": None,
        }
    except Exception as e:
        results["tests"]["reranker"] = {
            "status": "error",
            "ranked_count": 0,
            "error": str(e),
        }

    # Résumé global
    results["overall"] = (
        "ok"
        if all(
            t.get("status") in ["ok", "not_configured"]
            for t in results["tests"].values()
        )
        else "error"
    )

    # Générer HTML
    html_content = generate_test_html(results)
    return HTMLResponse(content=html_content)


@app.post("/admin/build-bm25")
def build_bm25_index():
    """Reconstruit l'index BM25 depuis Qdrant (admin uniquement)."""
    import pickle
    from pathlib import Path
    from rank_bm25 import BM25Okapi

    try:
        logger.info("Building BM25 index from Qdrant...")

        # Vérifier que Qdrant est accessible
        if not pipeline.vdb.is_ready():
            return {
                "status": "error",
                "message": "Qdrant n'est pas accessible. Vérifiez que le conteneur Qdrant est démarré.",
            }

        # Récupérer tous les documents via l'interface abstraite
        try:
            all_docs = pipeline.vdb.get_all_documents()
        except Exception as e:
            error_msg = str(e)
            if "Not found: Collection" in error_msg or "doesn't exist" in error_msg:
                return {
                    "status": "error",
                    "message": "La collection Qdrant 'documents' n'existe pas encore.\n\n"
                    "📧 Pour créer l'index BM25, vous devez d'abord :\n"
                    "1. Envoyer un email avec pièce jointe à Mail2RAG\n"
                    "2. Attendre que Mail2RAG traite et upload dans Qdrant\n"
                    "3. Revenir ici et cliquer sur 'Construire Index'\n\n"
                    "ℹ️ La collection sera créée automatiquement lors du premier upload.",
                }
            else:
                raise

        docs = []
        meta = []

        for doc_item in all_docs:
            text = doc_item.get("text", "")
            if text:
                docs.append(text)
                meta.append(doc_item.get("metadata", {}))

        if not docs:
            return {
                "status": "error",
                "message": "La collection existe mais ne contient aucun document.\n\n"
                "📧 Pour créer l'index BM25 :\n"
                "1. Envoyez des emails avec pièces jointes à Mail2RAG\n"
                "2. Attendez que les documents soient traités\n"
                "3. Revenez ici et cliquez sur 'Construire Index'\n\n"
                f"📊 Documents actuels : 0",
            }

        # Tokenization
        tokenized = [pipeline.bm25._tokenize(doc) for doc in docs]

        # Créer index BM25
        bm25 = BM25Okapi(tokenized)

        # Sauvegarder
        index_path = Path(BM25_INDEX_PATH)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        with index_path.open("wb") as f:
            pickle.dump((bm25, docs, meta), f)

        # Recharger dans le pipeline
        pipeline.bm25.bm25 = bm25
        pipeline.bm25.docs = docs
        pipeline.bm25.meta = meta

        logger.info(f"BM25 index built successfully: {len(docs)} documents")

        return {
            "status": "ok",
            "docs_count": len(docs),
            "index_size_kb": index_path.stat().st_size / 1024,
            "message": f"✅ Index créé avec succès !\n{len(docs)} documents indexés",
        }

    except Exception as e:
        logger.error(f"Failed to build BM25 index: {e}")
        return {
            "status": "error",
            "message": f"Erreur inattendue lors de la création de l'index:\n{str(e)}",
        }


@app.delete("/admin/delete-bm25")
def delete_bm25_index():
    """Supprime l'index BM25."""
    import os
    from pathlib import Path

    try:
        index_path = Path(BM25_INDEX_PATH)

        if index_path.exists():
            os.remove(index_path)

            # Vider le pipeline
            pipeline.bm25.bm25 = None
            pipeline.bm25.docs = []
            pipeline.bm25.meta = []

            logger.info("BM25 index deleted")
            return {"status": "ok", "message": "Index deleted"}
        else:
            return {"status": "ok", "message": "Index does not exist"}

    except Exception as e:
        logger.error(f"Failed to delete BM25 index: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/admin/auto-rebuild-bm25")
def auto_rebuild_bm25():
    """
    Reconstruction automatique intelligente de l'index BM25.
    Vérifie si Qdrant a plus de documents que BM25, et reconstruit si nécessaire.
    Appelé automatiquement par Mail2RAG après chaque ingestion.
    """
    try:
        logger.info("Auto-rebuild BM25: checking if rebuild needed...")

        # Vérifier que Qdrant est accessible
        if not pipeline.vdb.is_ready():
            logger.warning("Auto-rebuild BM25: Vector DB not ready")
            return {
                "status": "skipped",
                "reason": "Vector DB not ready",
                "rebuilt": False,
            }

        # Compter les documents dans la DB via l'interface abstraite
        try:
            db_count = pipeline.vdb.count_documents()
        except Exception as e:
            logger.warning(f"Auto-rebuild BM25: Failed to count docs: {e}")
            return {
                "status": "error",
                "reason": f"Failed to count docs: {str(e)}",
                "rebuilt": False,
            }

        # Compter les documents dans BM25
        bm25_count = len(pipeline.bm25.docs) if pipeline.bm25.is_ready() else 0

        logger.info(f"Auto-rebuild BM25: DB={db_count}, BM25={bm25_count}")

        # Décider si reconstruction nécessaire
        if db_count == 0:
            logger.info("Auto-rebuild BM25: No documents in DB, skipping")
            return {
                "status": "skipped",
                "reason": "No documents in DB",
                "db_count": 0,
                "bm25_count": bm25_count,
                "rebuilt": False,
            }

        if db_count == bm25_count and pipeline.bm25.is_ready():
            logger.info("Auto-rebuild BM25: Index already up-to-date")
            return {
                "status": "ok",
                "reason": "Index already up-to-date",
                "db_count": db_count,
                "bm25_count": bm25_count,
                "rebuilt": False,
            }

        # Reconstruction nécessaire
        logger.info(
            f"Auto-rebuild BM25: Rebuilding (DB={db_count} > BM25={bm25_count})"
        )
        result = build_bm25_index()

        if result.get("status") == "ok":
            logger.info(
                f"Auto-rebuild BM25: Successfully rebuilt with {result.get('docs_count')} documents"
            )
            return {
                "status": "ok",
                "reason": "Index rebuilt",
                "db_count": db_count,
                "bm25_count": result.get("docs_count"),
                "rebuilt": True,
                "index_size_kb": result.get("index_size_kb"),
            }
        else:
            logger.error(f"Auto-rebuild BM25: Failed - {result.get('message')}")
            return {
                "status": "error",
                "reason": result.get("message"),
                "rebuilt": False,
            }

    except Exception as e:
        logger.error(f"Auto-rebuild BM25: Unexpected error - {e}")
        return {
            "status": "error",
            "reason": str(e),
            "rebuilt": False,
        }


# -------------------------------------------------------------------------------------
# ENDPOINTS MULTI-COLLECTIONS
# -------------------------------------------------------------------------------------

@app.get("/admin/collections")
def list_collections():
    """Liste toutes les collections Qdrant disponibles."""
    try:
        collections = pipeline.vdb.list_collections()
        
        # Pour chaque collection, récupérer les stats
        collections_info = []
        for col_name in collections:
            # Compter les documents
            try:
                # Créer un provider temporaire pour cette collection
                from app.vectordb import QdrantProvider
                from app.config import VECTOR_DB_HOST, VECTOR_DB_PORT
                
                temp_provider = QdrantProvider(VECTOR_DB_HOST, VECTOR_DB_PORT, col_name)
                doc_count = temp_provider.count_documents()
                
                # Vérifier si un index BM25 existe
                bm25_ready = False
                bm25_count = 0
                if pipeline.multi_collection_mode and pipeline.bm25_multi:
                    bm25_ready = pipeline.bm25_multi.is_ready(col_name)
                    if bm25_ready:
                        stats = pipeline.bm25_multi.get_collection_stats(col_name)
                        bm25_count = stats.get("docs_count", 0)
                
                collections_info.append({
                    "name": col_name,
                    "qdrant_count": doc_count,
                    "bm25_ready": bm25_ready,
                    "bm25_count": bm25_count,
                })
            except Exception as e:
                logger.error(f"Error getting stats for collection {col_name}: {e}")
                collections_info.append({
                    "name": col_name,
                    "qdrant_count": 0,
                    "bm25_ready": False,
                    "bm25_count": 0,
                    "error": str(e)
                })
        
        return {
            "status": "ok",
            "multi_collection_mode": pipeline.multi_collection_mode,
            "collections": collections_info
        }
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/admin/build-bm25/{collection}")
def build_bm25_for_collection(collection: str):
    """Construit l'index BM25 pour une collection spécifique."""
    if not pipeline.multi_collection_mode or not pipeline.bm25_multi:
        return {
            "status": "error",
            "message": "Multi-collection mode is not enabled"
        }
    
    try:
        logger.info(f"Building BM25 index for collection '{collection}'...")
        
        # Créer un provider temporaire pour cette collection
        from app.vectordb import QdrantProvider
        from app.config import VECTOR_DB_HOST, VECTOR_DB_PORT
        
        temp_provider = QdrantProvider(VECTOR_DB_HOST, VECTOR_DB_PORT, collection)
        
        # Vérifier que la collection existe
        if not temp_provider.is_ready():
            return {
                "status": "error",
                "message": f"Collection '{collection}' not found in Qdrant"
            }
        
        # Récupérer tous les documents
        try:
            all_docs = temp_provider.get_all_documents()
        except Exception as e:
            error_msg = str(e)
            if "Not found: Collection" in error_msg or "doesn't exist" in error_msg:
                return {
                    "status": "error",
                    "message": f"Collection '{collection}' not found in Qdrant"
                }
            raise
        
        if not all_docs:
            return {
                "status": "error",
                "message": f"Collection '{collection}' exists but contains no documents"
            }
        
        # Extraire textes et métadonnées
        docs = []
        meta = []
        for doc_item in all_docs:
            text = doc_item.get("text", "")
            if text:
                docs.append(text)
                meta.append(doc_item.get("metadata", {}))
        
        if not docs:
            return {
                "status": "error",
                "message": f"No valid documents found in collection '{collection}'"
            }
        
        # Construire l'index
        success = pipeline.bm25_multi.build_index(collection, docs, meta)
        
        if success:
            return {
                "status": "ok",
                "collection": collection,
                "docs_count": len(docs),
                "message": f"✅ Index BM25 created for '{collection}' with {len(docs)} documents"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to build BM25 index"
            }
            
    except Exception as e:
        logger.error(f"Failed to build BM25 index for '{collection}': {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.delete("/admin/delete-bm25/{collection}")
def delete_bm25_for_collection(collection: str):
    """Supprime l'index BM25 pour une collection spécifique."""
    if not pipeline.multi_collection_mode or not pipeline.bm25_multi:
        return {
            "status": "error",
            "message": "Multi-collection mode is not enabled"
        }
    
    try:
        success = pipeline.bm25_multi.delete_index(collection)
        
        if success:
            return {
                "status": "ok",
                "collection": collection,
                "message": f"Index BM25 deleted for '{collection}'"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to delete BM25 index"
            }
    except Exception as e:
        logger.error(f"Failed to delete BM25 index for '{collection}': {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/admin/rebuild-all-bm25")
def rebuild_all_bm25():
    """Reconstruit les index BM25 pour toutes les collections Qdrant."""
    if not pipeline.multi_collection_mode or not pipeline.bm25_multi:
        return {
            "status": "error",
            "message": "Multi-collection mode is not enabled"
        }
    
    try:
        collections = pipeline.vdb.list_collections()
        results = []
        
        for collection in collections:
            logger.info(f"Rebuilding BM25 for collection '{collection}'...")
            result = build_bm25_for_collection(collection)
            results.append({
                "collection": collection,
                "status": result.get("status"),
                "docs_count": result.get("docs_count", 0),
                "message": result.get("message", "")
            })
        
        success_count = sum(1 for r in results if r["status"] == "ok")
        
        return {
            "status": "ok",
            "total_collections": len(collections),
            "success_count": success_count,
            "failed_count": len(collections) - success_count,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Failed to rebuild all BM25 indexes: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# -------------------------------------------------------------------------------------
# ENDPOINTS INGESTION
# -------------------------------------------------------------------------------------

@app.post("/admin/ingest", response_model=IngestResponse)
def ingest_document(req: IngestRequest):
    """
    Ingère un document avec chunking intelligent, génération embeddings, 
    et indexation dans Qdrant + BM25.
    
    Body:
        collection: Nom de la collection (workspace)
        text: Contenu textuel du document
        metadata: Métadonnées (subject, sender, date, filename, etc.)
        chunk_size: Taille des chunks (défaut: 800)
        chunk_overlap: Chevauchement (défaut: 100)
    
    Returns:
        status, collection, chunks_created
    """
    from app.chunker import TextChunker
    
    try:
        logger.info(f"Ingestion request for collection '{req.collection}'")
        
        # Validation
        if not req.text or not req.text.strip():
            return IngestResponse(
                status="error",
                collection=req.collection,
                message="Text content is empty"
            )
        
        # 1. Chunking
        chunker = TextChunker(
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
        
        chunks = chunker.chunk_document(
            text=req.text,
            metadata=req.metadata,
        )
        
        if not chunks:
            return IngestResponse(
                status="error",
                collection=req.collection,
                message="Chunking produced no results"
            )
        
        logger.info(f"Created {len(chunks)} chunks for '{req.collection}'")
        
        # 2. Génération embeddings
        for chunk in chunks:
            embedding = pipeline.embedder.embed(chunk["text"])
            chunk["embedding"] = embedding
        
        logger.info(f"Generated embeddings for {len(chunks)} chunks")
        
        # 3. Indexation Qdrant
        success = pipeline.vdb.upsert_documents(
            chunks=chunks,
            collection_name=req.collection,
        )
        
        if not success:
            return IngestResponse(
                status="error",
                collection=req.collection,
                message="Failed to index in Qdrant"
            )
        
        logger.info(f"Successfully indexed {len(chunks)} chunks in Qdrant")
        
        # 4. Rebuild BM25 (auto)
        if pipeline.multi_collection_mode and pipeline.bm25_multi:
            # Mode multi-collection
            try:
                from app.vectordb import QdrantProvider
                from app.config import VECTOR_DB_HOST, VECTOR_DB_PORT
                
                temp_provider = QdrantProvider(VECTOR_DB_HOST, VECTOR_DB_PORT, req.collection)
                all_docs = temp_provider.get_all_documents()
                
                docs = [d.get("text", "") for d in all_docs if d.get("text")]
                meta = [d.get("metadata", {}) for d in all_docs]
                
                if docs:
                    pipeline.bm25_multi.build_index(req.collection, docs, meta)
                    logger.info(f"BM25 index rebuilt for '{req.collection}'")
            except Exception as e:
                logger.warning(f"Failed to rebuild BM25 for '{req.collection}': {e}")
        
        return IngestResponse(
            status="ok",
            collection=req.collection,
            chunks_created=len(chunks),
            message=f"Successfully ingested {len(chunks)} chunks"
        )
        
    except Exception as e:
        logger.error(f"Ingestion failed for '{req.collection}': {e}", exc_info=True)
        return IngestResponse(
            status="error",
            collection=req.collection,
            message=str(e)
        )


@app.delete("/admin/document/{doc_id}")
def delete_document(doc_id: str, collection: Optional[str] = None):
    """
    Supprime un document (tous ses chunks) par identifiant.
    
    Args:
        doc_id: Identifiant du document (uid, message_id, etc.)
        collection: Collection cible (optionnel si mode single-collection)
    
    Returns:
        status, deleted_count
    """
    try:
        # Déterminer la collection
        target_collection = collection or pipeline.vdb.collection_name
        
        logger.info(f"Delete request for doc_id='{doc_id}' in collection '{target_collection}'")
        
        # Supprimer par métadonnées (on assume que doc_id est dans metadata.uid ou metadata.doc_id)
        # Essayer plusieurs clés possibles
        deleted_count = 0
        for key in ["uid", "doc_id", "message_id"]:
            count = pipeline.vdb.delete_by_metadata(
                collection_name=target_collection,
                metadata_filter={key: doc_id}
            )
            deleted_count += count
            if count > 0:
                break
        
        if deleted_count == 0:
            return {
                "status": "error",
                "message": f"Document '{doc_id}' not found in '{target_collection}'"
            }
        
        logger.info(f"Deleted {deleted_count} chunks for doc_id='{doc_id}'")
        
        # Rebuild BM25 (auto)
        if pipeline.multi_collection_mode and pipeline.bm25_multi:
            try:
                from app.vectordb import QdrantProvider
                from app.config import VECTOR_DB_HOST, VECTOR_DB_PORT
                
                temp_provider = QdrantProvider(VECTOR_DB_HOST, VECTOR_DB_PORT, target_collection)
                all_docs = temp_provider.get_all_documents()
                
                docs = [d.get("text", "") for d in all_docs if d.get("text")]
                meta = [d.get("metadata", {}) for d in all_docs]
                
                if docs:
                    pipeline.bm25_multi.build_index(target_collection, docs, meta)
                else:
                    # Collection vide, supprimer l'index
                    pipeline.bm25_multi.delete_index(target_collection)
                
                logger.info(f"BM25 index updated for '{target_collection}'")
            except Exception as e:
                logger.warning(f"Failed to update BM25 after deletion: {e}")
        
        return {
            "status": "ok",
            "collection": target_collection,
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} chunks"
        }
        
    except Exception as e:
        logger.error(f"Deletion failed for doc_id='{doc_id}': {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


# -------------------------------------------------------------------------------------
# ENDPOINT CHAT (Génération réponse via LLM)
# -------------------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Endpoint de chat RAG complet :
    1. Recherche hybride (Vector + BM25)
    2. Construction du contexte
   3. Génération de réponse via LM Studio
    
    Body:
        query: Question de l'utilisateur
        collection: Collection à interroger (optionnel)
        top_k: Nombre de documents à récupérer
        final_k: Nombre de documents après reranking
        use_bm25: Utiliser BM25
        temperature: Température LLM  
        max_tokens: Tokens max de réponse
    
    Returns:
        answer: Réponse générée
        sources: Documents sources utilisés
    """
    from app.config import (
        LLM_STUDIO_URL,
        LLM_CHAT_MODEL,
        LLM_CHAT_TEMPERATURE,
        LLM_CHAT_MAX_TOKENS,
        LLM_CHAT_SYSTEM_PROMPT,
    )
    import requests
    
    try:
        logger.info(f"Chat request: '{req.query[:100]}...'")
        
        # 1. Recherche RAG
        workspace = req.collection if req.collection else pipeline.vdb.collection_name
        
        rag_result = pipeline.search(
            query=req.query,
            top_k=req.top_k,
            final_k=req.final_k,
            use_bm25=req.use_bm25,
            workspace=workspace,
        )
        
        chunks = rag_result.get("chunks", [])
        
        if not chunks:
            return ChatResponse(
                query=req.query,
                answer="Je n'ai trouvé aucune information pertinente pour répondre à votre question.",
                sources=[],
                debug_info={"error": "No chunks found"}
            )
        
        # 2. Construction du contexte
        context_parts = []
        sources = []
        
        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})
            
            # Ajouter au contexte
            context_parts.append(f"[Document {i+1}]")
            context_parts.append(text)
            context_parts.append("")  # Ligne vide
            
            # Ajouter aux sources
            sources.append({
                "text": text[:200] + "..." if len(text) > 200 else text,
                "score": chunk.get("score", 0.0),
                "metadata": metadata,
            })
        
        context = "\n".join(context_parts)
        
        # 3. Construction du prompt
        system_prompt = LLM_CHAT_SYSTEM_PROMPT
        user_prompt = f"""Contexte :
{context}

Question : {req.query}

Réponds à la question en te basant uniquement sur le contexte fourni. Si le contexte ne contient pas assez d'informations, dis-le clairement."""
        
        # 4. Appel à LM Studio
        llm_payload = {
            "model": req.temperature if hasattr(req, 'model') else LLM_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": req.temperature if req.temperature is not None else LLM_CHAT_TEMPERATURE,
            "max_tokens": req.max_tokens if req.max_tokens else LLM_CHAT_MAX_TOKENS,
        }
        
        logger.debug(f"Calling LM Studio at {LLM_STUDIO_URL}/v1/chat/completions")
        
        response = requests.post(
            f"{LLM_STUDIO_URL}/v1/chat/completions",
            json=llm_payload,
            timeout=60,
        )
        
        if response.status_code != 200:
            logger.error(f"LM Studio error: {response.status_code} - {response.text}")
            return ChatResponse(
                query=req.query,
                answer="Erreur lors de la génération de la réponse (LLM indisponible).",
                sources=sources,
                debug_info={"llm_error": response.text}
            )
        
        llm_response = response.json()
        answer = llm_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not answer:
            answer = "Je n'ai pas pu générer de réponse."
        
        logger.info(f"Chat response generated ({len(answer)} chars)")
        
        return ChatResponse(
            query=req.query,
            answer=answer,
            sources=sources,
            debug_info={
                "chunks_retrieved": len(chunks),
                "context_length": len(context),
                "llm_model": LLM_CHAT_MODEL,
            }
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        return ChatResponse(
            query=req.query,
            answer=f"Une erreur s'est produite : {str(e)}",
            sources=[],
            debug_info={"error": str(e)}
        )


def generate_test_html(results: dict) -> str:
    """Génère le HTML pour la page de test."""

    # Préparer les données pour le template
    timestamp = results["timestamp"]
    overall = results["overall"]
    tests = results["tests"]

    # Construire le HTML statique (pas de f-string avec JavaScript)
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG Proxy - Test Status</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 800px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #2d3748;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        .timestamp {
            color: #718096;
            font-size: 0.9em;
            margin-bottom: 30px;
        }
        .overall-status {
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
            font-size: 1.2em;
            font-weight: bold;
        }
        .overall-ok {
            background: #c6f6d5;
            color: #22543d;
            border: 2px solid #48bb78;
        }
        .overall-error {
            background: #fed7d7;
            color: #742a2a;
            border: 2px solid #fc8181;
        }
        .test-card {
            background: #f7fafc;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid #cbd5e0;
            transition: transform 0.2s;
        }
        .test-card:hover {
            transform: translateX(5px);
        }
        .test-card.ok {
            border-left-color: #48bb78;
            background: #f0fff4;
        }
        .test-card.error {
            border-left-color: #f56565;
            background: #fff5f5;
        }
        .test-card.not-configured {
            border-left-color: #ed8936;
            background: #fffaf0;
        }
        .test-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .test-name {
            font-size: 1.3em;
            font-weight: 600;
            color: #2d3748;
        }
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-ok {
            background: #48bb78;
            color: white;
        }
        .status-error {
            background: #f56565;
            color: white;
        }
        .status-not-configured {
            background: #ed8936;
            color: white;
        }
        .test-details {
            color: #4a5568;
            margin-top: 8px;
            font-size: 0.95em;
        }
        .error-message {
            background: #fff5f5;
            border: 1px solid #fc8181;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
            color: #742a2a;
            font-family: monospace;
            font-size: 0.9em;
        }
        .icon {
            font-size: 1.5em;
            margin-right: 10px;
        }
        .btn {
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9em;
            transition: background 0.3s;
            margin-right: 10px;
        }
        .btn-success {
            background: #48bb78;
        }
        .btn-success:hover {
            background: #38a169;
        }
        .btn-danger {
            background: #f56565;
        }
        .btn-danger:hover {
            background: #e53e3e;
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 1em;
            cursor: pointer;
            margin-top: 20px;
            transition: background 0.3s;
        }
        .refresh-btn:hover {
            background: #5a67d8;
        }
        .bm25-actions {
            margin-top: 15px;
            display: flex;
            gap: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 RAG Proxy Test</h1>
        <div class="timestamp">⏰ """ + timestamp + """</div>
        
        <div class="overall-status overall-""" + overall + """">
            """ + (
        "✅ Tous les systèmes opérationnels"
        if overall == "ok"
        else "❌ Certains systèmes ont des erreurs"
    ) + """
        </div>
        
        <!-- Test Embeddings -->
        <div class="test-card """ + tests["embeddings"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">🧠</span>Embeddings (LM Studio)
                </div>
                <span class="status-badge status-""" + tests["embeddings"][
        "status"
    ] + """">
                    """ + tests["embeddings"]["status"] + """
                </span>
            </div>
            <div class="test-details">
                """ + (
        f"Dimension: {tests['embeddings']['dimension']}"
        if tests["embeddings"]["status"] == "ok"
        else ""
    ) + """
            </div>
            """ + (
        f'<div class="error-message">{tests["embeddings"]["error"]}</div>'
        if tests["embeddings"]["error"]
        else ""
    ) + """
        </div>
        
        <!-- Test Qdrant -->
        <div class="test-card """ + tests["qdrant"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">🗄️</span>Qdrant Vector DB
                </div>
                <span class="status-badge status-""" + tests["qdrant"][
        "status"
    ] + """">
                    """ + tests["qdrant"]["status"] + """
                </span>
            </div>
            """ + (
        f'<div class="error-message">{tests["qdrant"]["error"]}</div>'
        if tests["qdrant"].get("error")
        else ""
    ) + """
        </div>
        
        <!-- Test BM25 -->
        <div class="test-card """ + tests["bm25"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">📊</span>BM25 Index
                </div>
                <span class="status-badge status-""" + tests["bm25"][
        "status"
    ].replace(
        "_", "-"
    ) + """">
                    """ + tests["bm25"]["status"] + """
                </span>
            </div>
            <div class="test-details">
                """ + (
        f"Documents indexés: {tests['bm25']['docs_count']}"
        if tests["bm25"]["status"] != "error"
        else ""
    ) + """
                """ + (
        " (optionnel)"
        if tests["bm25"]["status"] == "not_configured"
        else ""
    ) + """
            </div>
            """ + (
        f'<div class="error-message">{tests["bm25"]["error"]}</div>'
        if tests["bm25"].get("error")
        else ""
    ) + """
            
            <div class="bm25-actions">
                <button onclick="buildBM25()" class="btn btn-success">
                    🔨 Construire Index
                </button>
                <button onclick="deleteBM25()" class="btn btn-danger" """ + (
        "disabled" if tests["bm25"]["status"] != "ok" else ""
    ) + """>
                    🗑️ Supprimer Index
                </button>
            </div>
        </div>
        
        <!-- Test Reranker -->
        <div class="test-card """ + tests["reranker"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">🎯</span>Reranker (LM Studio)
                </div>
                <span class="status-badge status-""" + tests["reranker"][
        "status"
    ] + """">
                    """ + tests["reranker"]["status"] + """
                </span>
            </div>
            <div class="test-details">
                """ + (
        f"Test réussi avec {tests['reranker']['ranked_count']} documents mockés"
        if tests["reranker"]["status"] == "ok"
        else ""
    ) + """
            </div>
            """ + (
        f'<div class="error-message">{tests["reranker"]["error"]}</div>'
        if tests["reranker"].get("error")
        else ""
    ) + """
        </div>
        
        <button class="refresh-btn" onclick="location.reload()">🔄 Rafraîchir</button>
    </div>
    
    <script>
        async function buildBM25() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Construction...';
            
            try {
                const response = await fetch('/admin/build-bm25', { method: 'POST' });
                const data = await response.json();
                
                if (data.status === 'ok') {
                    alert('✅ Index BM25 créé !\\n' + data.docs_count + ' documents indexés\\nTaille: ' + data.index_size_kb.toFixed(2) + ' KB');
                    location.reload();
                } else {
                    alert('❌ Erreur: ' + data.message);
                }
            } catch (e) {
                alert('❌ Erreur: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '🔨 Construire Index';
            }
        }
        
        async function deleteBM25() {
            if (!confirm('Êtes-vous sûr de vouloir supprimer l\\'index BM25 ?')) return;
            
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Suppression...';
            
            try {
                const response = await fetch('/admin/delete-bm25', { method: 'DELETE' });
                const data = await response.json();
                
                if (data.status === 'ok') {
                    alert('✅ Index BM25 supprimé');
                    location.reload();
                } else {
                    alert('❌ Erreur: ' + data.message);
                }
            } catch (e) {
                alert('❌ Erreur: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '🗑️ Supprimer Index';
            }
        }
    </script>
</body>
</html>"""

    return html
