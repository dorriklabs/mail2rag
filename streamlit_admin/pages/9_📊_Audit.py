import streamlit as st
import json
import pandas as pd
import os

st.set_page_config(page_title="Journal d'Audit", page_icon="📊", layout="wide")

if st.session_state.get("role") != "admin":
    st.error("Accès refusé. Vous devez être administrateur.")
    st.stop()

st.title("📊 Journal d'Audit")
st.markdown("Suivi en temps réel des requêtes effectuées sur le RAG (Dashboard et Email).")

AUDIT_FILE = "/state/audit.jsonl"

def load_audit_logs():
    logs = []
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        except Exception as e:
            st.error(f"Erreur lors de la lecture des logs: {e}")
    return logs

logs = load_audit_logs()

if not logs:
    st.info("Aucun log d'audit disponible pour le moment.")
else:
    # Convertir en DataFrame pour l'affichage et le filtrage
    df = pd.DataFrame(logs)
    
    # Formater la date
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['Date'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        df['Date'] = "Inconnue"
        
    # Renommer les colonnes pour un affichage plus propre
    display_df = df[['Date', 'source', 'user', 'workspaces', 'query']].copy()
    display_df.columns = ['Date', 'Source', 'Utilisateur', 'Workspaces', 'Requête']
    
    # Trier par date décroissante
    display_df = display_df.sort_values(by='Date', ascending=False).reset_index(drop=True)
    
    # Filtres
    col1, col2 = st.columns(2)
    with col1:
        sources = ["Toutes"] + list(display_df['Source'].unique())
        selected_source = st.selectbox("Filtrer par Source", sources)
    with col2:
        users = ["Tous"] + list(display_df['Utilisateur'].unique())
        selected_user = st.selectbox("Filtrer par Utilisateur", users)
        
    # Appliquer les filtres
    filtered_df = display_df.copy()
    if selected_source != "Toutes":
        filtered_df = filtered_df[filtered_df['Source'] == selected_source]
    if selected_user != "Tous":
        filtered_df = filtered_df[filtered_df['Utilisateur'] == selected_user]
        
    st.metric("Nombre de requêtes", len(filtered_df))
    
    # Affichage interactif
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True
    )
    
    st.divider()
    if st.button("🗑️ Vider le journal d'audit", type="primary"):
        try:
            open(AUDIT_FILE, "w").close()
            st.success("Journal d'audit vidé avec succès.")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur lors du nettoyage du journal: {e}")
