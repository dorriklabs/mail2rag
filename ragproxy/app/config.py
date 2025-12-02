# include/config.py

import os
from typing import Optional


def str_to_bool(x: Optional[str], default: bool = False) -> bool:
    if x is None:
        return default
    return x.strip().lower() in {"1", "true", "yes", "y", "on"}


LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://lmstudio:1234")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gte-large")
RERANK_MODEL = os.getenv("RERANK_MODEL", "bge-reranker-v2-m3")

VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "qdrant")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", "6333"))
VECTOR_DB_COLLECTION = os.getenv("VECTOR_DB_COLLECTION", "documents")

BM25_INDEX_PATH = os.getenv("BM25_INDEX", "/bm25/bm25.pkl")
USE_BM25_DEFAULT = str_to_bool(os.getenv("USE_BM25", "true"), default=True)

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))  # secondes
