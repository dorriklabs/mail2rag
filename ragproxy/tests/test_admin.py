"""
Tests for /admin endpoints with mocked dependencies.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestIngestEndpoint:
    """Tests for the /admin/ingest endpoint."""
    
    def test_ingest_success(self, client, mocker):
        """Test successful document ingestion."""
        with patch("app.routers.admin.pipeline") as mock_pipeline:
            # Mock embedder
            mock_pipeline.embedder.embed.return_value = [0.1] * 1024
            
            # Mock vectordb
            mock_pipeline.vdb.upsert_documents.return_value = True
            
            # Mock BM25 (multi-collection mode)
            mock_pipeline.multi_collection_mode = True
            mock_pipeline.bm25_multi = MagicMock()
            
            with patch("app.routers.admin.QdrantProvider") as mock_qdrant:
                mock_qdrant.return_value.get_all_documents.return_value = [
                    {"text": "Test document", "metadata": {}}
                ]
                
                response = client.post("/admin/ingest", json={
                    "collection": "test-collection",
                    "text": "This is a test document for ingestion. It should be chunked and indexed properly.",
                    "metadata": {"source": "test", "doc_id": "test-123"},
                    "chunk_size": 800,
                    "chunk_overlap": 100,
                })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["collection"] == "test-collection"
        assert data["chunks_created"] >= 1
    
    def test_ingest_empty_text(self, client):
        """Test ingestion with empty text returns error."""
        with patch("app.routers.admin.pipeline"):
            response = client.post("/admin/ingest", json={
                "collection": "test-collection",
                "text": "",
                "metadata": {},
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "empty" in data["message"].lower()
    
    def test_ingest_qdrant_failure(self, client, mocker):
        """Test ingestion when Qdrant fails."""
        with patch("app.routers.admin.pipeline") as mock_pipeline:
            mock_pipeline.embedder.embed.return_value = [0.1] * 1024
            mock_pipeline.vdb.upsert_documents.return_value = False
            
            response = client.post("/admin/ingest", json={
                "collection": "test-collection",
                "text": "Test document content",
                "metadata": {},
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "qdrant" in data["message"].lower() or "index" in data["message"].lower()


class TestDeleteEndpoint:
    """Tests for the /admin/document/{doc_id} DELETE endpoint."""
    
    def test_delete_success(self, client):
        """Test successful document deletion."""
        with patch("app.routers.admin.pipeline") as mock_pipeline:
            mock_pipeline.vdb.collection_name = "default"
            mock_pipeline.vdb.delete_by_metadata.return_value = 3  # 3 chunks deleted
            
            response = client.delete("/admin/document/test-doc-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["deleted_count"] == 3
    
    def test_delete_not_found(self, client):
        """Test deletion when document not found."""
        with patch("app.routers.admin.pipeline") as mock_pipeline:
            mock_pipeline.vdb.collection_name = "default"
            mock_pipeline.vdb.delete_by_metadata.return_value = 0
            
            response = client.delete("/admin/document/nonexistent-doc")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["deleted_count"] == 0


class TestCollectionsEndpoint:
    """Tests for the /admin/collections GET endpoint."""
    
    def test_list_collections(self, client):
        """Test listing all collections."""
        with patch("app.routers.admin.pipeline") as mock_pipeline:
            mock_pipeline.vdb.list_collections.return_value = ["default", "workspace-1", "workspace-2"]
            mock_pipeline.multi_collection_mode = True
            mock_pipeline.bm25_multi = MagicMock()
            mock_pipeline.bm25_multi.is_ready.return_value = True
            mock_pipeline.bm25_multi.get_collection_stats.return_value = {"docs_count": 100}
            
            with patch("app.routers.admin.QdrantProvider") as mock_qdrant:
                mock_qdrant.return_value.count_documents.return_value = 150
                
                response = client.get("/admin/collections")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["multi_collection_mode"] is True
        assert len(data["collections"]) == 3
