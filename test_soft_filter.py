import urllib.request
import urllib.parse
import json
import time

PROXY_URL = "http://localhost:9100"

def ingest(text, year, uid):
    data = {
        "collection": "test-softfilter",
        "text": text,
        "metadata": {"year": year, "uid": uid}
    }
    req = urllib.request.Request(
        f"{PROXY_URL}/admin/ingest",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)

def query_rag(query):
    data = {
        "query": query,
        "top_k": 5,
        "final_k": 2,
        "workspace": "test-softfilter"
    }
    req = urllib.request.Request(
        f"{PROXY_URL}/rag",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read().decode("utf-8"))

def delete(uid):
    req = urllib.request.Request(
        f"{PROXY_URL}/admin/document/{uid}?collection=test-softfilter",
        method="DELETE"
    )
    try:
        urllib.request.urlopen(req)
    except:
        pass

if __name__ == "__main__":
    print("🧹 Nettoyage initial...")
    delete("doc2023")
    delete("doc2024")
    
    print("📥 Ingestion du document 2023...")
    ingest("La piscine municipale est ouverte de 8h à 18h en 2023.", "2023", "doc2023")
    
    print("📥 Ingestion du document 2024...")
    ingest("La piscine municipale est ouverte de 10h à 20h en 2024.", "2024", "doc2024")
    
    time.sleep(1) # Attendre l'indexation Qdrant
    
    q = "Quels sont les horaires de la piscine pour 2024 ?"
    print(f"🔍 Requête RAG : '{q}'")
    
    res = query_rag(q)
    
    print("\n✅ RÉSULTAT RAG :")
    for i, chunk in enumerate(res.get("chunks", [])):
        print(f"Rang {i+1} : Score = {chunk['score']} | Année = {chunk['metadata'].get('year')} | Texte = {chunk['text']}")
        
    print("\n🛠️  Debug Info :")
    print(json.dumps(res.get("debug_info"), indent=2, ensure_ascii=False))
    
    print("\n🧹 Nettoyage final...")
    delete("doc2023")
    delete("doc2024")
