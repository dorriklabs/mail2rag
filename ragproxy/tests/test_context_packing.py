from unittest.mock import MagicMock, patch, AsyncMock
import json
import tiktoken
from fastapi.testclient import TestClient

from main import app
from app.routers.chat import LLM_MAX_CONTEXT_TOKENS

client = TestClient(app)

def test_context_packing_limit(mocker):
    """
    Test que le contexte construit par l'endpoint /chat ne dépasse jamais
    la limite stricte LLM_MAX_CONTEXT_TOKENS, même si les chunks sont gigantesques.
    """
    giant_text = "mot " * 500
    
    mock_search_result = {
        "chunks": [
            {"text": f"Extrait {i}: " + giant_text, "score": 0.9, "metadata": {"uid": str(1000+i), "subject": f"Sujet {i}"}}
            for i in range(20)
        ]
    }
    
    intercepted_prompt = {}
    
    mock_llm = AsyncMock()
    async def mocked_call_llm(messages, temperature, max_tokens):
        intercepted_prompt["messages"] = messages
        return "Dummy answer", {}, 1.0, 10.0
    mock_llm.side_effect = mocked_call_llm

    with patch("app.routers.chat.pipeline") as mock_pipeline:
        mock_pipeline.run.return_value = (mock_search_result["chunks"], {})
        mock_pipeline.search.return_value = mock_search_result
        mock_pipeline.vdb.collection_name = "default"
        mock_pipeline.vdb.check_semantic_cache.return_value = None
        
        with patch("app.routers.chat._call_llm", new=mock_llm):
            response = client.post("/chat", json={
                "query": "Question de test context packing",
                "top_k": 20,
                "final_k": 20,
            })
    
    assert response.status_code == 200
    
    # The actual messages sent to the LLM
    messages = intercepted_prompt.get("messages")
    assert messages is not None, "LLM was not called"
    
    user_prompt = next((m["content"] for m in messages if m["role"] == "user"), "")
    
    # Verify the token length of the generated user_prompt
    enc = tiktoken.get_encoding("cl100k_base")
    total_prompt_tokens = len(enc.encode(user_prompt))
    
    # It should be strictly less than or equal to LLM_MAX_CONTEXT_TOKENS 
    # plus some margin for the instructions (around 200 tokens). 
    # But context itself shouldn't exceed LLM_MAX_CONTEXT_TOKENS.
    assert total_prompt_tokens <= LLM_MAX_CONTEXT_TOKENS + 300, f"Token limit exceeded! Tokens: {total_prompt_tokens}"
    
    data = response.json()
    assert "debug_info" in data
    debug_info = data["debug_info"]
    print("DEBUG INFO:", debug_info)
    
    # The debug info should specify how many chunks were used
    chunks_used = debug_info.get("chunks_used", 0)
    
    # Since 20 * 500 = 10000 tokens, and limit is usually 3500-6000, 
    # it MUST have used less than 20 chunks!
    assert chunks_used < 20, "It used all chunks, packing failed to truncate!"
    assert chunks_used > 0, "No chunks were used!"
    
    print(f"Context packing successful: used {chunks_used}/20 chunks. Total prompt tokens: {total_prompt_tokens}")

if __name__ == "__main__":
    # Fake pytest mocker locally
    test_context_packing_limit(None)
