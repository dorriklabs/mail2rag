"""
Admin endpoints: ingestion, document deletion, collections.
"""

import logging
from typing import Optional

from fastapi import APIRouter

from app.config import VECTOR_DB_HOST, VECTOR_DB_PORT
from app.models import IngestRequest, IngestResponse, CronConfigRequest, CronConfigResponse
from app.pipeline import RAGPipeline
from app.chunker import TextChunker
from app.vectordb import QdrantProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Pipeline instance (will be set by main.py)
pipeline: RAGPipeline = None # type: ignore


def set_pipeline(p: RAGPipeline):
    """Set the pipeline instance for this router."""
    global pipeline
    pipeline = p


@router.post("/ingest", response_model=IngestResponse)
def ingest_document(req: IngestRequest):
    """
    Ingest a document with chunking, embedding generation, and indexing.
    
    Args:
        collection: Collection name (workspace)
        text: Document text content
        metadata: Metadata dict
        chunk_size: Chunk size (default: 800)
        chunk_overlap: Overlap (default: 100)
    """
    try:
        logger.info(f"Ingestion request for collection '{req.collection}'")
        
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
        
        # 2. Generate embeddings
        for chunk in chunks:
            embedding = pipeline.embedder.embed(chunk["text"])
            chunk["embedding"] = embedding
        
        logger.info(f"Generated embeddings for {len(chunks)} chunks")
        
        # 3. Index in Qdrant
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
        
        # BM25 is now native in Qdrant via Sparse Vectors. No manual rebuild needed.
        logger.info(f"Native hybrid index automatically updated for '{req.collection}'")
        
        # Invalidate the semantic cache when new documents are added
        try:
            pipeline.vdb.clear_semantic_cache()
            logger.info("Semantic cache invalidated due to new ingestion")
        except Exception as e:
            logger.warning(f"Failed to invalidate semantic cache: {e}")
        
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


@router.delete("/document/{doc_id}")
def delete_document(doc_id: str, collection: Optional[str] = None):
    """
    Delete a document (all its chunks) by identifier.
    
    Args:
        doc_id: Document identifier (uid, message_id, etc.)
        collection: Target collection (optional)
    """
    try:
        target_collection = collection or pipeline.vdb.collection_name
        
        logger.info(f"Delete request for doc_id='{doc_id}' in collection '{target_collection}'")
        
        deleted_count = 0
        for key in ["uid", "doc_id", "message_id"]:
            try:
                count = pipeline.vdb.delete_by_metadata(
                    collection_name=target_collection,
                    metadata_filter={key: doc_id},
                )
                deleted_count += count
                if count > 0:
                    logger.info(f"Deleted {count} chunks by {key}='{doc_id}'")
                    break
            except Exception as e:
                logger.debug(f"Delete by {key} failed: {e}")
                continue
        
        if deleted_count == 0:
            return {
                "status": "ok",
                "deleted_count": 0,
                "message": f"No documents found with id '{doc_id}'"
            }
        
        try:
            pipeline.vdb.clear_semantic_cache()
        except Exception as e:
            logger.warning(f"Failed to invalidate semantic cache: {e}")
            
        return {
            "status": "ok",
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} chunks"
        }
        
    except Exception as e:
        logger.error(f"Delete failed for '{doc_id}': {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/collections")
def list_collections():
    """List all Qdrant collections with stats."""
    try:
        collections = pipeline.vdb.list_collections()
        
        collections_info = []
        for col_name in collections:
            try:
                temp_provider = QdrantProvider(VECTOR_DB_HOST, VECTOR_DB_PORT, col_name)
                doc_count = temp_provider.count_documents()
                
                # BM25 native in Qdrant
                bm25_ready = True
                bm25_count = doc_count
                
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
            "multi_collection_mode": True,
            "collections": collections_info
        }
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.delete("/collection/{name}")
def delete_collection(name: str):
    """
    Delete an entire collection from Qdrant and BM25.
    
    Args:
        name: Collection name to delete
    
    Returns:
        Status with deletion details
    """
    try:
        logger.info(f"Delete collection request for '{name}'")
        
        result = {
            "status": "ok",
            "collection": name,
            "qdrant_deleted": False,
            "bm25_deleted": False,
        }
        
        # 1. Delete from Qdrant
        try:
            temp_provider = QdrantProvider(VECTOR_DB_HOST, VECTOR_DB_PORT, name)
            if temp_provider.collection_exists():
                temp_provider.delete_collection()
                result["qdrant_deleted"] = True
                logger.info(f"Deleted Qdrant collection '{name}'")
            else:
                logger.warning(f"Qdrant collection '{name}' does not exist")
        except Exception as e:
            logger.error(f"Failed to delete Qdrant collection '{name}': {e}")
            result["qdrant_error"] = str(e)
        
        # BM25 is native in Qdrant, deleted automatically with collection
        result["bm25_deleted"] = True
        
        try:
            pipeline.vdb.clear_semantic_cache()
        except Exception as e:
            logger.warning(f"Failed to invalidate semantic cache: {e}")
            
        result["message"] = f"Collection '{name}' deleted"
        return result
        
    except Exception as e:
        logger.error(f"Delete collection failed for '{name}': {e}", exc_info=True)
        return {
            "status": "error",
            "collection": name,
            "message": str(e)
        }

@router.get("/cron", response_model=CronConfigResponse)
def get_cron_config():
    """Get the current cron configuration."""
    from app.scheduler_manager import scheduler_manager
    config = scheduler_manager.get_config()
    return CronConfigResponse(status="ok", config=config)

@router.post("/cron", response_model=CronConfigResponse)
def update_cron_config(req: CronConfigRequest):
    """Update cron configuration."""
    from app.scheduler_manager import scheduler_manager
    config = scheduler_manager.update_config(req.task_name, req.active, req.hour, req.minute)
    return CronConfigResponse(status="ok", config={req.task_name: config})

@router.post("/cron/{task_name}/run")
async def run_cron_task(task_name: str):
    """Run a specific cron task immediately."""
    from app.scheduler_manager import scheduler_manager
    if task_name == "rgpd_purge":
        import asyncio
        asyncio.create_task(scheduler_manager.run_rgpd_purge())
        return {"status": "ok", "message": "Task 'rgpd_purge' started in background."}
    return {"status": "error", "message": f"Unknown task: {task_name}"}
