"""
LLM Gateway Service - Unified interface for multiple LLM providers.

Uses LiteLLM to abstract LLM calls across providers:
- LM Studio (local, default)
- OpenAI (cloud)
- Anthropic (cloud)
- Groq (cloud, fast & free tier)
- Mistral (cloud, EU-based)
- Google Gemini (cloud, free tier)
- Ollama (local alternative)

Author: Mail2RAG Team
"""
import logging
import os
from typing import List, Dict, Any, Optional

import litellm
from litellm import completion, embedding

from .config import (
    LLM_PROVIDER,
    LM_STUDIO_URL,
    EMBED_MODEL,
    LLM_CHAT_MODEL,
    LLM_CHAT_MODEL_LITELLM,
    LLM_VISION_MODEL,
    LLM_EMBED_MODEL_LITELLM,
    LLM_FALLBACK_MODELS,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    LLM_CHAT_TEMPERATURE,
    LLM_CHAT_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

# Configure LiteLLM logging
litellm.set_verbose = False


class LLMGateway:
    """
    Unified LLM gateway supporting multiple providers.
    
    Provides consistent interface for:
    - Chat completions
    - Vision analysis
    - Embeddings generation
    """
    
    def __init__(self):
        """Initialize the LLM Gateway with provider configuration."""
        self.provider = LLM_PROVIDER.lower()
        self._setup_provider()
        
        logger.info(
            f"LLM Gateway initialized: provider={self.provider}, "
            f"chat_model={self.chat_model}, embed_model={self.embed_model}"
        )
    
    def _setup_provider(self):
        """Configure LiteLLM based on the selected provider."""
        if self.provider == "lmstudio":
            # LM Studio uses OpenAI-compatible API
            self.base_url = LM_STUDIO_URL
            self.api_key = "lm-studio"  # LM Studio doesn't need a real key
            
            # Use existing model names from config
            self.chat_model = f"openai/{LLM_CHAT_MODEL}"
            self.vision_model = f"openai/{LLM_CHAT_MODEL}"  # Same model for vision
            self.embed_model = f"openai/{EMBED_MODEL}"
            
            # Set LiteLLM to use custom base URL
            os.environ["OPENAI_API_BASE"] = f"{LM_STUDIO_URL}/v1"
            os.environ["OPENAI_API_KEY"] = self.api_key
            
        elif self.provider == "openai":
            self.base_url = None
            self.api_key = OPENAI_API_KEY
            
            self.chat_model = LLM_CHAT_MODEL_LITELLM or "openai/gpt-4o-mini"
            self.vision_model = LLM_VISION_MODEL or "openai/gpt-4o"
            self.embed_model = LLM_EMBED_MODEL_LITELLM or "openai/text-embedding-3-small"
            
            if self.api_key:
                os.environ["OPENAI_API_KEY"] = self.api_key
            
        elif self.provider == "anthropic":
            self.base_url = None
            self.api_key = ANTHROPIC_API_KEY
            
            self.chat_model = LLM_CHAT_MODEL_LITELLM or "anthropic/claude-3-haiku-20240307"
            self.vision_model = LLM_VISION_MODEL or "anthropic/claude-3-5-sonnet-20241022"
            # Anthropic doesn't have embeddings, fallback to OpenAI
            self.embed_model = LLM_EMBED_MODEL_LITELLM or "openai/text-embedding-3-small"
            
            if self.api_key:
                os.environ["ANTHROPIC_API_KEY"] = self.api_key
        
        elif self.provider == "groq":
            # Groq: Fast inference, generous free tier
            self.base_url = None
            self.api_key = os.getenv("GROQ_API_KEY", "")
            
            self.chat_model = LLM_CHAT_MODEL_LITELLM or "groq/llama-3.1-8b-instant"
            self.vision_model = LLM_VISION_MODEL or "groq/llava-v1.5-7b-4096-preview"
            # Groq doesn't have embeddings, fallback to OpenAI
            self.embed_model = LLM_EMBED_MODEL_LITELLM or "openai/text-embedding-3-small"
            
            if self.api_key:
                os.environ["GROQ_API_KEY"] = self.api_key
        
        elif self.provider == "mistral":
            # Mistral AI: EU-based, RGPD-friendly
            self.base_url = None
            self.api_key = os.getenv("MISTRAL_API_KEY", "")
            
            self.chat_model = LLM_CHAT_MODEL_LITELLM or "mistral/mistral-small-latest"
            self.vision_model = LLM_VISION_MODEL or "mistral/pixtral-12b-2409"
            self.embed_model = LLM_EMBED_MODEL_LITELLM or "mistral/mistral-embed"
            
            if self.api_key:
                os.environ["MISTRAL_API_KEY"] = self.api_key
        
        elif self.provider == "gemini":
            # Google Gemini: Generous free tier
            self.base_url = None
            self.api_key = os.getenv("GEMINI_API_KEY", "")
            
            self.chat_model = LLM_CHAT_MODEL_LITELLM or "gemini/gemini-1.5-flash"
            self.vision_model = LLM_VISION_MODEL or "gemini/gemini-1.5-pro"
            self.embed_model = LLM_EMBED_MODEL_LITELLM or "gemini/text-embedding-004"
            
            if self.api_key:
                os.environ["GEMINI_API_KEY"] = self.api_key
        
        elif self.provider == "ollama":
            # Ollama: Local alternative to LM Studio
            self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self.api_key = "ollama"  # Ollama doesn't need a key
            
            self.chat_model = LLM_CHAT_MODEL_LITELLM or "ollama/llama3"
            self.vision_model = LLM_VISION_MODEL or "ollama/llava"
            self.embed_model = LLM_EMBED_MODEL_LITELLM or "ollama/nomic-embed-text"
            
            os.environ["OLLAMA_API_BASE"] = self.base_url
        
        else:
            # Fallback to LM Studio
            logger.warning(f"Unknown provider '{self.provider}', falling back to lmstudio")
            self.provider = "lmstudio"
            self._setup_provider()
        
        self.fallback_models = LLM_FALLBACK_MODELS
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Generate a chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Override model (optional)
            temperature: Override temperature (optional)
            max_tokens: Override max tokens (optional)
            **kwargs: Additional LiteLLM parameters
            
        Returns:
            Generated text response
        """
        try:
            target_model = model or self.chat_model
            
            # Build request params
            params = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature if temperature is not None else LLM_CHAT_TEMPERATURE,
                "max_tokens": max_tokens if max_tokens is not None else LLM_CHAT_MAX_TOKENS,
            }
            
            # Add LM Studio specific config
            if self.provider == "lmstudio":
                params["api_base"] = f"{self.base_url}/v1"
                params["api_key"] = self.api_key
            
            # Add fallbacks if configured
            if self.fallback_models:
                params["fallbacks"] = self.fallback_models
            
            params.update(kwargs)
            
            logger.debug(f"LLM chat request: model={target_model}")
            
            response = completion(**params)
            
            content = response.choices[0].message.content
            logger.debug(f"LLM chat response: {len(content)} chars")
            
            return content
            
        except Exception as e:
            logger.error(f"LLM chat error: {e}", exc_info=True)
            raise
    
    def vision(
        self,
        prompt: str,
        image_base64: str,
        model: Optional[str] = None,
        max_tokens: int = 1500,
    ) -> str:
        """
        Analyze an image using a vision-capable model.
        
        Args:
            prompt: Text prompt describing what to analyze
            image_base64: Base64-encoded image data
            model: Override model (optional)
            max_tokens: Max tokens for response
            
        Returns:
            Generated description/analysis
        """
        try:
            target_model = model or self.vision_model
            
            # Build vision message format
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]
            
            params = {
                "model": target_model,
                "messages": messages,
                "max_tokens": max_tokens,
            }
            
            # Add LM Studio specific config
            if self.provider == "lmstudio":
                params["api_base"] = f"{self.base_url}/v1"
                params["api_key"] = self.api_key
            
            logger.debug(f"LLM vision request: model={target_model}")
            
            response = completion(**params)
            
            content = response.choices[0].message.content
            logger.debug(f"LLM vision response: {len(content)} chars")
            
            return content
            
        except Exception as e:
            logger.error(f"LLM vision error: {e}", exc_info=True)
            raise
    
    def embed(
        self,
        texts: List[str],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of texts to embed
            model: Override model (optional)
            
        Returns:
            List of embedding vectors
        """
        try:
            target_model = model or self.embed_model
            
            params = {
                "model": target_model,
                "input": texts,
            }
            
            # Add LM Studio specific config
            if self.provider == "lmstudio":
                params["api_base"] = f"{self.base_url}/v1"
                params["api_key"] = self.api_key
            
            logger.debug(f"LLM embed request: model={target_model}, texts={len(texts)}")
            
            response = embedding(**params)
            
            embeddings = [item["embedding"] for item in response.data]
            logger.debug(f"LLM embed response: {len(embeddings)} vectors")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"LLM embed error: {e}", exc_info=True)
            raise
    
    def embed_single(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            model: Override model (optional)
            
        Returns:
            Embedding vector
        """
        embeddings = self.embed([text], model)
        return embeddings[0] if embeddings else []


# Singleton instance
_gateway: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    """Get or create the singleton LLM Gateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
