"""
RAG search endpoint.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.config import USE_BM25_DEFAULT, MAX_QUERY_CHARS, MAX_TOP_K
from app.models import RequestModel, ResponseModel, Chunk
from app.pipeline import RAGPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["RAG"])

# Pipeline instance (will be set by main.py)
pipeline: RAGPipeline = None


def set_pipeline(p: RAGPipeline):
    """Set the pipeline instance for this router."""
    global pipeline
    pipeline = p


@router.post("/rag", response_model=ResponseModel)
def rag_endpoint(req: RequestModel):
    """
    Hybrid RAG search endpoint.
    
    Performs vector similarity + optional BM25 search,
    then reranks and returns top results.
    """
    # Validation
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
