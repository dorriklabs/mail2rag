"""
Test fixtures for RAG Proxy.
"""

import sys
from pathlib import Path

import pytest

# Add ragproxy to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client (imports app lazily to avoid circular imports)."""
    from main import app
    return TestClient(app)


@pytest.fixture
def api_headers():
    """Headers with test API key."""
    return {"X-API-Key": "test-api-key"}
