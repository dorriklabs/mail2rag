"""
Page 3 : Chat RAG
Interface de recherche et chat avec sources citées
"""

import streamlit as st
import requests
from datetime import datetime

st.set_page_config(page_title="Chat RAG", page_icon="💬", layout="wide")

RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")

st.title("💬 Chat RAG")

# Récupérer les collections
def get_collections():
    try:
        response = requests.get(f"{RAG_PROXY_URL}/admin/collections", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                return [c["name"] for c in data.get("collections", [])]
        return []
    except:
        return []

# Fonction de recherche
def search_rag(query, collection, top_k=10, final_k=5, use_bm25=True):
    try:
        payload = {
            "query": query,
            "workspace": collection,
            "top_k": top_k,
            "final_k": final_k,
            "use_bm25": use_bm25
        }
        response = requests.post(
            f"{RAG_PROXY_URL}/rag",
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Erreur recherche: {e}")
        return None

# Sidebar - Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    collections = get_collections()
    
    if not collections:
        st.error("Aucune collection disponible")
        st.stop()
    
    selected_collection = st.selectbox(
        "Collection",
        options=collections,
        help="Sélectionner la collection pour la recherche"
    )
    
    st.divider()
    
    use_bm25 = st.checkbox(
        "Utiliser BM25",
        value=True,
        help="Activer la recherche hybride (Vector + BM25)"
    )
    
    top_k = st.slider(
        "Top K (récupération)",
        min_value=5,
        max_value=50,
        value=20,
        help="Nombre de documents à récup avant reranking"
    )
    
    final_k = st.slider(
        "Final K (résultats)",
        min_value=1,
        max_value=20,
        value=5,
        help="Nombre de résultats finaux après reranking"
    )
    
    st.divider()
    
    if st.button("🗑️ Effacer l'historique"):
        st.session_state.chat_history = []
        st.rerun()

# Initialiser historique de chat
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Zone de saisie
st.subheader(f"🔍 Recherche dans '{selected_collection}'")

query = st.text_input(
    "Votre question :",
    placeholder="Ex: Comment configurer Mail2RAG ?",
    help="Posez une question pour rechercher dans la base documentaire"
)

col1, col2 = st.columns([1, 4])

with col1:
    search_button = st.button("🔎 Rechercher", use_container_width=True, type="primary")

with col2:
    if st.button("🧹 Nouvelle recherche", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

st.divider()

# Effectuer la recherche
if search_button and query:
    with st.spinner("Recherche en cours..."):
        result = search_rag(
            query=query,
            collection=selected_collection,
            top_k=top_k,
            final_k=final_k,
            use_bm25=use_bm25
        )
        
        if result:
            # Ajouter à l'historique
            st.session_state.chat_history.append({
                "query": query,
                "result": result,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })

# Afficher l'historique (du plus récent au plus ancien)
if st.session_state.chat_history:
    for idx, entry in enumerate(reversed(st.session_state.chat_history)):
        query_text = entry["query"]
        result_data = entry["result"]
        timestamp = entry["timestamp"]
        chunks = result_data.get("chunks", [])
        
        # Question
        st.markdown(f"### 🙋 Question ({timestamp})")
        st.info(query_text)
        
        # Résultats
        st.markdown(f"### 📚 Résultats ({len(chunks)} chunks)")
        
        if not chunks:
            st.warning("Aucun résultat trouvé")
        else:
            # Afficher chaque chunk
            for i, chunk in enumerate(chunks):
                with st.expander(f"📄 Résultat #{i+1} (Score: {chunk.get('score', 0):.2f})", expanded=(i == 0)):
                    text = chunk.get("text", "")
                    metadata = chunk.get("metadata", {})
                    
                    # Afficher le texte
                    st.markdown("**Contenu:**")
                    st.text_area(
                        "Texte",
                        value=text,
                        height=150,
                        key=f"chunk_{idx}_{i}",
                        disabled=True
                    )
                    
                    # Afficher les métadonnées importantes
                    st.markdown("**Source:**")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if metadata.get("subject"):
                            st.text(f"📧 Sujet: {metadata['subject']}")
                        if metadata.get("sender"):
                            st.text(f"👤 Expéditeur: {metadata['sender']}")
                        if metadata.get("date"):
                            st.text(f"📅 Date: {metadata['date']}")
                    
                    with col2:
                        if metadata.get("filename"):
                            st.text(f"📎 Fichier: {metadata['filename']}")
                        if metadata.get("uid"):
                            st.text(f"🔑 UID: {metadata['uid']}")
                        
                        chunk_info = f"{metadata.get('chunk_index', '?')}/{metadata.get('chunk_total', '?')}"
                        st.text(f"📊 Chunk: {chunk_info}")
        
        st.divider()

else:
    st.info("💡 Aucune recherche effectuée. Saisissez une question ci-dessus.")

# Footer
st.caption(f"Paramètres actifs: Top K={top_k}, Final K={final_k}, BM25={'Activé' if use_bm25 else 'Désactivé'}")
