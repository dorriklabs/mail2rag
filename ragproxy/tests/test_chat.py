"""
Tests for /chat endpoint with mocked dependencies.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestChatEndpoint:
    """Tests for the /chat endpoint."""
    
    def test_chat_success_with_chunks(self, client, mocker):
        """Test successful chat with chunks found and LLM response."""
        # Mock the pipeline.search method
        mock_search_result = {
            "chunks": [
                {"text": "Le contrat a été signé le 15 janvier 2024.", "score": 0.95, "metadata": {}},
                {"text": "La durée est de 12 mois.", "score": 0.85, "metadata": {}},
            ]
        }
        
        # Mock requests.post for LM Studio
        mock_llm_response = MagicMock()
        mock_llm_response.status_code = 200
        mock_llm_response.json.return_value = {
            "choices": [{"message": {"content": "Le contrat a été signé le 15 janvier 2024."}}]
        }
        
        with patch("app.routers.chat.pipeline") as mock_pipeline:
            mock_pipeline.search.return_value = mock_search_result
            mock_pipeline.vdb.collection_name = "default"
            
            with patch("app.routers.chat.requests.post", return_value=mock_llm_response):
                response = client.post("/chat", json={
                    "query": "Quelle est la date du contrat ?",
                    "top_k": 10,
                    "final_k": 3,
                })
        
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "Quelle est la date du contrat ?"
        assert "15 janvier 2024" in data["answer"]
        assert len(data["sources"]) == 2
    
    def test_chat_no_chunks_found(self, client, mocker):
        """Test chat when no relevant chunks are found."""
        with patch("app.routers.chat.pipeline") as mock_pipeline:
            mock_pipeline.search.return_value = {"chunks": []}
            mock_pipeline.vdb.collection_name = "default"
            
            response = client.post("/chat", json={
                "query": "Question sans réponse",
            })
        
        assert response.status_code == 200
        data = response.json()
        assert "aucune information" in data["answer"].lower()
        assert data["sources"] == []
    
    def test_chat_llm_unavailable(self, client, mocker):
        """Test chat when LM Studio is unavailable."""
        mock_search_result = {
            "chunks": [{"text": "Some context", "score": 0.9, "metadata": {}}]
        }
        
        mock_llm_response = MagicMock()
        mock_llm_response.status_code = 500
        mock_llm_response.text = "Internal Server Error"
        
        with patch("app.routers.chat.pipeline") as mock_pipeline:
            mock_pipeline.search.return_value = mock_search_result
            mock_pipeline.vdb.collection_name = "default"
            
            with patch("app.routers.chat.requests.post", return_value=mock_llm_response):
                response = client.post("/chat", json={
                    "query": "Test question",
                })
        
        assert response.status_code == 200
        data = response.json()
        assert "erreur" in data["answer"].lower() or "indisponible" in data["answer"].lower()
    
    def test_chat_validation_empty_query(self, client):
        """Test chat with empty query returns error message."""
        with patch("app.routers.chat.pipeline") as mock_pipeline:
            mock_pipeline.search.side_effect = Exception("Empty query")
            mock_pipeline.vdb.collection_name = "default"
            
            response = client.post("/chat", json={
                "query": "",
            })
        
        # Empty query goes through but triggers error handling
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == ""
        # Should have error in response (caught by exception handler)
