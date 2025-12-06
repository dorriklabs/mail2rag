"""
Chat endpoint with RAG + LLM response generation.
"""

import logging

import requests
from fastapi import APIRouter

from app.config import (
    LLM_STUDIO_URL,
    LLM_CHAT_MODEL,
    LLM_CHAT_TEMPERATURE,
    LLM_CHAT_MAX_TOKENS,
    LLM_CHAT_SYSTEM_PROMPT,
)
from app.models import ChatRequest, ChatResponse
from app.pipeline import RAGPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

# Pipeline instance (will be set by main.py)
pipeline: RAGPipeline = None


def set_pipeline(p: RAGPipeline):
    """Set the pipeline instance for this router."""
    global pipeline
    pipeline = p


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    RAG Chat endpoint:
    1. Hybrid search (Vector + BM25)
    2. Context building
    3. LLM response generation via LM Studio
    """
    try:
        logger.info(f"Chat request: '{req.query[:100]}...'")
        
        # 1. RAG Search
        workspace = req.collection if req.collection else pipeline.vdb.collection_name
        
        rag_result = pipeline.search(
            query=req.query,
            top_k=req.top_k,
            final_k=req.final_k,
            use_bm25=req.use_bm25,
            workspace=workspace,
        )
        
        chunks = rag_result.get("chunks", [])
        
        if not chunks:
            return ChatResponse(
                query=req.query,
                answer="Je n'ai trouvé aucune information pertinente pour répondre à votre question.",
                sources=[],
                debug_info={"error": "No chunks found"}
            )
        
        # 2. Build context
        context_parts = []
        sources = []
        
        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})
            
            context_parts.append(f"[Document {i+1}]")
            context_parts.append(text)
            context_parts.append("")
            
            sources.append({
                "text": text[:200] + "..." if len(text) > 200 else text,
                "score": chunk.get("score", 0.0),
                "metadata": metadata,
            })
        
        context = "\n".join(context_parts)
        
        # 3. Build prompt
        system_prompt = LLM_CHAT_SYSTEM_PROMPT
        user_prompt = f"""Contexte :
{context}

Question : {req.query}

Réponds à la question en te basant uniquement sur le contexte fourni. Si le contexte ne contient pas assez d'informations, dis-le clairement."""
        
        # 4. Call LM Studio
        llm_payload = {
            "model": LLM_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": req.temperature if req.temperature is not None else LLM_CHAT_TEMPERATURE,
            "max_tokens": req.max_tokens if req.max_tokens else LLM_CHAT_MAX_TOKENS,
        }
        
        logger.debug(f"Calling LM Studio at {LLM_STUDIO_URL}/v1/chat/completions")
        
        response = requests.post(
            f"{LLM_STUDIO_URL}/v1/chat/completions",
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
