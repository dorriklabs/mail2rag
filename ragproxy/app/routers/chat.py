"""
Chat endpoint with RAG + LLM response generation.

Supports multiple LLM providers via LiteLLM Gateway:
- LM Studio (default, local)
- OpenAI, Anthropic, etc. (cloud)
"""

import logging

import requests
from fastapi import APIRouter

from app.config import (
    LM_STUDIO_URL,
    LLM_CHAT_MODEL,
    LLM_CHAT_TEMPERATURE,
    LLM_CHAT_MAX_TOKENS,
    LLM_CHAT_SYSTEM_PROMPT,
    LLM_MAX_CONTEXT_TOKENS,
    LLM_PROVIDER,
)
from app.models import ChatRequest, ChatResponse
from app.pipeline import RAGPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

# Pipeline instance (will be set by main.py)
pipeline: RAGPipeline = None

# Estimation: ~4 caractères par token (approximation pour le français)
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estime le nombre de tokens pour un texte donné."""
    return len(text) // CHARS_PER_TOKEN


def set_pipeline(p: RAGPipeline):
    """Set the pipeline instance for this router."""
    global pipeline
    pipeline = p


# LLM Gateway singleton (lazy loaded)
_llm_gateway = None


def _get_llm_gateway():
    """Get or create LLM Gateway for cloud providers."""
    global _llm_gateway
    if _llm_gateway is None:
        from app.llm_gateway import get_llm_gateway
        _llm_gateway = get_llm_gateway()
    return _llm_gateway


def _use_gateway() -> bool:
    """Check if we should use LLM Gateway instead of direct HTTP."""
    return LLM_PROVIDER.lower() not in ("lmstudio", "")


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    RAG Chat endpoint:
    1. Hybrid search (Vector + BM25)
    2. Context building with dynamic token limiting
    3. LLM response generation via LM Studio
    """
    try:
        logger.info(f"Chat request: '{req.query[:100]}...'")
        
        # 1. RAG Search with full pipeline
        workspace = req.collection if req.collection else pipeline.vdb.collection_name
        
        # pipeline.run() returns (chunks, debug_info) tuple
        chunks, rag_debug = pipeline.run(
            query=req.query,
            top_k=req.top_k,
            final_k=req.final_k,
            use_bm25=req.use_bm25,
            workspace=workspace,
        )
        
        
        if not chunks:
            return ChatResponse(
                query=req.query,
                answer="Je n'ai trouvé aucune information pertinente pour répondre à votre question.",
                sources=[],
                debug_info={"error": "No chunks found"}
            )
        
        # 2. Build context with dynamic token limiting
        context_parts = []
        sources = []
        total_tokens = 0
        chunks_used = 0
        
        # Reserve tokens for system prompt, user query, and response buffer
        reserved_tokens = estimate_tokens(LLM_CHAT_SYSTEM_PROMPT) + estimate_tokens(req.query) + 500
        available_tokens = LLM_MAX_CONTEXT_TOKENS - reserved_tokens
        
        logger.debug(f"Context limit: {LLM_MAX_CONTEXT_TOKENS} tokens, available for chunks: {available_tokens}")
        
        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})
            
            # Estimate tokens for this chunk
            chunk_tokens = estimate_tokens(text) + 10  # +10 for formatting
            
            # Check if adding this chunk would exceed the limit
            if total_tokens + chunk_tokens > available_tokens:
                logger.info(f"Context limit reached: {chunks_used} chunks used, {total_tokens} tokens")
                break
            
            context_parts.append(f"[Document {i+1}]")
            context_parts.append(text)
            context_parts.append("")
            
            sources.append({
                "text": text[:200] + "..." if len(text) > 200 else text,
                "score": chunk.get("score", 0.0),
                "metadata": metadata,
            })
            
            total_tokens += chunk_tokens
            chunks_used += 1
        
        if chunks_used == 0:
            # Fallback: include at least the first chunk, truncated
            first_chunk = chunks[0]
            max_chars = available_tokens * CHARS_PER_TOKEN
            text = first_chunk.get("text", "")[:max_chars]
            context_parts = [f"[Document 1]", text, ""]
            sources = [{
                "text": text[:200] + "..." if len(text) > 200 else text,
                "score": first_chunk.get("score", 0.0),
                "metadata": first_chunk.get("metadata", {}),
            }]
            chunks_used = 1
            total_tokens = estimate_tokens(text)
            logger.warning(f"Single chunk truncated to {len(text)} chars to fit context limit")
        
        context = "\n".join(context_parts)
        
        logger.info(f"Context built: {chunks_used}/{len(chunks)} chunks, ~{total_tokens} tokens")
        
        # 3. Build prompt
        system_prompt = LLM_CHAT_SYSTEM_PROMPT
        user_prompt = f"""Contexte :
{context}

Question : {req.query}

Réponds à la question en te basant uniquement sur le contexte fourni. Si le contexte ne contient pas assez d'informations, dis-le clairement."""
        
        # 4. Call LLM (via Gateway or direct HTTP)
        messages = [{"role": "system", "content": system_prompt}]
        
        # Ajouter l'historique de conversation si présent
        if req.history:
            messages.extend(req.history)
            logger.info(f"Using conversation history: {len(req.history)} messages")
        
        # Ajouter la question actuelle
        messages.append({"role": "user", "content": user_prompt})
        
        temperature = req.temperature if req.temperature is not None else LLM_CHAT_TEMPERATURE
        max_tokens = req.max_tokens if req.max_tokens else LLM_CHAT_MAX_TOKENS
        
        if _use_gateway():
            # Use LiteLLM Gateway for cloud providers
            logger.debug(f"Calling LLM via Gateway (provider: {LLM_PROVIDER})")
            try:
                gateway = _get_llm_gateway()
                answer = gateway.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                logger.error(f"LLM Gateway error: {e}")
                return ChatResponse(
                    query=req.query,
                    answer="Erreur lors de la génération de la réponse (LLM indisponible).",
                    sources=sources,
                    debug_info={"llm_error": str(e)}
                )
        else:
            # Direct HTTP for LM Studio (more efficient)
            llm_payload = {
                "model": LLM_CHAT_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            logger.debug(f"Calling LM Studio at {LM_STUDIO_URL}/v1/chat/completions")
            
            response = requests.post(
                f"{LM_STUDIO_URL}/v1/chat/completions",
                json=llm_payload,
                timeout=60,
            )
            
            if response.status_code != 200:
                logger.error(f"LM Studio error: {response.status_code} - {response.text}")
                return ChatResponse(
                    query=req.query,
                    answer="Erreur lors de la génération de la réponse (LLM indisponible).",
                    sources=sources,
                    debug_info={"llm_error": response.text}
                )
            
            llm_response = response.json()
            answer = llm_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not answer:
            answer = "Je n'ai pas pu générer de réponse."
        
        logger.info(f"Chat response generated ({len(answer)} chars)")
        
        return ChatResponse(
            query=req.query,
            answer=answer,
            sources=sources,
            debug_info={
                "chunks_retrieved": len(chunks),
                "chunks_used": chunks_used,
                "context_tokens": total_tokens,
                "context_length": len(context),
                "llm_model": LLM_CHAT_MODEL,
            }
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        return ChatResponse(
            query=req.query,
            answer=f"Une erreur s'est produite : {str(e)}",
            sources=[],
            debug_info={"error": str(e)}
        )
