"""
Page 2 : Gestion Documents
Liste, recherche, filtrage et suppression de documents
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestion Documents", page_icon="📄", layout="wide")

RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")
QDRANT_URL = st.session_state.get("qdrant_url", "http://qdrant:6333")

st.title("📄 Gestion des Documents")

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

# Récupérer les documents d'une collection
def get_documents(collection, limit=100):
    try:
        response = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={"limit": limit, "with_payload": True, "with_vector": False},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("result", {}).get("points", [])
        return []
    except Exception as e:
        st.error(f"Erreur: {e}")
        return []

# Supprimer un document
def delete_document(doc_id, collection):
    try:
        response = requests.delete(
            f"{RAG_PROXY_URL}/admin/document/{doc_id}",
            params={"collection": collection},
            timeout=10
        )
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        st.error(f"Erreur suppression: {e}")
        return None

# Sélection de collection
collections = get_collections()

if not collections:
    st.warning("Aucune collection disponible")
    st.stop()

selected_collection = st.selectbox(
    "🗂️ Sélectionner une collection",
    options=collections,
    help="Choisissez la collection à explorer"
)

st.divider()

# Chargement des documents
with st.spinner(f"Chargement des documents de '{selected_collection}'..."):
    documents = get_documents(selected_collection, limit=200)

if not documents:
    st.info("Aucun document dans cette collection")
    st.stop()

st.success(f"✅ {len(documents)} documents chargés")

# Filtres
st.subheader("🔍 Filtres")

col1, col2, col3 = st.columns(3)

with col1:
    search_text = st.text_input(
        "Recherche texte",
        placeholder="Rechercher dans le contenu...",
        help="Recherche dans le texte et les métadonnées"
    )

with col2:
    # Extraire les senders uniques
    senders = set()
    for doc in documents:
        sender = doc.get("payload", {}).get("sender")
        if sender:
            senders.add(sender)
    
    filter_sender = st.selectbox(
        "Filtrer par expéditeur",
        options=["Tous"] + sorted(list(senders)),
    )

with col3:
    # Extraire les dates uniques
    dates = set()
    for doc in documents:
        date = doc.get("payload", {}).get("date")
        if date:
            dates.add(date[:10] if len(date) > 10 else date)
    
    filter_date = st.selectbox(
        "Filtrer par date",
        options=["Toutes"] + sorted(list(dates), reverse=True),
    )

st.divider()

# Appliquer les filtres
filtered_docs = documents

if search_text:
    search_lower = search_text.lower()
    filtered_docs = [
        doc for doc in filtered_docs
        if search_lower in str(doc.get("payload", {})).lower()
    ]

if filter_sender != "Tous":
    filtered_docs = [
        doc for doc in filtered_docs
        if doc.get("payload", {}).get("sender") == filter_sender
    ]

if filter_date != "Toutes":
    filtered_docs = [
        doc for doc in filtered_docs
        if doc.get("payload", {}).get("date", "").startswith(filter_date)
    ]

st.info(f"📊 {len(filtered_docs)} documents après filtrage")

# Affichage des documents
st.subheader("📋 Liste des Documents")

for idx, doc in enumerate(filtered_docs[:50]):  # Limiter à 50 pour performance
    payload = doc.get("payload", {})
    doc_id = doc.get("id", "N/A")
    
    with st.expander(
        f"📄 {payload.get('subject', 'Sans sujet')} - {payload.get('date', 'N/A')}",
        expanded=False
    ):
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Texte:**")
            text_content = payload.get("text", "")
            st.text_area(
                "Contenu",
                value=text_content,
                height=150,
                key=f"text_{idx}",
                disabled=True
            )
            
            st.markdown("**Métadonnées:**")
            metadata_str = "\n".join([
                f"• {k}: {v}"
                for k, v in payload.items()
                if k not in ["text"] and v
            ])
            st.text(metadata_str)
        
        with col2:
            st.markdown(f"**ID:** `{doc_id}`")
            
            # Informations chunk
            chunk_idx = payload.get("chunk_index", "?")
            chunk_total = payload.get("chunk_total", "?")
            st.text(f"Chunk {chunk_idx}/{chunk_total}")
            
            st.divider()
            
            # Bouton suppression
            uid = payload.get("uid")
            if uid and st.button(f"🗑️ Supprimer doc", key=f"del_{idx}", help=f"Supprimer UID: {uid}"):
                with st.spinner("Suppression..."):
                    result = delete_document(uid, selected_collection)
                    if result and result.get("status") == "ok":
                        st.success(f"✅ {result.get('deleted_count', 0)} chunks supprimés")
                        st.rerun()
                    else:
                        st.error(f"❌ Échec: {result.get('message') if result else 'Erreur inconnue'}")

if len(filtered_docs) > 50:
    st.warning(f"⚠️ Affichage limité aux 50 premiers documents ({len(filtered_docs)} total)")

# Statistiques
st.divider()
st.subheader("📊 Statistiques")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Documents totaux", len(documents))

with col2:
    st.metric("Documents filtrés", len(filtered_docs))

with col3:
    unique_uids = len(set(
        doc.get("payload", {}).get("uid")
        for doc in filtered_docs
        if doc.get("payload", {}).get("uid")
    ))
    st.metric("Documents uniques (UID)", unique_uids)
