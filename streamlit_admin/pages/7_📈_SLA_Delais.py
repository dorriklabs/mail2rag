import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="SLA & Délais de Réponse", page_icon="📈", layout="wide")

st.title("📈 Suivi SLA & Délais de Réponse")
st.markdown("Ce tableau de bord mesure le délai entre le transfert d'un e-mail par l'IA et la réponse de l'agent métier au citoyen.")

STATE_PATH = os.environ.get("STATE_PATH", "/state/state.json")
DB_PATH = os.path.join(os.path.dirname(STATE_PATH), "sla_tracker.db")

def get_db_connection():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)

def load_data():
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    query = "SELECT thread_id, sender, subject, target_service, dispatched_at, replied_at, response_time_hours, status FROM dispatch_sla ORDER BY dispatched_at DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Convert dates
    df['dispatched_at'] = pd.to_datetime(df['dispatched_at'])
    df['replied_at'] = pd.to_datetime(df['replied_at'])
    return df

df = load_data()

if df.empty:
    st.info("Aucune donnée SLA disponible pour le moment. La base de données est peut-être vide ou en cours de création.")
    st.stop()

# KPIs (Métriques Clés)
col1, col2, col3 = st.columns(3)

pending_df = df[df['status'] == 'PENDING'].copy()
replied_df = df[df['status'] == 'REPLIED'].copy()

# Recalculer l'âge en heures pour les Pending
now = datetime.utcnow()
if not pending_df.empty:
    pending_df['current_delay_hours'] = (now - pending_df['dispatched_at']).dt.total_seconds() / 3600.0
else:
    pending_df['current_delay_hours'] = []

total_pending = len(pending_df)
avg_response_time = replied_df['response_time_hours'].mean() if not replied_df.empty else 0
# Nombre de pending > 48h
critical_pending = len(pending_df[pending_df['current_delay_hours'] > 48])

with col1:
    st.metric("E-mails en attente de réponse", total_pending)
with col2:
    st.metric("Temps de réponse moyen (Global)", f"{avg_response_time:.1f} h" if avg_response_time else "N/A")
with col3:
    st.metric("Demandes critiques (>48h)", critical_pending, delta_color="inverse")

st.divider()

# Onglets
tab1, tab2 = st.tabs(["🔴 En Souffrance (PENDING)", "🟢 Historique (REPLIED)"])

with tab1:
    st.subheader("Dossiers en attente de réponse")
    
    if pending_df.empty:
        st.success("Bravo ! Aucun e-mail n'est en attente de réponse.")
    else:
        # Filtre par service
        services = ["Tous"] + sorted(pending_df['target_service'].unique().tolist())
        selected_service = st.selectbox("Filtrer par service", services, key="pending_service_filter")
        
        filtered_pending = pending_df if selected_service == "Tous" else pending_df[pending_df['target_service'] == selected_service]
        
        # Format pour affichage
        display_df = filtered_pending[['dispatched_at', 'target_service', 'sender', 'subject', 'current_delay_hours']].copy()
        display_df = display_df.sort_values(by='current_delay_hours', ascending=False)
        display_df['dispatched_at'] = display_df['dispatched_at'].dt.strftime('%d/%m/%Y %H:%M')
        display_df['current_delay_hours'] = display_df['current_delay_hours'].round(1).astype(str) + " h"
        
        # Fonction pour appliquer les couleurs
        def color_delay(val):
            try:
                hours = float(val.replace(" h", ""))
                if hours > 72:
                    return 'background-color: #ffcccc'
                elif hours > 48:
                    return 'background-color: #ffebcc'
                return ''
            except:
                return ''
                
        styled_df = display_df.style.applymap(color_delay, subset=['current_delay_hours'])
        
        st.dataframe(
            styled_df,
            column_config={
                "dispatched_at": "Transféré le",
                "target_service": "Service",
                "sender": "Citoyen",
                "subject": "Sujet",
                "current_delay_hours": "En attente depuis"
            },
            use_container_width=True,
            hide_index=True
        )

with tab2:
    st.subheader("Historique des réponses")
    
    if replied_df.empty:
        st.info("Aucune réponse n'a encore été enregistrée.")
    else:
        # Temps moyen par service
        st.markdown("**Temps de réponse moyen par service**")
        stats_df = replied_df.groupby('target_service')['response_time_hours'].mean().reset_index()
        stats_df['response_time_hours'] = stats_df['response_time_hours'].round(1).astype(str) + " h"
        st.dataframe(stats_df, column_config={"target_service": "Service", "response_time_hours": "Moyenne"}, hide_index=True)
        
        st.markdown("**Détail des réponses**")
        display_rep = replied_df[['dispatched_at', 'replied_at', 'target_service', 'sender', 'response_time_hours']].copy()
        display_rep = display_rep.sort_values(by='replied_at', ascending=False).head(100)
        
        display_rep['dispatched_at'] = display_rep['dispatched_at'].dt.strftime('%d/%m/%Y %H:%M')
        display_rep['replied_at'] = display_rep['replied_at'].dt.strftime('%d/%m/%Y %H:%M')
        display_rep['response_time_hours'] = display_rep['response_time_hours'].round(1).astype(str) + " h"
        
        st.dataframe(
            display_rep,
            column_config={
                "dispatched_at": "Arrivé le",
                "replied_at": "Répondu le",
                "target_service": "Service",
                "sender": "Citoyen",
                "response_time_hours": "Délai"
            },
            use_container_width=True,
            hide_index=True
        )
