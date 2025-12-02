#!/usr/bin/env python3
"""
Script pour créer l'index BM25 à partir des documents via l'abstraction VectorDB.
À exécuter une fois que la base vectorielle contient des documents.
"""

import os
import sys
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi

# Ajouter le dossier courant au path pour pouvoir importer app
sys.path.append(str(Path(__file__).parent))

try:
    from app.vectordb import VectorDBService
except ImportError:
    print("❌ Impossible d'importer app.vectordb. Assurez-vous d'être à la racine de ragproxy.")
    sys.exit(1)

def create_index():
    # Paramètres (modifiables via ENV)
    DB_HOST = os.getenv("VECTOR_DB_HOST", "localhost")
    DB_PORT = int(os.getenv("VECTOR_DB_PORT", "6333"))
    COLLECTION = os.getenv("VECTOR_DB_COLLECTION", "documents")
    OUTPUT = os.getenv("BM25_OUTPUT", "./bm25/bm25.pkl")
    
    print("=" * 60)
    print("🚀 Création de l'Index BM25 (via Abstraction VectorDB)")
    print("=" * 60)
    print(f"DB Host: {DB_HOST}:{DB_PORT}")
    print(f"Collection: {COLLECTION}")
    print(f"Output: {OUTPUT}")
    print("-" * 60)

    # 1. Initialisation du Service de Base de Données (Abstraction)
    print("🔌 Connexion à la base vectorielle...")
    try:
        vdb = VectorDBService(host=DB_HOST, port=DB_PORT, collection_name=COLLECTION)
        
        if not vdb.is_ready():
            print("❌ Erreur: La base de données n'est pas accessible.")
            return
            
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return

    # 2. Récupération des documents
    print("📥 Récupération des documents...")
    try:
        all_docs = vdb.get_all_documents()
        
        if not all_docs:
            print("⚠️ Aucun document trouvé dans la collection.")
            return
            
        print(f"✅ {len(all_docs)} documents récupérés.")
        
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des documents: {e}")
        return

    # 3. Préparation des données
    print("⚙️ Traitement des données...")
    docs = []
    meta = []
    
    for item in all_docs:
        text = item.get("text", "")
        if text:
            docs.append(text)
            meta.append(item.get("metadata", {}))

    if not docs:
        print("❌ Aucun texte valide trouvé dans les documents.")
        return

    # 4. Tokenization simple
    # Note: Dans l'app principale, on utilise une tokenization plus avancée.
    # Ici on reste simple pour le script standalone.
    print("✂️ Tokenization...")
    tokenized_corpus = [doc.lower().split() for doc in docs]

    # 5. Création de l'index
    print("🏗️ Construction de l'index BM25...")
    bm25 = BM25Okapi(tokenized_corpus)

    # 6. Sauvegarde
    print(f"💾 Sauvegarde vers {OUTPUT}...")
    output_path = Path(OUTPUT)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        pickle.dump((bm25, docs, meta), f)

    print("=" * 60)
    print(f"✅ SUCCÈS ! Index créé avec {len(docs)} documents.")
    print(f"Taille du fichier : {output_path.stat().st_size / 1024:.2f} KB")
    print("=" * 60)

if __name__ == "__main__":
    create_index()
