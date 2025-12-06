"""
Tests for Pydantic models.
"""

import pytest
from pydantic import ValidationError

from app.models import (
    RequestModel,
    IngestRequest,
    ChatRequest,
)


class TestRequestModel:
    """Tests for RAG RequestModel."""
    
    def test_valid_request(self):
        """Test valid request is accepted."""
        req = RequestModel(query="test query")
        assert req.query == "test query"
        assert req.top_k == 20  # default
        assert req.final_k == 5  # default
    
    def test_custom_values(self):
        """Test custom values are preserved."""
        req = RequestModel(query="test", top_k=10, final_k=3, use_bm25=False)
        assert req.top_k == 10
        assert req.final_k == 3
        assert req.use_bm25 is False
    
    def test_workspace_optional(self):
        """Test workspace is optional."""
        req = RequestModel(query="test", workspace="my-workspace")
        assert req.workspace == "my-workspace"


class TestIngestRequest:
    """Tests for IngestRequest model."""
    
    def test_valid_ingest(self):
        """Test valid ingest request."""
        req = IngestRequest(collection="test", text="some content")
        assert req.collection == "test"
        assert req.text == "some content"
        assert req.chunk_size == 800  # default
    
    def test_custom_chunking(self):
        """Test custom chunk settings."""
        req = IngestRequest(
            collection="test",
            text="content",
            chunk_size=500,
            chunk_overlap=50,
        )
        assert req.chunk_size == 500
        assert req.chunk_overlap == 50


class TestChatRequest:
    """Tests for ChatRequest model."""
    
    def test_valid_chat(self):
        """Test valid chat request."""
        req = ChatRequest(query="What is AI?")
        assert req.query == "What is AI?"
        assert req.temperature == 0.1  # default
    
    def test_custom_llm_settings(self):
        """Test custom LLM settings."""
        req = ChatRequest(
            query="test",
            temperature=0.7,
            max_tokens=2000,
        )
        assert req.temperature == 0.7
        assert req.max_tokens == 2000
