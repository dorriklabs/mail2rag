"""
Page 1 : Vue d'ensemble
Statistiques globales, graphiques et monitoring
"""

import streamlit as st
import requests
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Vue d'ensemble", page_icon="📊", layout="wide")

# URLs depuis session state
RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")
QDRANT_URL = st.session_state.get("qdrant_url", "http://qdrant:6333")

st.title("📊 Vue d'ensemble")

# Fonction helper pour appeler RAG Proxy
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

# Récupérer les données
with st.spinner("Chargement des statistiques..."):
    collections_data = get_collections()
    readyz_data = get_readyz()

# Statut des services
st.subheader("🔗 Statut des Services")
col1, col2, col3, col4 = st.columns(4)

if readyz_data:
    deps = readyz_data.get("deps", {})
    
    with col1:
        qdrant_status = "✅ OK" if deps.get("qdrant") else "❌ Erreur"
        st.metric("Qdrant", qdrant_status)
    
    with col2:
        embedder_status = "✅ OK" if deps.get("embedder") else "❌ Erreur"
        st.metric("Embeddings", embedder_status)
    
    with col3:
        bm25_status = "✅ OK" if deps.get("bm25") else "⚠️ Non configuré"
        st.metric("BM25", bm25_status)
    
    with col4:
        overall_status = "✅ Opérationnel" if readyz_data.get("ready") else "❌ Problème"
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
    st.text(f"Mode Multi-Collection: {collections_data.get('multi_collection_mode', 'N/A')}")
    st.text(f"Dernière mise à jour: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

with col2:
    st.text(f"RAG Proxy URL: {RAG_PROXY_URL}")
    st.text(f"Qdrant URL: {QDRANT_URL}")

# Bouton refresh
if st.button("🔄 Rafraîchir les données", use_container_width=True):
    st.rerun()
