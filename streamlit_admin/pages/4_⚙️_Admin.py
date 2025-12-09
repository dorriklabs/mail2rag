"""
Page 4 : Administration
Rebuild BM25, logs système, configuration
"""

import streamlit as st
import requests
from datetime import datetime

st.set_page_config(page_title="Administration", page_icon="⚙️", layout="wide")

RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")

st.title("⚙️ Administration")

# Fonctions helper
def get_collections():
    try:
        response = requests.get(f"{RAG_PROXY_URL}/admin/collections", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                return data.get("collections", [])
        return []
    except:
        return []

def rebuild_bm25(collection):
    try:
        response = requests.post(
            f"{RAG_PROXY_URL}/admin/build-bm25/{collection}",
            timeout=60
        )
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        st.error(f"Erreur: {e}")
        return None

def rebuild_all_bm25():
    try:
        response = requests.post(
            f"{RAG_PROXY_URL}/admin/rebuild-all-bm25",
            timeout=120
        )
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        st.error(f"Erreur: {e}")
        return None

# Tabs
tab1, tab2, tab3 = st.tabs(["🔨 Index BM25", "📜 Logs Système", "🔧 Configuration"])

# =====================================
# TAB 1 : Index BM25
# =====================================
with tab1:
    st.header("🔨 Gestion Index BM25")
    
    st.markdown("""
    Les index BM25 permettent la recherche par mots-clés. 
    Ils doivent être reconstruits après l'ingestion de nouveaux documents.
    """)
    
    st.divider()
    
    collections = get_collections()
    
    if not collections:
        st.warning("Aucune collection disponible")
    else:
        # Rebuild toutes les collections
        st.subheader("🌍 Rebuild Global")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.info(f"Reconstruire l'index BM25 pour toutes les {len(collections)} collections")
        
        with col2:
            if st.button("🔨 Rebuild All", type="primary", use_container_width=True):
                with st.spinner("Reconstruction globale en cours..."):
                    result = rebuild_all_bm25()
                    
                    if result and result.get("status") == "ok":
                        st.success(f"✅ {result.get('success_count', 0)}/{result.get('total_collections', 0)} collections indexées")
                        
                        # Afficher les détails
                        if result.get("results"):
                            with st.expander("📋 Détails par collection"):
                                for r in result["results"]:
                                    status_icon = "✅" if r["status"] == "ok" else "❌"
                                    st.text(f"{status_icon} {r['collection']}: {r.get('docs_count', 0)} docs")
                    else:
                        st.error("❌ Échec du rebuild global")
        
        st.divider()
        
        # Rebuild par collection
        st.subheader("🎯 Rebuild par Collection")
        
        for collection in collections:
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            
            with col1:
                st.text(f"📚 {collection['name']}")
            
            with col2:
                qdrant_count = collection.get("qdrant_count", 0)
                st.text(f"📄 {qdrant_count} docs")
            
            with col3:
                bm25_status = "✅" if collection.get("bm25_ready") else "❌"
                bm25_count = collection.get("bm25_count", 0)
                st.text(f"{bm25_status} BM25: {bm25_count}")
            
            with col4:
                if st.button("🔨 Rebuild", key=f"rebuild_{collection['name']}", use_container_width=True):
                    with st.spinner(f"Rebuild de '{collection['name']}'..."):
                        result = rebuild_bm25(collection['name'])
                        
                        if result and result.get("status") == "ok":
                            st.success(f"✅ {result.get('docs_count', 0)} documents indexés")
                            st.rerun()
                        else:
                            st.error(f"❌ Échec: {result.get('message') if result else 'Erreur inconnue'}")
        
        st.divider()
        
        # Danger Zone - Suppression de collection
        st.markdown("### ⚠️ Zone de Danger")
        
        with st.expander("🗑️ Supprimer une Collection", expanded=False):
            st.warning("""
            **Attention !** La suppression d'une collection est irréversible.
            Cette action supprime:
            - Tous les documents de Qdrant
            - L'index BM25 associé
            """)
            
            # Sélecteur de collection à supprimer
            collection_names = [c["name"] for c in collections]
            collection_to_delete = st.selectbox(
                "Collection à supprimer",
                options=collection_names,
                key="collection_to_delete",
                help="Sélectionnez la collection à supprimer"
            )
            
            # Confirmation par texte
            confirm_text = st.text_input(
                "Confirmez en tapant le nom de la collection",
                key="confirm_delete",
                help="Tapez exactement le nom de la collection pour confirmer"
            )
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                delete_archives = st.checkbox(
                    "Supprimer aussi les dossiers d'archive",
                    key="delete_archives_with_collection",
                    help="Supprime tous les dossiers d'archive associés à cette collection"
                )
            
            with col2:
                if st.button("🗑️ Supprimer la Collection", type="primary", use_container_width=True):
                    if confirm_text == collection_to_delete:
                        with st.spinner(f"Suppression de '{collection_to_delete}'..."):
                            try:
                                # Appeler l'API de suppression
                                response = requests.delete(
                                    f"{RAG_PROXY_URL}/admin/collection/{collection_to_delete}",
                                    timeout=30
                                )
                                
                                if response.status_code == 200:
                                    result = response.json()
                                    if result.get("status") == "ok":
                                        msg = f"✅ Collection '{collection_to_delete}' supprimée"
                                        if result.get("qdrant_deleted"):
                                            msg += " (Qdrant ✓)"
                                        if result.get("bm25_deleted"):
                                            msg += " (BM25 ✓)"
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Échec: {result.get('message', 'Erreur inconnue')}")
                                else:
                                    st.error(f"❌ Erreur HTTP: {response.status_code}")
                            except Exception as e:
                                st.error(f"❌ Erreur: {e}")
                    else:
                        st.error("❌ Le nom de confirmation ne correspond pas")

# =====================================
# TAB 2 : Logs Système
# =====================================
with tab2:
    st.header("📜 Logs Système")
    
    st.info("💡 **Tip:** Utilisez Docker pour accéder aux logs en temps réel")
    
    st.markdown("""
    ### Commandes Docker
    
    ```bash
    # Logs RAG Proxy
    docker-compose logs -f rag_proxy
    
    # Logs Mail2RAG
    docker-compose logs -f mail2rag
    
    # Logs Qdrant
    docker-compose logs -f qdrant
    
    # Tous les services
    docker-compose logs -f
    ```
    """)
    
    st.divider()
    
    st.markdown("""
    ### Logs Importants
    
    **RAG Proxy:**
    - Requêtes d'ingestion
    - Recherches RAG
    - Rebuild BM25
    
    **Mail2RAG:**
    - Emails reçus
    - Documents traités
    - Erreurs d'ingestion
    
    **Qdrant:**
    - Opérations sur collections
    - Indexation de vecteurs
    """)

# =====================================
# TAB 3 : Configuration
# =====================================
with tab3:
    st.header("🔧 Configuration")
    
    st.markdown("""
    ### Variables d'Environnement
    
    Les paramètres suivants sont configurables via `.env` :
    """)
    
    # Paramètres chunking
    st.subheader("📏 Chunking Intelligent")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.code("""
CHUNK_SIZE=800
CHUNK_OVERLAP=100
CHUNKING_STRATEGY=recursive
        """, language="bash")
    
    with col2:
        st.markdown("""
        - **CHUNK_SIZE**: Taille maximale des chunks (caractères)
        - **CHUNK_OVERLAP**: Chevauchement entre chunks
        - **CHUNKING_STRATEGY**: Stratégie de découpage
        """)
    
    st.divider()
    
    # Ingestion (RAG Proxy uniquement)
    st.subheader("📥 Ingestion")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.code("""
RAG_PROXY_URL=http://rag_proxy:8000
EMBED_MODEL=text-embedding-bge-m3
LLM_CHAT_MODEL=qwen2.5-7b-instruct
        """, language="bash")
    
    with col2:
        st.markdown("""
        - **RAG_PROXY_URL**: URL du service RAG Proxy
        - **EMBED_MODEL**: Modèle d'embedding
        - **LLM_CHAT_MODEL**: Modèle LLM pour les réponses
        """)
    
    st.divider()
    
    # BM25
    st.subheader("🔍 BM25")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.code("""
AUTO_REBUILD_BM25=true
USE_LOCAL_RERANKER=true
        """, language="bash")
    
    with col2:
        st.markdown("""
        - **AUTO_REBUILD_BM25**: Rebuild auto après ingestion
        - **USE_LOCAL_RERANKER**: Reranking local (cross-encoder)
        """)
    
    st.divider()
    
    # Connexions
    st.subheader("🔗 Services")
    
    st.text(f"RAG Proxy: {RAG_PROXY_URL}")
    st.text(f"Qdrant: {st.session_state.get('qdrant_url', 'http://qdrant:6333')}")
    
    st.divider()
    
    st.info("💡 Redémarrez les services Docker après modification du `.env`")
    
    st.code("""
docker-compose down
docker-compose up -d
    """, language="bash")

# Footer
st.divider()
st.caption(f"Dernière mise à jour: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
