"""
BM25 index management endpoints.
"""

import logging
import os
import pickle
from pathlib import Path

from fastapi import APIRouter
from rank_bm25 import BM25Okapi

from app.config import BM25_INDEX_PATH, VECTOR_DB_HOST, VECTOR_DB_PORT
from app.pipeline import RAGPipeline
from app.vectordb import QdrantProvider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["BM25"])

# Pipeline instance (will be set by main.py)
pipeline: RAGPipeline = None


def set_pipeline(p: RAGPipeline):
    """Set the pipeline instance for this router."""
    global pipeline
    pipeline = p


@router.post("/admin/build-bm25")
def build_bm25_index():
    """Build BM25 index from Qdrant (default collection)."""
    try:
        logger.info("Building BM25 index from Qdrant...")

        if not pipeline.vdb.is_ready():
            return {
                "status": "error",
                "message": "Qdrant n'est pas accessible.",
            }

        try:
            all_docs = pipeline.vdb.get_all_documents()
        except Exception as e:
            error_msg = str(e)
            if "Not found: Collection" in error_msg or "doesn't exist" in error_msg:
                return {
                    "status": "error",
                    "message": "La collection Qdrant n'existe pas encore.",
                }
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
                "message": "Aucun document trouvé.",
            }

        # Tokenization
        tokenized = [pipeline.bm25._tokenize(doc) for doc in docs]

        # Create BM25 index
        bm25 = BM25Okapi(tokenized)

        # Save
        index_path = Path(BM25_INDEX_PATH)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        with index_path.open("wb") as f:
            pickle.dump((bm25, docs, meta), f)

        # Reload in pipeline
        pipeline.bm25.bm25 = bm25
        pipeline.bm25.docs = docs
        pipeline.bm25.meta = meta

        logger.info(f"BM25 index built: {len(docs)} documents")

        return {
            "status": "ok",
            "docs_count": len(docs),
            "index_size_kb": index_path.stat().st_size / 1024,
        }

    except Exception as e:
        logger.error(f"Failed to build BM25 index: {e}")
        return {"status": "error", "message": str(e)}


@router.delete("/admin/delete-bm25")
def delete_bm25_index():
    """Delete the BM25 index."""
    try:
        index_path = Path(BM25_INDEX_PATH)

        if index_path.exists():
            os.remove(index_path)
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


@router.post("/admin/auto-rebuild-bm25")
def auto_rebuild_bm25():
    """
    Smart auto-rebuild: only rebuild if Qdrant has more docs than BM25.
    Called automatically after each ingestion.
    """
    try:
        logger.info("Auto-rebuild BM25: checking...")

        if not pipeline.vdb.is_ready():
            return {"status": "skipped", "reason": "Vector DB not ready", "rebuilt": False}

        try:
            db_count = pipeline.vdb.count_documents()
        except Exception as e:
            return {"status": "error", "reason": str(e), "rebuilt": False}

        bm25_count = len(pipeline.bm25.docs) if pipeline.bm25.is_ready() else 0

        logger.info(f"Auto-rebuild BM25: DB={db_count}, BM25={bm25_count}")

        if db_count == 0:
            return {"status": "skipped", "reason": "No documents", "rebuilt": False}

        if db_count == bm25_count and pipeline.bm25.is_ready():
            return {"status": "ok", "reason": "Already up-to-date", "rebuilt": False}

        # Rebuild needed
        result = build_bm25_index()

        if result.get("status") == "ok":
            return {
                "status": "ok",
                "reason": "Index rebuilt",
                "rebuilt": True,
                "docs_count": result.get("docs_count"),
            }
        else:
            return {"status": "error", "reason": result.get("message"), "rebuilt": False}

    except Exception as e:
        logger.error(f"Auto-rebuild BM25 error: {e}")
        return {"status": "error", "reason": str(e), "rebuilt": False}


# Multi-collection endpoints

@router.post("/admin/build-bm25/{collection}")
def build_bm25_for_collection(collection: str):
    """Build BM25 index for a specific collection."""
    if not pipeline.multi_collection_mode or not pipeline.bm25_multi:
        return {"status": "error", "message": "Multi-collection mode not enabled"}

    try:
        logger.info(f"Building BM25 for '{collection}'...")

        temp_provider = QdrantProvider(VECTOR_DB_HOST, VECTOR_DB_PORT, collection)

        if not temp_provider.is_ready():
            return {"status": "error", "message": f"Collection '{collection}' not found"}

        all_docs = temp_provider.get_all_documents()

        if not all_docs:
            return {"status": "error", "message": "Collection is empty"}

        docs = [d.get("text", "") for d in all_docs if d.get("text")]
        meta = [d.get("metadata", {}) for d in all_docs]

        if not docs:
            return {"status": "error", "message": "No valid documents"}

        success = pipeline.bm25_multi.build_index(collection, docs, meta)

        if success:
            return {
                "status": "ok",
                "collection": collection,
                "docs_count": len(docs),
            }
        else:
            return {"status": "error", "message": "Failed to build index"}

    except Exception as e:
        logger.error(f"Failed to build BM25 for '{collection}': {e}")
        return {"status": "error", "message": str(e)}


@router.delete("/admin/delete-bm25/{collection}")
def delete_bm25_for_collection(collection: str):
    """Delete BM25 index for a specific collection."""
    if not pipeline.multi_collection_mode or not pipeline.bm25_multi:
        return {"status": "error", "message": "Multi-collection mode not enabled"}

    try:
        success = pipeline.bm25_multi.delete_index(collection)
        if success:
            return {"status": "ok", "collection": collection}
        else:
            return {"status": "error", "message": "Failed to delete index"}
    except Exception as e:
        logger.error(f"Failed to delete BM25 for '{collection}': {e}")
        return {"status": "error", "message": str(e)}


@router.post("/admin/rebuild-all-bm25")
def rebuild_all_bm25():
    """Rebuild BM25 indexes for all Qdrant collections."""
    if not pipeline.multi_collection_mode or not pipeline.bm25_multi:
        return {"status": "error", "message": "Multi-collection mode not enabled"}

    try:
        collections = pipeline.vdb.list_collections()
        results = []

        for collection in collections:
            result = build_bm25_for_collection(collection)
            results.append({
                "collection": collection,
                "status": result.get("status"),
                "docs_count": result.get("docs_count", 0),
            })

        success_count = sum(1 for r in results if r["status"] == "ok")

        return {
            "status": "ok",
            "total_collections": len(collections),
            "success_count": success_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Failed to rebuild all BM25: {e}")
        return {"status": "error", "message": str(e)}
