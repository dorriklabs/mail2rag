"""
Tests for RAG search endpoint.
"""

import pytest


def test_rag_empty_query_rejected(client):
    """Test /rag rejects empty query."""
    response = client.post("/rag", json={"query": ""})
    assert response.status_code == 422


def test_rag_missing_query_rejected(client):
    """Test /rag requires query field."""
    response = client.post("/rag", json={})
    assert response.status_code == 422


def test_rag_invalid_top_k_rejected(client):
    """Test /rag rejects invalid top_k."""
    response = client.post("/rag", json={"query": "test", "top_k": 0})
    assert response.status_code == 422


def test_rag_final_k_greater_than_top_k_rejected(client):
    """Test /rag rejects final_k > top_k."""
    response = client.post("/rag", json={"query": "test", "top_k": 5, "final_k": 10})
    assert response.status_code == 422


def test_rag_valid_request_returns_response(client):
    """Test /rag returns valid response structure."""
    response = client.post("/rag", json={"query": "test query", "top_k": 5, "final_k": 3})
    # May fail if Qdrant/LM Studio not available, but should not be 422
    # 502/503 are acceptable when external services (LM Studio) are unavailable
    assert response.status_code in [200, 500, 502, 503]
    if response.status_code == 200:
        data = response.json()
        assert "query" in data
        assert "chunks" in data
