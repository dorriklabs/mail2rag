"""
Page 3 : Chat RAG
Interface de recherche et chat avec sources citées
"""

import streamlit as st
import requests
import os
from datetime import datetime

st.set_page_config(page_title="Chat RAG", page_icon="💬", layout="wide")

RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234")

st.title("💬 Chat RAG")

# Fonction pour résumer l'historique ancien
def summarize_history(exchanges, max_summary_chars=500):
    """
    Résume les échanges anciens en un texte court via le LLM.
    
    Args:
        exchanges: Liste de dicts avec 'query' et 'answer'
        max_summary_chars: Longueur max du résumé
        
    Returns:
        Un message système contenant le résumé
    """
    if not exchanges:
        return None
    
    # Construire le texte des échanges à résumer
    exchanges_text = "\n".join([
        f"Q: {e['query']}\nR: {e.get('answer', 'N/A')[:200]}..."
        for e in exchanges
    ])
    
    try:
        response = requests.post(
            f"{LM_STUDIO_URL}/v1/chat/completions",
            json={
                "model": "default",
                "messages": [
                    {
                        "role": "system",
                        "content": "Tu es un assistant qui résume des conversations. Sois très concis."
                    },
                    {
                        "role": "user",
                        "content": f"""Résume cette conversation précédente en 2-3 phrases maximum, en conservant les informations clés (noms, chiffres, dates) :

{exchanges_text}

Résumé concis :"""
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=30,
        )
        
        if response.status_code == 200:
            summary = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            return summary[:max_summary_chars] if summary else None
        return None
    except Exception as e:
        st.warning(f"Résumé historique impossible: {e}")
        return None

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

# Fonction de chat avec génération IA
def chat_rag(query, collection, top_k=10, final_k=5, use_bm25=True, temperature=0.1, history=None):
    try:
        payload = {
            "query": query,
            "collection": collection,
            "top_k": top_k,
            "final_k": final_k,
            "use_bm25": use_bm25,
            "temperature": temperature,
        }
        # Ajouter l'historique si fourni
        if history:
            payload["history"] = history
        
        response = requests.post(
            f"{RAG_PROXY_URL}/chat",
            json=payload,
            timeout=120  # Plus long car génération LLM
        )
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Erreur API: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Erreur chat: {e}")
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
    
    # BM25 toujours activé (recherche hybride)
    use_bm25 = True
    
    top_k = st.slider(
        "Top K (récupération)",
        min_value=5,
        max_value=50,
        value=20,
        help="Nombre de documents à récupérer avant reranking"
    )
    
    # Valeur fixe - le système ajuste automatiquement selon le contexte LLM
    final_k = 10
    
    # Température fixe optimale pour RAG (précision maximale)
    temperature = 0.1
    
    # Toggle Mémoire conversationnelle
    use_history = st.checkbox(
        "💬 Mémoire conversation",
        value=False,
        help="Inclure les échanges précédents comme contexte (désactivé par défaut)"
    )
    
    if use_history:
        history_depth = st.slider(
            "Profondeur historique",
            min_value=1,
            max_value=10,
            value=3,
            help="Nombre d'échanges à considérer (anciens résumés automatiquement)"
        )
    else:
        history_depth = 0
    
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
    with st.spinner("🤖 Génération de la réponse IA..."):
        # Construire l'historique si activé
        history_to_send = None
        if use_history and history_depth > 0 and st.session_state.chat_history:
            # Filtrer les échanges
            chat_entries = [
                entry for entry in st.session_state.chat_history
            ]
            
            if chat_entries:
                # Stratégie : résumer les anciens, garder les 2 derniers en entier
                RECENT_FULL = 2  # Nombre d'échanges récents à garder en entier
                
                if len(chat_entries) > RECENT_FULL:
                    # Séparer anciens et récents
                    old_entries = chat_entries[:-RECENT_FULL]
                    recent_entries = chat_entries[-RECENT_FULL:]
                    
                    # Résumer les anciens
                    old_for_summary = [
                        {
                            "query": e["query"],
                            "answer": e.get("result", {}).get("answer", "")
                        }
                        for e in old_entries[-history_depth:]  # Limiter au depth demandé
                    ]
                    
                    summary = summarize_history(old_for_summary)
                    
                    # Construire l'historique avec résumé + récents
                    formatted_history = []
                    
                    if summary:
                        # Ajouter le résumé comme contexte système
                        formatted_history.append({
                            "role": "system",
                            "content": f"[Résumé de la conversation précédente: {summary}]"
                        })
                    
                    # Ajouter les échanges récents en entier
                    for e in recent_entries:
                        formatted_history.append({"role": "user", "content": e["query"]})
                        answer = e.get("result", {}).get("answer", "")
                        if answer:
                            formatted_history.append({"role": "assistant", "content": answer})
                    
                    history_to_send = formatted_history
                else:
                    # Peu d'historique, garder tout en entier
                    formatted_history = []
                    for e in chat_entries[-history_depth:]:
                        formatted_history.append({"role": "user", "content": e["query"]})
                        answer = e.get("result", {}).get("answer", "")
                        if answer:
                            formatted_history.append({"role": "assistant", "content": answer})
                    history_to_send = formatted_history
        
        # Appel Chat IA
        result = chat_rag(
            query=query,
            collection=selected_collection,
            top_k=top_k,
            final_k=final_k,
            use_bm25=use_bm25,
            temperature=temperature,
            history=history_to_send
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
        
        # Question
        st.markdown(f"### 🙋 Question ({timestamp})")
        st.info(query_text)
        
        # Réponse IA
        answer = result_data.get("answer", "")
        sources = result_data.get("sources", [])
        debug_info = result_data.get("debug_info", {})
        
        st.markdown("### 🤖 Réponse IA")
        st.success(answer)
        
        # Debug info
        if debug_info:
            with st.expander("📊 Informations de génération", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Chunks utilisés", f"{debug_info.get('chunks_used', '?')}/{debug_info.get('chunks_retrieved', '?')}")
                with col2:
                    st.metric("Tokens contexte", debug_info.get('context_tokens', '?'))
                with col3:
                    st.metric("Modèle", debug_info.get('llm_model', '?'))
        
        # Sources - Affichage compact dans un accordéon
        if sources:
            with st.expander(f"📚 Sources ({len(sources)})", expanded=False):
                for i, source in enumerate(sources):
                    metadata = source.get("metadata", {})
                    score = source.get("score", 0)
                    filename = metadata.get("filename", "Document")
                    text = source.get("text", "")
                    
                    # Créer un aperçu du chunk (début...fin)
                    if text and len(text) > 50:
                        preview = text[:25].strip() + "..." + text[-25:].strip()
                        preview = preview.replace('"', "'").replace('\n', ' ')
                    elif text:
                        preview = text.replace('"', "'").replace('\n', ' ')
                    else:
                        preview = "Aperçu non disponible"
                    
                    # Calcul de l'indicateur de position [----#]
                    chunk_index = metadata.get("chunk_index", 0)
                    chunk_total = metadata.get("chunk_total", 1)
                    if chunk_total > 0:
                        position = int((chunk_index / chunk_total) * 5)
                        position = min(position, 4)  # Max 4 (index 0-4 pour 5 positions)
                        indicator = "[" + "-" * position + "#" + "-" * (4 - position) + "]"
                    else:
                        indicator = "[--#--]"
                    
                    # Construire le lien
                    file_link = (metadata.get("link") or 
                                metadata.get("url") or 
                                metadata.get("archive_url") or
                                metadata.get("source_url"))
                    
                    # Format: #1 (0.85) [--#--] filename.txt avec tooltip sur l'indicateur
                    indicator_html = f'<span title="{preview}" style="cursor:help;">{indicator}</span>'
                    if file_link:
                        st.markdown(f"**#{i+1}** ({score:.2f}) {indicator_html} [{filename}]({file_link})", unsafe_allow_html=True)
                    else:
                        st.markdown(f"**#{i+1}** ({score:.2f}) {indicator_html} {filename}", unsafe_allow_html=True)
        
        st.divider()

else:
    st.info("💡 Aucune recherche effectuée. Saisissez une question ci-dessus.")

# Footer
st.caption(f"Top K={top_k}")
