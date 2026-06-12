"""
Page 3 : Chat RAG
Interface de recherche et chat avec sources citées
"""

import streamlit as st
import requests
import os
from datetime import datetime
from utils import get_filtered_collections, load_workspaces_config, log_audit_event, fix_encoding

st.set_page_config(page_title="Chat RAG", page_icon="💬", layout="wide")

RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234")

col1, col2 = st.columns([8, 2])
with col1:
    st.title("💬 Chat RAG")
with col2:
    st.write("") # Spacer
    if st.button("➕ Nouvelle discussion", use_container_width=True, type="primary"):
        st.session_state.chat_history = []
        st.rerun()

# Fonction pour résumer l'historique ancien
def summarize_history(exchanges, max_summary_chars=500):
    if not exchanges:
        return None
    
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
                        "content": f"Résume cette conversation précédente en 2-3 phrases maximum, en conservant les informations clés (noms, chiffres, dates) :\n\n{exchanges_text}\n\nRésumé concis :"
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

# Fonction de chat avec génération IA
def chat_rag(query, collection, top_k=10, final_k=5, use_bm25=True, temperature=0.1, history=None, system_prompt=None):
    try:
        payload = {
            "query": query,
            "collection": collection,
            "top_k": top_k,
            "final_k": final_k,
            "use_bm25": use_bm25,
            "temperature": temperature,
        }
        if history:
            payload["history"] = history
        if system_prompt:
            payload["system_prompt"] = system_prompt
        
        response = requests.post(
            f"{RAG_PROXY_URL}/chat",
            json=payload,
            timeout=120
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
    
    collections = get_filtered_collections(RAG_PROXY_URL)
    
    if not collections:
        st.error("Aucune collection disponible")
        st.stop()
    
    selected_collections = st.multiselect(
        "Collections",
        options=collections,
        default=collections,
        help="Sélectionner la ou les collections pour la recherche"
    )
    
    if not selected_collections:
        st.warning("Veuillez sélectionner au moins une collection.")
        st.stop()
        
    selected_collection = ",".join(selected_collections)
    
    custom_system_prompt = None
    if len(selected_collections) == 1:
        try:
            ws_config = load_workspaces_config()
            ws_data = ws_config.get(selected_collections[0], {})
            response_style = ws_data.get("response_style", {})
            custom_system_prompt = response_style.get("custom_prompt", None)
        except Exception:
            pass
    
    st.divider()
    
    use_bm25 = True
    
    top_k = st.slider(
        "Top K (récupération)",
        min_value=5,
        max_value=50,
        value=20,
        help="Nombre de documents à récupérer avant reranking"
    )
    final_k = 10
    temperature = 0.1
    
    use_history = st.checkbox(
        "💬 Mémoire conversation",
        value=True,
        help="Inclure les échanges précédents comme contexte"
    )
    
    if use_history:
        history_depth = st.slider(
            "Profondeur historique",
            min_value=1,
            max_value=10,
            value=3,
            help="Nombre d'échanges à considérer"
        )
    else:
        history_depth = 0

# Initialiser historique de chat
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
else:
    # Si l'historique contient l'ancien format (query/result), on l'efface
    if st.session_state.chat_history and "role" not in st.session_state.chat_history[0]:
        st.session_state.chat_history = []

@st.dialog("📖 Aperçu de l'extrait", width="large")
def show_source_modal(filename, text, chunk_index, chunk_total, file_link):
    st.markdown(f"**Document :** {filename} (Extrait {chunk_index + 1}/{chunk_total})")
    
    formatted_text = fix_encoding(text)
    if chunk_total > 1:
        if chunk_index > 0:
            formatted_text = "*(...)*\n\n" + formatted_text
        if chunk_index < chunk_total - 1:
            formatted_text = formatted_text + "\n\n*(...)*"
            
    st.info(formatted_text)
    
    if file_link:
        st.markdown(f"[🔗 Ouvrir le document original]({file_link})")

# Afficher l'historique
if not st.session_state.chat_history:
    st.info(f"💡 Posez votre question ci-dessous pour rechercher dans '{selected_collection}'.")

for msg_idx, message in enumerate(st.session_state.chat_history):
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])
    elif message["role"] == "assistant":
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(message["content"])
            
            result_data = message.get("result_data", {})
            sources = result_data.get("sources", [])
            debug_info = result_data.get("debug_info", {})
            
            if debug_info:
                with st.expander("📊 Informations de génération", expanded=False):
                    if debug_info.get('cache_hit'):
                        st.success("⚡ Réponse servie instantanément depuis le Cache Sémantique !")
                        if 'score' in debug_info:
                            st.metric("Score de similarité", f"{debug_info['score']:.3f}")
                    else:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Chunks", f"{debug_info.get('chunks_used', '?')}/{debug_info.get('chunks_retrieved', '?')}")
                            
                            usage = debug_info.get('usage', {})
                            prompt_tokens = usage.get('prompt_tokens') or debug_info.get('context_tokens', '?')
                            max_ctx = debug_info.get('max_context', '?')
                            st.metric("Contexte utilisé", f"{prompt_tokens} / {max_ctx} tokens")
                            
                        with col2:
                            speed = debug_info.get('tokens_per_sec', '?')
                            st.metric("Vitesse (LLM)", f"{speed} t/s")
                            
                            duration = debug_info.get('llm_duration', '?')
                            st.metric("Temps (LLM)", f"{duration}s")
                            
                        with col3:
                            gen_tokens = usage.get('completion_tokens', '?')
                            st.metric("Tokens générés", str(gen_tokens))
            
            if sources:
                with st.expander(f"📚 Sources ({len(sources)})", expanded=False):
                    from collections import defaultdict
                    grouped_sources = defaultdict(list)
                    for i, source in enumerate(sources):
                        collection_name = source.get("metadata", {}).get("collection", "Général")
                        grouped_sources[collection_name].append((i, source))
                    
                    for collection_name, group in grouped_sources.items():
                        st.markdown(f"**{collection_name} :**")
                        for i, source in group:
                            metadata = source.get("metadata", {})
                            score = source.get("score", 0)
                            filename = metadata.get("filename", "Document")
                            text = source.get("text", "")
                            fixed_text = fix_encoding(text)
                            
                            if fixed_text and len(fixed_text) > 50:
                                preview = fixed_text[:25].strip() + "..." + fixed_text[-25:].strip()
                                preview = preview.replace('"', "'").replace('\n', ' ')
                            elif fixed_text:
                                preview = fixed_text.replace('"', "'").replace('\n', ' ')
                            else:
                                preview = "Aperçu non disponible"
                            
                            chunk_index = metadata.get("chunk_index", 0)
                            chunk_total = metadata.get("chunk_total", 1)
                            if chunk_total > 0:
                                position = int((chunk_index / chunk_total) * 5)
                                position = min(position, 4)
                                indicator = "[" + "-" * position + "#" + "-" * (4 - position) + "]"
                            else:
                                indicator = "[--#--]"
                            
                            file_link = (metadata.get("link") or 
                                        metadata.get("url") or 
                                        metadata.get("archive_url") or
                                        metadata.get("source_url"))
                                        
                            if not file_link:
                                secure_id = metadata.get("secure_id")
                                if secure_id:
                                    archive_base = os.getenv("ARCHIVE_BASE_URL", "http://localhost:9102")
                                    file_link = f"{archive_base}/{secure_id}/{filename}"
                            
                            indicator_html = f'<span title="{preview}" style="cursor:help;">{indicator}</span>'
                            
                            col_src, col_btn = st.columns([8, 2])
                            with col_src:
                                if file_link:
                                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;**#{i+1}** ({score:.2f}) {indicator_html} [{filename}]({file_link})", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;**#{i+1}** ({score:.2f}) {indicator_html} {filename}", unsafe_allow_html=True)
                            with col_btn:
                                if st.button("👁️ Lire", key=f"src_btn_{msg_idx}_{i}"):
                                    show_source_modal(filename, text, chunk_index, chunk_total, file_link)

# Input
if prompt := st.chat_input("Votre question..."):
    # Afficher la bulle utilisateur
    with st.chat_message("user"):
        st.markdown(prompt)
    
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    
    # Construire history_to_send pour l'API
    history_to_send = None
    if use_history and history_depth > 0:
        # Extraire les paires utilisateur/assistant précédentes
        pairs = []
        current_query = None
        for m in st.session_state.chat_history[:-1]: # Exclure la question actuelle
            if m["role"] == "user":
                current_query = m["content"]
            elif m["role"] == "assistant" and current_query:
                pairs.append({"query": current_query, "answer": m["content"]})
                current_query = None
                
        if pairs:
            RECENT_FULL = 2
            formatted_history = []
            
            if len(pairs) > RECENT_FULL:
                old_pairs = pairs[:-RECENT_FULL]
                recent_pairs = pairs[-RECENT_FULL:]
                
                # Resumer au max history_depth
                old_for_summary = old_pairs[-history_depth:]
                summary = summarize_history(old_for_summary)
                if summary:
                    formatted_history.append({"role": "system", "content": f"[Résumé conversation: {summary}]"})
            else:
                recent_pairs = pairs[-history_depth:]
                
            for p in recent_pairs:
                formatted_history.append({"role": "user", "content": p["query"]})
                formatted_history.append({"role": "assistant", "content": p["answer"]})
                
            history_to_send = formatted_history

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Recherche et réflexion..."):
            result = chat_rag(
                query=prompt,
                collection=selected_collection,
                top_k=top_k,
                final_k=final_k,
                use_bm25=use_bm25,
                temperature=temperature,
                history=history_to_send,
                system_prompt=custom_system_prompt
            )
            
            if result:
                log_audit_event(
                    user=st.session_state.get("username", "Unknown"),
                    source="Dashboard",
                    workspaces=selected_collection,
                    query=prompt
                )
                
                answer = result.get("answer", "")
                st.markdown(answer)
                
                st.session_state.chat_history.append({
                    "role": "assistant", 
                    "content": answer,
                    "result_data": result,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                st.rerun()
