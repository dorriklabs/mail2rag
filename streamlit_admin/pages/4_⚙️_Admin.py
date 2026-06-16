"""
Page 4 : Administration
Rebuild BM25, logs système, configuration
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from utils import load_routing_config, save_routing_config

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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🔨 Index BM25", "📜 Logs Système", "🔧 Configuration", "🔀 Routage Sémantique", "🧠 Prompts IA", "🔒 Règles d'Accès (ACL)"])

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

# =====================================
# TAB 4 : Routage Sémantique
# =====================================
with tab4:
    st.header("🔀 Routage Sémantique IA")
    routing_data = load_routing_config()
    sd_config = routing_data.get("semantic_dispatch", {"enabled": False, "mapping": {}})
    
    st.markdown("L'IA analyse le contenu des emails pour les transférer automatiquement au bon service.")
    
    enabled = st.toggle("Activer le Routage Sémantique", value=sd_config.get("enabled", False))
    
    st.subheader("Configuration des Services")
    mapping = sd_config.get("mapping", {})
    
    df = pd.DataFrame(list(mapping.items()), columns=["Service", "Email"])
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    
    if st.button("💾 Sauvegarder la configuration", type="primary"):
        new_mapping = {}
        for _, row in edited_df.iterrows():
            srv = str(row["Service"]).strip()
            eml = str(row["Email"]).strip()
            if srv and eml and srv != "None" and eml != "None":
                new_mapping[srv] = eml
                
        routing_data["semantic_dispatch"] = {
            "enabled": enabled,
            "mapping": new_mapping
        }
        
        save_routing_config(routing_data)
            
        st.success("✅ Configuration du routage sémantique sauvegardée avec succès !")
        st.rerun()

# =====================================
# TAB 5 : Prompts IA
# =====================================
with tab5:
    from utils import load_workspaces_config, save_workspaces_config
    
    st.header("🧠 Personnalisation des Prompts par Workspace")
    
    st.markdown("""
    Définissez ici des **instructions spécifiques (System Prompts)** pour chaque workspace.
    Lorsque l'utilisateur interroge *uniquement* ce workspace, l'IA obéira à ces règles (ex: ton de la voix, format de réponse, contraintes métier).
    """)
    
    ws_config = load_workspaces_config()
    
    collections_list = get_collections()
    col_names = [c["name"] for c in collections_list] if collections_list else list(ws_config.keys())
    
    # Merge les noms du json avec ceux de Qdrant
    all_workspaces = list(set(col_names + list(ws_config.keys())))
    all_workspaces.sort()
    
    selected_ws = st.selectbox("Sélectionnez le workspace à configurer", all_workspaces)
    
    if selected_ws:
        # Récupérer la config actuelle
        ws_data = ws_config.get(selected_ws, {})
        response_style = ws_data.get("response_style", {})
        current_prompt = response_style.get("custom_prompt", "")
        
        new_prompt = st.text_area(
            "Instructions pour l'IA (System Prompt)",
            value=current_prompt,
            height=250,
            help="Laissez vide pour utiliser le prompt global par défaut du système."
        )
        
        if st.button("💾 Sauvegarder le Prompt"):
            # Initialiser si besoin
            if selected_ws not in ws_config:
                ws_config[selected_ws] = {}
            if "response_style" not in ws_config[selected_ws]:
                ws_config[selected_ws]["response_style"] = {}
                
            # Sauvegarder
            if new_prompt.strip():
                ws_config[selected_ws]["response_style"]["custom_prompt"] = new_prompt.strip()
            else:
                # Remove if empty
                if "custom_prompt" in ws_config[selected_ws]["response_style"]:
                    del ws_config[selected_ws]["response_style"]["custom_prompt"]
                    
            save_workspaces_config(ws_config)
                
            st.success(f"✅ Prompt mis à jour pour le workspace '{selected_ws}' !")
            st.rerun()

# =====================================
# TAB 6 : Règles d'Accès (ACL)
# =====================================
with tab6:
    st.header("🔒 Règles d'Accès (ACL)")
    routing_data = load_routing_config()
    rules_data = routing_data.get("rules", [])
    
    st.markdown("Configurez ici les règles d'accès et de transfert prioritaires pour les emails reçus.")
    
    with st.expander("📖 Guide d'utilisation des règles ACL", expanded=False):
        st.markdown("""
        **Types de règles disponibles :**
        - `sender` : Adresse email exacte (ex: *facturation@fournisseur.com*)
        - `sender_domain` : Domaine de l'expéditeur (ex: *fournisseur.com*)
        - `subject` : Sujet exact de l'email
        - `subject_regex` : Expression régulière pour filtrer le sujet
        - `body_contains` : Mot-clé ou phrase spécifique dans le corps du message
        
        **Configuration des cibles :**
        - **Workspace Cible** : Force le transfert exclusif vers ce workspace (contourne le routage IA).
        - **Workspaces Autorisés** : Restreint l'accès à une liste définie (séparez les noms par des virgules).
        """)
        
    st.divider()
    st.caption(f"📊 **{len(rules_data)}** règle(s) configurée(s) actuellement dans le système.")
    
    # Préparer les données pour le dataframe
    df_data = []
    for rule in rules_data:
        allowed_ws = rule.get("allowed_workspaces", [])
        df_data.append({
            "Type": rule.get("type", ""),
            "Valeur": rule.get("value", ""),
            "Workspace Cible": rule.get("target_workspace", ""),
            "Workspaces Autorisés": ", ".join(allowed_ws) if isinstance(allowed_ws, list) else str(allowed_ws)
        })
        
    df = pd.DataFrame(df_data, columns=["Type", "Valeur", "Workspace Cible", "Workspaces Autorisés"])
    
    # Configuration des colonnes pour le data editor
    column_config = {
        "Type": st.column_config.SelectboxColumn(
            "Type",
            help="Critère de déclenchement",
            width="medium",
            options=["sender", "sender_domain", "subject", "subject_regex", "body_contains"],
            required=True
        ),
        "Valeur": st.column_config.TextColumn(
            "Valeur", 
            help="Valeur à faire correspondre (ex: domaine.com)",
            required=True,
            width="large"
        ),
        "Workspace Cible": st.column_config.TextColumn(
            "Workspace Cible",
            help="Workspace de destination forcée"
        ),
        "Workspaces Autorisés": st.column_config.TextColumn(
            "Workspaces Autorisés", 
            help="Noms des workspaces autorisés séparés par des virgules (ex: ws_finance, ws_direction)",
            width="large"
        )
    }
    
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        column_config=column_config,
        use_container_width=True,
        hide_index=True
    )
    
    st.write("") # Espace visuel
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        save_btn = st.button("💾 Sauvegarder les règles ACL", type="primary", use_container_width=True)
        
    if save_btn:
        new_rules = []
        for _, row in edited_df.iterrows():
            r_type = str(row["Type"]).strip()
            r_val = str(row["Valeur"]).strip()
            r_target = str(row["Workspace Cible"]).strip() if pd.notna(row["Workspace Cible"]) else ""
            r_allowed_str = str(row["Workspaces Autorisés"]).strip() if pd.notna(row["Workspaces Autorisés"]) else ""
            
            # Ignorer les lignes incomplètes (None, nan, vides)
            if r_type and r_type != "None" and r_type != "nan" and r_val and r_val != "None" and r_val != "nan":
                # Traiter les workspaces autorisés
                if r_allowed_str and r_allowed_str != "None" and r_allowed_str != "nan":
                    r_allowed = [ws.strip() for ws in r_allowed_str.split(",") if ws.strip()]
                else:
                    r_allowed = []
                    
                rule_obj = {
                    "type": r_type,
                    "value": r_val,
                    "allowed_workspaces": r_allowed
                }
                if r_target and r_target != "None" and r_target != "nan":
                    rule_obj["target_workspace"] = r_target
                    
                new_rules.append(rule_obj)
                
        # Recharger le fichier pour éviter d'écraser des modifs concurrentes sur semantic_dispatch
        current_data = load_routing_config()
        current_data["rules"] = new_rules
        save_routing_config(current_data)
            
        st.success("✅ Règles ACL sauvegardées avec succès !")
        st.rerun()

