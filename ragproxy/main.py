"""
RAG Proxy - FastAPI Application

A hybrid search proxy combining vector similarity (Qdrant) with
BM25 keyword matching and cross-encoder reranking.
"""

import logging

from fastapi import FastAPI

from app.config import LOG_LEVEL, API_KEY_ENABLED
from app.pipeline import RAGPipeline
from app.routers import health, rag, chat, admin

import os
from logging.handlers import RotatingFileHandler

# Configure logging
log_path = os.getenv("LOG_PATH", "/var/log/mail2rag/rag_proxy.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)

file_handler = RotatingFileHandler(
    log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[file_handler, stream_handler],
    force=True
)

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.scheduler_manager import scheduler_manager
    scheduler_manager.start()
    yield
    scheduler_manager.shutdown()

# Create FastAPI app
app = FastAPI(
    title="RAG Proxy",
    description="Hybrid RAG search with Vector + BM25 + Reranking",
    version="1.0.0",
    lifespan=lifespan,
)

# Add authentication middleware if enabled
if API_KEY_ENABLED:
    from app.middleware import APIKeyMiddleware
    app.add_middleware(APIKeyMiddleware)
    logger.info("API key authentication enabled")

# Create pipeline instance
pipeline = RAGPipeline()

# Set pipeline for all routers
health.set_pipeline(pipeline)
rag.set_pipeline(pipeline)
chat.set_pipeline(pipeline)
admin.set_pipeline(pipeline)

# Include routers
app.include_router(health.router)
app.include_router(rag.router)
app.include_router(chat.router)
app.include_router(admin.router)

logger.info("RAG Proxy application started")
