"""
Page 1 : Vue d'ensemble
Statistiques globales, graphiques et monitoring
"""

import streamlit as st
import requests
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import os

st.set_page_config(page_title="Vue d'ensemble", page_icon="📊", layout="wide")

# URLs depuis session state ou env
RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")
QDRANT_URL = st.session_state.get("qdrant_url", "http://qdrant:6333")
TIKA_URL = os.getenv("TIKA_URL", "http://tika:9998")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://lmstudio:1234")

st.title("📊 Vue d'ensemble")

# Fonctions helper pour les health checks
def get_collections():
    try:
        response = requests.get(f"{RAG_PROXY_URL}/admin/collections", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Erreur connexion RAG Proxy: {e}")
        return None

def get_readyz():
    try:
        response = requests.get(f"{RAG_PROXY_URL}/readyz", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        return None

def check_tika():
    """Vérifie si Tika est accessible."""
    try:
        response = requests.get(f"{TIKA_URL}/tika", timeout=3)
        return response.status_code == 200
    except Exception:
        return False

def check_lm_studio():
    """Vérifie si LM Studio est accessible."""
    try:
        response = requests.get(f"{LM_STUDIO_URL}/v1/models", timeout=3)
        return response.status_code == 200
    except Exception:
        return False

# Récupérer les données
with st.spinner("Chargement des statistiques..."):
    collections_data = get_collections()
    readyz_data = get_readyz()
    tika_ok = check_tika()
    lm_studio_ok = check_lm_studio()

# Statut des services - Ligne 1 : Services Core
st.subheader("🔗 Statut des Services")

col1, col2, col3, col4, col5, col6 = st.columns(6)

if readyz_data:
    deps = readyz_data.get("deps", {})
    
    with col1:
        qdrant_status = "✅ OK" if deps.get("qdrant") else "❌ Erreur"
        st.metric("Qdrant", qdrant_status)
    
    with col2:
        embedder_status = "✅ OK" if deps.get("lm_studio") else "❌ Erreur"
        st.metric("Embeddings", embedder_status)
    
    with col3:
        bm25_status = "✅ OK" if deps.get("bm25") else "⚠️ Non config."
        st.metric("BM25", bm25_status)
    
    with col4:
        tika_status = "✅ OK" if tika_ok else "❌ Erreur"
        st.metric("Tika", tika_status)
    
    with col5:
        lm_status = "✅ OK" if lm_studio_ok else "❌ Erreur"
        st.metric("LM Studio", lm_status)
    
    with col6:
        # Global = tous les services critiques OK
        all_ok = (
            deps.get("qdrant") and 
            deps.get("lm_studio") and 
            tika_ok
        )
        overall_status = "✅ Opérationnel" if all_ok else "⚠️ Partiel"
        st.metric("Global", overall_status)
else:
    st.error("Impossible de récupérer le statut des services")

st.divider()

# Statistiques globales
st.subheader("📈 Statistiques Globales")

if collections_data and collections_data.get("status") == "ok":
    collections = collections_data.get("collections", [])
    total_collections = len(collections)
    total_docs = sum(c.get("qdrant_count", 0) for c in collections)
    bm25_ready_count = sum(1 for c in collections if c.get("bm25_ready"))
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="📚 Collections",
            value=total_collections,
            help="Nombre total de collections Qdrant"
        )
    
    with col2:
        st.metric(
            label="📄 Documents",
            value=f"{total_docs:,}",
            help="Nombre total de documents/chunks indexés"
        )
    
    with col3:
        st.metric(
            label="🔍 Index BM25",
            value=f"{bm25_ready_count}/{total_collections}",
            help="Collections avec index BM25 actif"
        )
    
    with col4:
        avg_docs = total_docs // total_collections if total_collections > 0 else 0
        st.metric(
            label="📊 Moyenne/Collection",
            value=f"{avg_docs:,}",
            help="Nombre moyen de documents par collection"
        )
    
    st.divider()
    
    # Graphiques
    st.subheader("📊 Visualisations")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Graphique en barres : Documents par collection
        if collections:
            fig_bar = go.Figure()
            
            collection_names = [c["name"] for c in collections]
            qdrant_counts = [c.get("qdrant_count", 0) for c in collections]
            
            fig_bar.add_trace(go.Bar(
                x=collection_names,
                y=qdrant_counts,
                marker_color='lightblue',
                text=qdrant_counts,
                textposition='auto',
            ))
            
            fig_bar.update_layout(
                title="Documents par Collection",
                xaxis_title="Collection",
                yaxis_title="Nombre de Documents",
                height=400,
            )
            
            st.plotly_chart(fig_bar, use_container_width=True)
    
    with col2:
        # Graphique en camembert : Distribution des documents
        if collections and total_docs > 0:
            collection_names = [c["name"] for c in collections if c.get("qdrant_count", 0) > 0]
            counts = [c.get("qdrant_count", 0) for c in collections if c.get("qdrant_count", 0) > 0]
            
            fig_pie = go.Figure(data=[go.Pie(
                labels=collection_names,
                values=counts,
                hole=.3,
            )])
            
            fig_pie.update_layout(
                title="Distribution des Documents",
                height=400,
            )
            
            st.plotly_chart(fig_pie, use_container_width=True)
    
    st.divider()
    
    # Tableau des collections
    st.subheader("📑 Détails des Collections")
    
    import pandas as pd
    
    df_data = []
    for c in collections:
        df_data.append({
            "Collection": c["name"],
            "Documents (Qdrant)": c.get("qdrant_count", 0),
            "BM25 Ready": "✅" if c.get("bm25_ready") else "❌",
            "BM25 Count": c.get("bm25_count", 0) if c.get("bm25_ready") else "-",
        })
    
    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
else:
    st.warning("Aucune collection trouvée ou erreur de connexion")
    
    if st.button("🔄 Rafraîchir"):
        st.rerun()

# Informations système
st.divider()
st.subheader("ℹ️ Informations Système")

col1, col2 = st.columns(2)

with col1:
    st.text(f"Mode Multi-Collection: {collections_data.get('multi_collection_mode', 'N/A') if collections_data else 'N/A'}")
    st.text(f"Dernière mise à jour: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

with col2:
    st.text(f"RAG Proxy: {RAG_PROXY_URL}")
    st.text(f"Tika: {TIKA_URL}")
    st.text(f"LM Studio: {LM_STUDIO_URL}")

# Bouton refresh
if st.button("🔄 Rafraîchir les données", use_container_width=True):
    st.rerun()
