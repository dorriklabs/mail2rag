"""
Pydantic models for RAG Proxy API.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# RAG Search
# ---------------------------------------------------------------------------

class RequestModel(BaseModel):
    """Request for RAG search."""
    query: str
    top_k: int = 20
    final_k: int = 5
    use_bm25: Optional[bool] = None
    workspace: Optional[str] = None


class Chunk(BaseModel):
    """A single search result chunk."""
    text: str
    score: float
    metadata: Dict


class ResponseModel(BaseModel):
    """Response from RAG search."""
    query: str
    chunks: List[Chunk]
    debug_info: Optional[Dict] = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Simple health check response."""
    status: str


class ReadyResponse(BaseModel):
    """Readiness check with dependency status."""
    ready: bool
    deps: Dict[str, Any]
    bm25_collections: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    """Request to ingest a document."""
    collection: str
    text: str
    metadata: Dict[str, Any] = {}
    chunk_size: int = 800
    chunk_overlap: int = 100


class IngestResponse(BaseModel):
    """Response from document ingestion."""
    status: str
    collection: str
    chunks_created: int = 0
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Request for RAG chat with LLM response."""
    query: str
    collection: Optional[str] = None
    top_k: int = 20
    final_k: int = 5
    use_bm25: bool = True
    temperature: float = 0.1
    max_tokens: int = 1000


class ChatResponse(BaseModel):
    """Response from RAG chat."""
    query: str
    answer: str
    sources: List[Dict[str, Any]] = []
    debug_info: Optional[Dict] = None
