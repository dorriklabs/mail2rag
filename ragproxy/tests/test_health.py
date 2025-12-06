"""
Tests for health endpoints.
"""


def test_healthz(client):
    """Test /healthz returns ok."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health(client):
    """Test /health alias returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_structure(client):
    """Test /readyz returns expected structure."""
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert "ready" in data
    assert "deps" in data
    assert isinstance(data["deps"], dict)
