"""
LLM Client Service - Unified interface for LLM calls in Mail2RAG.

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
import base64
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import litellm
from litellm import completion

logger = logging.getLogger(__name__)

# Configure LiteLLM logging
litellm.set_verbose = False


class LLMClient:
    """
    Unified LLM client for Mail2RAG.
    
    Provides consistent interface for:
    - Chat completions
    - Vision analysis (image description)
    """
    
    def __init__(self, config):
        """
        Initialize the LLM Client.
        
        Args:
            config: Mail2RAG Config instance
        """
        self.config = config
        self.provider = os.getenv("LLM_PROVIDER", "lmstudio").lower()
        self._setup_provider()
        
        logger.info(
            f"LLMClient initialized: provider={self.provider}, "
            f"chat_model={self.chat_model}, vision_model={self.vision_model}"
        )
    
    def _setup_provider(self):
        """Configure LiteLLM based on the selected provider."""
        if self.provider == "lmstudio":
            # LM Studio uses OpenAI-compatible API
            self.base_url = self.config.ai_api_url.rsplit("/", 1)[0]  # Remove /chat/completions
            self.api_key = self.config.ai_api_key or "lm-studio"
            
            # Use existing model names from config
            self.chat_model = f"openai/{self.config.llm_chat_model}"
            self.vision_model = f"openai/{self.config.ai_model_name}"
            
            # Set environment for LiteLLM
            os.environ["OPENAI_API_BASE"] = self.base_url
            os.environ["OPENAI_API_KEY"] = self.api_key
            
        elif self.provider == "openai":
            self.base_url = None
            self.api_key = os.getenv("OPENAI_API_KEY", "")
            
            self.chat_model = os.getenv("LLM_CHAT_MODEL_LITELLM", "openai/gpt-4o-mini")
            self.vision_model = os.getenv("LLM_VISION_MODEL", "openai/gpt-4o")
            
            if self.api_key:
                os.environ["OPENAI_API_KEY"] = self.api_key
            
        elif self.provider == "anthropic":
            self.base_url = None
            self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
            
            self.chat_model = os.getenv("LLM_CHAT_MODEL_LITELLM", "anthropic/claude-3-haiku-20240307")
            self.vision_model = os.getenv("LLM_VISION_MODEL", "anthropic/claude-3-5-sonnet-20241022")
            
            if self.api_key:
                os.environ["ANTHROPIC_API_KEY"] = self.api_key
        
        elif self.provider == "groq":
            # Groq: Fast inference, generous free tier
            self.base_url = None
            self.api_key = os.getenv("GROQ_API_KEY", "")
            
            self.chat_model = os.getenv("LLM_CHAT_MODEL_LITELLM", "groq/llama-3.1-8b-instant")
            self.vision_model = os.getenv("LLM_VISION_MODEL", "groq/llava-v1.5-7b-4096-preview")
            
            if self.api_key:
                os.environ["GROQ_API_KEY"] = self.api_key
        
        elif self.provider == "mistral":
            # Mistral AI: EU-based, RGPD-friendly
            self.base_url = None
            self.api_key = os.getenv("MISTRAL_API_KEY", "")
            
            self.chat_model = os.getenv("LLM_CHAT_MODEL_LITELLM", "mistral/mistral-small-latest")
            self.vision_model = os.getenv("LLM_VISION_MODEL", "mistral/pixtral-12b-2409")
            
            if self.api_key:
                os.environ["MISTRAL_API_KEY"] = self.api_key
        
        elif self.provider == "gemini":
            # Google Gemini: Generous free tier
            self.base_url = None
            self.api_key = os.getenv("GEMINI_API_KEY", "")
            
            self.chat_model = os.getenv("LLM_CHAT_MODEL_LITELLM", "gemini/gemini-1.5-flash")
            self.vision_model = os.getenv("LLM_VISION_MODEL", "gemini/gemini-1.5-pro")
            
            if self.api_key:
                os.environ["GEMINI_API_KEY"] = self.api_key
        
        elif self.provider == "ollama":
            # Ollama: Local alternative to LM Studio
            self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self.api_key = "ollama"
            
            self.chat_model = os.getenv("LLM_CHAT_MODEL_LITELLM", "ollama/llama3")
            self.vision_model = os.getenv("LLM_VISION_MODEL", "ollama/llava")
            
            os.environ["OLLAMA_API_BASE"] = self.base_url
        
        else:
            # Fallback to LM Studio
            logger.warning(f"Unknown provider '{self.provider}', falling back to lmstudio")
            self.provider = "lmstudio"
            self._setup_provider()
        
        # Fallback models (optional)
        self.fallback_models = [
            m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()
        ]
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Generate a chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Override model (optional)
            temperature: Override temperature (optional)
            max_tokens: Override max tokens (optional)
            timeout: Request timeout in seconds (optional)
            
        Returns:
            Generated text response
        """
        try:
            target_model = model or self.chat_model
            
            # Build request params
            params = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature if temperature is not None else 0.7,
                "max_tokens": max_tokens if max_tokens is not None else 1000,
            }
            
            # Add LM Studio specific config
            if self.provider == "lmstudio":
                params["api_base"] = self.base_url
                params["api_key"] = self.api_key
            
            # Add fallbacks if configured
            if self.fallback_models:
                params["fallbacks"] = self.fallback_models
            
            # Add timeout if specified
            if timeout:
                params["timeout"] = timeout
            
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
        image_path: Optional[Path] = None,
        image_base64: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1500,
        timeout: int = 90,
    ) -> str:
        """
        Analyze an image using a vision-capable model.
        
        Args:
            prompt: Text prompt describing what to analyze
            image_path: Path to image file (optional)
            image_base64: Base64-encoded image data (optional)
            model: Override model (optional)
            max_tokens: Max tokens for response
            timeout: Request timeout in seconds
            
        Returns:
            Generated description/analysis
        """
        try:
            target_model = model or self.vision_model
            
            # Get base64 from path if needed
            if image_path and not image_base64:
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            if not image_base64:
                raise ValueError("Either image_path or image_base64 must be provided")
            
            # Determine image type from path or default to jpeg
            image_type = "jpeg"
            if image_path:
                suffix = Path(image_path).suffix.lower()
                if suffix in (".png",):
                    image_type = "png"
                elif suffix in (".webp",):
                    image_type = "webp"
            
            # Build vision message format
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]
            
            params = {
                "model": target_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
            
            # Add LM Studio specific config
            if self.provider == "lmstudio":
                params["api_base"] = self.base_url
                params["api_key"] = self.api_key
            
            logger.debug(f"LLM vision request: model={target_model}")
            
            response = completion(**params)
            
            content = response.choices[0].message.content
            logger.debug(f"LLM vision response: {len(content)} chars")
            
            return content
            
        except Exception as e:
            logger.error(f"LLM vision error: {e}", exc_info=True)
            raise


# Singleton instance
_client: Optional[LLMClient] = None


def get_llm_client(config) -> LLMClient:
    """Get or create the singleton LLM Client instance."""
    global _client
    if _client is None:
        _client = LLMClient(config)
    return _client


def use_gateway() -> bool:
    """Check if we should use LiteLLM Gateway instead of direct HTTP."""
    provider = os.getenv("LLM_PROVIDER", "lmstudio").lower()
    return provider not in ("lmstudio", "")
