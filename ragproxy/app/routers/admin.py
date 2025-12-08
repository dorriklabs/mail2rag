"""
Admin endpoints: ingestion, document deletion, collections.
"""

import logging
from typing import Optional

from fastapi import APIRouter

from app.config import VECTOR_DB_HOST, VECTOR_DB_PORT
from app.models import IngestRequest, IngestResponse
from app.pipeline import RAGPipeline
from app.chunker import TextChunker
from app.vectordb import QdrantProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Pipeline instance (will be set by main.py)
pipeline: RAGPipeline = None


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
        
        # 4. Rebuild BM25 (auto)
        if pipeline.multi_collection_mode and pipeline.bm25_multi:
            try:
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
                    key=key,
                    value=doc_id,
                    collection_name=target_collection,
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
        
        # 2. Delete BM25 index if exists
        if pipeline.multi_collection_mode and pipeline.bm25_multi:
            try:
                if pipeline.bm25_multi.is_ready(name):
                    pipeline.bm25_multi.delete_index(name)
                    result["bm25_deleted"] = True
                    logger.info(f"Deleted BM25 index for '{name}'")
            except Exception as e:
                logger.warning(f"Failed to delete BM25 for '{name}': {e}")
                result["bm25_error"] = str(e)
        
        result["message"] = f"Collection '{name}' deleted"
        return result
        
    except Exception as e:
        logger.error(f"Delete collection failed for '{name}': {e}", exc_info=True)
        return {
            "status": "error",
            "collection": name,
            "message": str(e)
        }
