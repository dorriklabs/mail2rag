import os
from typing import Optional



def str_to_bool(x: Optional[str], default: bool = False) -> bool:
    if x is None:
        return default
    return x.strip().lower() in {"1", "true", "yes", "y", "on"}


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# API Authentication (disabled by default)
API_KEY = os.getenv("RAG_PROXY_API_KEY", "")
API_KEY_ENABLED = str_to_bool(os.getenv("API_KEY_ENABLED", "false"), default=False)

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

# Configuration LLM pour génération de réponses (chat endpoint)
LLM_CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "qwen2-vl-7b-instruct")
LLM_CHAT_TEMPERATURE = float(os.getenv("LLM_CHAT_TEMPERATURE", "0.1"))
LLM_CHAT_MAX_TOKENS = int(os.getenv("LLM_CHAT_MAX_TOKENS", "1000"))
LLM_CHAT_SYSTEM_PROMPT = os.getenv(
    "LLM_CHAT_SYSTEM_PROMPT",
    "Tu es un assistant expert Mail2RAG. Ta mission est d'aider l'utilisateur en analysant ses documents et emails archivés.\n\n"
    "RÈGLES STRICTES :\n"
    "1. Réponds TOUJOURS en français.\n"
    "2. Base tes réponses UNIQUEMENT sur le contexte fourni (les documents).\n"
    "3. Si l'information exacte pour la situation ou la zone demandée est absente, dis \"Je ne trouve pas cette information dans vos documents\". Ne déduis JAMAIS que les règles d'une autre zone s'appliquent.\n"
    "4. Sois précis et factuel. Utilise des listes à puces pour la clarté.\n"
    "5. Cite TOUJOURS tes sources en utilisant la syntaxe exacte [Document X] à la fin de tes affirmations.\n"
    "6. Si le contexte renvoie à une autre section réglementaire (ex: 'se reporter aux dispositions communes', 'voir article X'), tu DOIS explicitement mentionner ce renvoi dans ta réponse.\n"
    "7. Sois EXHAUSTIF sur les prérequis et conditions, mais reste strictement dans le périmètre de la question."
)

# Limite de tokens pour le contexte (évite les dépassements de context window)
# Par défaut 6000 tokens (~24000 caractères) pour laisser de la marge au prompt et à la réponse
LLM_MAX_CONTEXT_TOKENS = int(os.getenv("LLM_MAX_CONTEXT_TOKENS", "6000"))

# ---------------------------------------------------------------------------
# SOFT FILTERING & METADATA CONFIGURATION
# ---------------------------------------------------------------------------
# Liste des filtres dynamiques supportés (séparés par des virgules)
RAG_ALLOWED_FILTERS = [
    f.strip() for f in os.getenv("RAG_ALLOWED_FILTERS", "doc_type,status").split(",") if f.strip()
]

# Instruction ajoutée au prompt du Query Router pour extraire ces métadonnées
RAG_QUERY_ROUTER_EXTRA_PROMPT = os.getenv(
    "RAG_QUERY_ROUTER_EXTRA_PROMPT",
    "le type de document attendu (doc_type: facture, procédure, email, rapport, etc.) et le statut (status: validé, brouillon, officiel, obsolète)"
)

# Poids (bonus) accordés lors du reranking (format: key:weight,key:weight)
_weights_str = os.getenv("RAG_FILTER_WEIGHTS", "doc_type:0.20,status:0.15,default:0.10")
RAG_FILTER_WEIGHTS = {}
for pair in _weights_str.split(","):
    if ":" in pair:
        k, v = pair.split(":")
        RAG_FILTER_WEIGHTS[k.strip()] = float(v.strip())
if "default" not in RAG_FILTER_WEIGHTS:
    RAG_FILTER_WEIGHTS["default"] = 0.10
# ---------------------------------------------------------------------------
# LLM PROVIDER CONFIGURATION (LiteLLM Gateway)
# ---------------------------------------------------------------------------
# Provider: lmstudio (default), openai, anthropic
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "lmstudio")

# API Keys for cloud providers (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Model names (LiteLLM format: provider/model-name)
# For LM Studio: use "openai/model-name" with custom base_url
# For OpenAI: use "openai/gpt-4o-mini", "openai/gpt-4o", etc.
# For Anthropic: use "anthropic/claude-3-haiku-20240307", etc.
LLM_CHAT_MODEL_LITELLM = os.getenv("LLM_CHAT_MODEL_LITELLM", "")
LLM_VISION_MODEL = os.getenv("LLM_VISION_MODEL", "")
LLM_EMBED_MODEL_LITELLM = os.getenv("LLM_EMBED_MODEL_LITELLM", "")

# Fallback models (comma-separated, optional)
LLM_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()
]
