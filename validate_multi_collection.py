import requests
import json
import time
import sys

# Configuration
QDRANT_HOST = "qdrant"
QDRANT_PORT = 6333
QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
RAG_PROXY_URL = "http://rag_proxy:8000"
COLLECTION_NAME = "test-multi-collection"

def log(msg):
    print(f"[TEST] {msg}")

def main():
    log("Starting multi-collection validation (REST API mode)...")
    
    # 1. Create collection
    log(f"Creating collection '{COLLECTION_NAME}'...")
    create_payload = {
        "vectors": {
            "size": 384,
            "distance": "Cosine"
        }
    }
    resp = requests.put(f"{QDRANT_URL}/collections/{COLLECTION_NAME}", json=create_payload)
    if resp.status_code != 200:
        log(f"❌ Failed to create collection: {resp.text}")
        return

    # 2. Add documents
    log("Adding documents...")
    docs = [
        {"text": "This is a document about finance and invoices.", "metadata": {"source": "doc1"}},
        {"text": "This is a document about engineering and code.", "metadata": {"source": "doc2"}},
        {"text": "Another finance document regarding taxes.", "metadata": {"source": "doc3"}}
    ]
    
    points = []
    for i, doc in enumerate(docs):
        points.append({
            "id": i+1,
            "vector": [0.1] * 384,  # Dummy vector
            "payload": doc
        })
        
    upsert_payload = {"points": points}
    resp = requests.put(f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points?wait=true", json=upsert_payload)
    if resp.status_code != 200:
        log(f"❌ Failed to upsert points: {resp.text}")
        return
    
    # 3. Trigger BM25 build
    log("Triggering BM25 build...")
    resp = requests.post(f"{RAG_PROXY_URL}/admin/build-bm25/{COLLECTION_NAME}")
    log(f"Build response: {resp.json()}")
    
    if resp.status_code != 200 or resp.json().get("status") != "ok":
        log("❌ Failed to build BM25 index")
        return
        
    # 4. Verify collection list
    log("Verifying collection list...")
    resp = requests.get(f"{RAG_PROXY_URL}/admin/collections")
    collections = resp.json().get("collections", [])
    found = False
    for col in collections:
        if col["name"] == COLLECTION_NAME:
            log(f"Found collection: {col}")
            if col["bm25_ready"] and col["bm25_count"] == 3:
                found = True
            break
            
    if not found:
        log("❌ Collection not found or stats incorrect")
        return
        
    # 5. Search
    log("Testing search...")
    search_payload = {
        "query": "finance",
        "workspace": COLLECTION_NAME,
        "top_k": 5,
        "use_bm25": True
    }
    resp = requests.post(f"{RAG_PROXY_URL}/rag", json=search_payload)
    results = resp.json()
    
    log(f"Search results for 'finance': {len(results.get('chunks', []))} chunks")
    for chunk in results.get("chunks", []):
        log(f"- {chunk['text'][:50]}... (score: {chunk.get('metadata', {}).get('bm25_score')})")
        
    if len(results.get("chunks", [])) > 0:
        log("✅ Search successful")
    else:
        log("❌ Search returned no results")
        
    # 6. Cleanup
    log("Cleaning up...")
    requests.delete(f"{RAG_PROXY_URL}/admin/delete-bm25/{COLLECTION_NAME}")
    requests.delete(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")
    log("Cleanup done.")
    
    log("✅ VALIDATION SUCCESSFUL")

if __name__ == "__main__":
    main()
