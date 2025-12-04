import os
from typing import Optional



def str_to_bool(x: Optional[str], default: bool = False) -> bool:
    if x is None:
        return default
    return x.strip().lower() in {"1", "true", "yes", "y", "on"}


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://lmstudio:1234")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gte-large")
RERANK_MODEL = os.getenv("RERANK_MODEL", "bge-reranker-v2-m3")

VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "qdrant")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", "6333"))

# Mode multi-collections : si activé, le système détecte automatiquement
# toutes les collections Qdrant et crée un index BM25 par collection
MULTI_COLLECTION_MODE = str_to_bool(os.getenv("MULTI_COLLECTION_MODE", "true"), default=True)

# Collection par défaut (utilisée en mode mono-collection ou comme fallback)
VECTOR_DB_COLLECTION = os.getenv("VECTOR_DB_COLLECTION", "default-workspace")

BM25_INDEX_PATH = os.getenv("BM25_INDEX", "/bm25/bm25.pkl")
USE_BM25_DEFAULT = str_to_bool(os.getenv("USE_BM25", "true"), default=True)

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))  # secondes

# Reranking : mode local ou via LM Studio
USE_LOCAL_RERANKER = str_to_bool(os.getenv("USE_LOCAL_RERANKER", "true"), default=True)
LOCAL_RERANKER_MODEL = os.getenv("LOCAL_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Limites RAG (configurables via env)
MAX_QUERY_CHARS = int(os.getenv("RAG_MAX_QUERY_CHARS", "10240"))
MAX_TOP_K = int(os.getenv("RAG_MAX_TOP_K", "200"))
# final_k est validé dynamiquement comme <= top_k, donc pas besoin d'un max dédié

MAX_RERANK_PASSAGES = int(os.getenv("MAX_RERANK_PASSAGES", "50"))
