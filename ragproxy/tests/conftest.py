"""
Test fixtures for RAG Proxy.
"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def api_headers():
    """Headers with test API key."""
    return {"X-API-Key": "test-api-key"}
