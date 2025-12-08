"""
Mail2RAG - Admin Dashboard
Interface d'administration Streamlit pour le système RAG
"""

import streamlit as st
import os

# Configuration de la page
st.set_page_config(
    page_title="Mail2RAG Admin",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configuration des URLs depuis variables d'environnement
RAG_PROXY_URL = os.getenv("RAG_PROXY_URL", "http://rag_proxy:8000")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

# Store dans session state
if "rag_proxy_url" not in st.session_state:
    st.session_state.rag_proxy_url = RAG_PROXY_URL
if "qdrant_url" not in st.session_state:
    st.session_state.qdrant_url = QDRANT_URL

# Titre principal
st.title("📧 Mail2RAG - Dashboard Admin")

# Sidebar avec navigation
st.sidebar.title("Navigation")
st.sidebar.markdown("""
Bienvenue sur le dashboard d'administration Mail2RAG.

**Pages disponibles :**
- 📊 **Vue d'ensemble** - Statistiques et graphiques
- 📄 **Documents** - Gestion des documents
- 💬 **Chat RAG** - Interface de recherche
- ⚙️ **Administration** - Configuration et maintenance
""")

# Informations de connexion
st.sidebar.divider()
st.sidebar.subheader("🔗 Services")
st.sidebar.text(f"RAG Proxy: {RAG_PROXY_URL}")
st.sidebar.text(f"Qdrant: {QDRANT_URL}")

# Page d'accueil
st.header("🏠 Accueil")

st.markdown("""
### Bienvenue sur le Dashboard Mail2RAG !

Ce dashboard offre des fonctionnalités avancées :

#### 📊 Vue d'ensemble
- Statistiques globales (documents, collections, taille)
- Graphiques par workspace
- Monitoring temps réel

#### 📄 Gestion Documents
- Liste complète avec filtres
- Recherche full-text
- Suppression et déplacement

#### 💬 Chat RAG
- Interface de recherche intelligente
- Sources citées avec liens
- Paramètres ajustables

#### ⚙️ Administration
- Rebuild index BM25
- Logs système
- Configuration dynamique

---

**🚀 Utilisez le menu latéral pour naviguer entre les pages.**
""")

# Statistics Cards
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="📚 Collections",
        value="...",
        delta="Chargement...",
        help="Nombre total de collections Qdrant"
    )

with col2:
    st.metric(
        label="📄 Documents",
        value="...",
        delta="Chargement...",
        help="Nombre total de documents indexés"
    )

with col3:
    st.metric(
        label="🔍 Index BM25",
        value="...",
        delta="Chargement...",
        help="Statut des index BM25"
    )

st.info("💡 **Tip:** Utilisez les pages dédiées pour des fonctionnalités avancées.")

# Footer
st.divider()
st.caption("Mail2RAG Dashboard v1.0 - Powered by RAG Proxy & Streamlit")
