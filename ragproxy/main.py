"""
RAG Proxy - FastAPI Application

A hybrid search proxy combining vector similarity (Qdrant) with
BM25 keyword matching and cross-encoder reranking.
"""

import logging

from fastapi import FastAPI

from app.config import LOG_LEVEL
from app.pipeline import RAGPipeline
from app.routers import health, rag, chat, admin, bm25

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="RAG Proxy",
    description="Hybrid RAG search with Vector + BM25 + Reranking",
    version="1.0.0",
)

# Create pipeline instance
pipeline = RAGPipeline()

# Set pipeline for all routers
health.set_pipeline(pipeline)
rag.set_pipeline(pipeline)
chat.set_pipeline(pipeline)
admin.set_pipeline(pipeline)
bm25.set_pipeline(pipeline)

# Include routers
app.include_router(health.router)
app.include_router(rag.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(bm25.router)

logger.info("RAG Proxy application started")
