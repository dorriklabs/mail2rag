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

import json
from datetime import datetime

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage()
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
# Apply JSON formatter to all handlers
formatter = JsonFormatter()
for handler in logging.root.handlers:
    handler.setFormatter(formatter)

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
