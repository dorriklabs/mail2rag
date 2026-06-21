#!/usr/bin/env python3
import requests
import json
import os
import sys

PROXY_URL = "http://localhost:9100"
TIKA_URL = "http://localhost:9120/tika"
FILE_PATH = os.path.join(os.path.dirname(__file__), "tests_framework/data/real_data/5.1 - Règlement écrit.pdf")

def main():
    print(f"🔄 Début du test sur données réelles : {FILE_PATH}")
    
    if not os.path.exists(FILE_PATH):
        print(f"❌ Fichier introuvable : {FILE_PATH}")
        sys.exit(1)

    print("\n⏳ Étape 0 : Extraction du texte du PDF via Tika (localhost:9120)...")
    extracted_text = ""
    try:
        with open(FILE_PATH, 'rb') as f:
            headers = {
                "Accept": "text/plain",
            }
            resp = requests.put(TIKA_URL, data=f, headers=headers, timeout=300)
            if resp.status_code == 200:
                extracted_text = resp.text
                print(f"✅ Extraction terminée. Longueur du texte brut : {len(extracted_text)} caractères.")
            else:
                print(f"❌ Échec de l'extraction Tika. Code: {resp.status_code}")
                sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction Tika : {e}")
        sys.exit(1)

    if not extracted_text.strip():
        print("❌ Le texte extrait est vide.")
        sys.exit(1)

    # 1. Nettoyage de la collection précédente pour éviter les doublons
    try:
        requests.delete(f"{PROXY_URL}/admin/collection/plui_test")
    except:
        pass

    # 2. Ingestion du fichier
    print("\n⏳ Étape 1 : Ingestion du texte dans Qdrant via RAG Proxy...")
    try:
        payload = {
            "collection": "plui_test",
            "text": extracted_text,
            "metadata": {
                "filename": "5.1 - Règlement écrit.pdf", 
                "source": "test"
            },
            "chunk_size": 800,
            "chunk_overlap": 100
        }
        resp = requests.post(f"{PROXY_URL}/admin/ingest", json=payload, timeout=300)
        
        if resp.status_code == 200:
            print(f"✅ Ingestion réussie ! Réponse : {resp.json()}")
        else:
            print(f"❌ Échec de l'ingestion. Code: {resp.status_code}, Réponse: {resp.text}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur lors de l'ingestion : {e}")
        sys.exit(1)
        
    # 3. Recherche avec RAG
    print("\n⏳ Étape 2 : Test de découpage Parent-Child (recherche sémantique)...")
    query_text = "Quelles sont les règles d'emprise au sol dans la zone UH ?"
    print(f"Question posée : '{query_text}'")
    
    payload_search = {
        "query": query_text,
        "workspace": "plui_test",
        "acl_groups": [], # <--- VIDE POUR DÉSACTIVER LE FILTRE ACL
        "top_k": 5,
        "final_k": 3
    }
    
    try:
        resp = requests.post(f"{PROXY_URL}/rag", json=payload_search, timeout=60)
        if resp.status_code != 200:
            print(f"❌ Échec de la recherche. Code: {resp.status_code}, Réponse: {resp.text}")
            sys.exit(1)
            
        data = resp.json()
        chunks = data.get("chunks", [])
        print(f"\n✅ Recherche réussie ! {len(chunks)} chunks trouvés.")
        
        if len(chunks) == 0:
            print("⚠️ Aucun chunk trouvé ! Le filtre ACL ou Qdrant pose problème.")
        
        # 4. Analyse des chunks
        print("\n📊 Analyse des tailles de contexte (Parent-Child) :")
        max_context_size = 0
        
        for i, chunk in enumerate(chunks):
            text_returned = chunk.get("text", "")
            meta = chunk.get("metadata", {})
            extended_text = meta.get("extended_text", "")
            
            context_size = len(extended_text) if extended_text else len(text_returned)
            max_context_size = max(max_context_size, context_size)
            
            print(f"\n--- Chunk #{i+1} ---")
            print(f"Taille du chunk de base : {len(text_returned)} caractères")
            print(f"Aperçu: {text_returned[:100]}...")
            
            if extended_text:
                print(f"Taille du Parent (contexte étendu) : {len(extended_text)} caractères")
                print(f"Ratio d'agrandissement : {len(extended_text) / max(1, len(text_returned)):.2f}x")
            else:
                print("Aucun contexte étendu trouvé dans ce chunk.")
                
        print(f"\n📈 Taille maximale de contexte envoyée au LLM pour 1 chunk : {max_context_size} caractères")
        
        estimated_tokens = int(max_context_size * 0.25) * len(chunks)
        print(f"🧠 Estimation des tokens consomés en entrée LLM pour ces {len(chunks)} chunks : ~{estimated_tokens} tokens")
        
        if estimated_tokens < 4500:
            print("\n✅ SUCCÈS : Le découpage est robuste. Le contexte n'explosera pas la limite de 5500 tokens de Qwen3.")
        else:
            print("\n❌ AVERTISSEMENT : Le contexte généré est trop grand et risque de saturer Qwen3 (OOM).")
            
    except Exception as e:
        print(f"❌ Erreur lors de la recherche : {e}")

if __name__ == "__main__":
    main()
