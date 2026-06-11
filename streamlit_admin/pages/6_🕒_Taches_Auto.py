import streamlit as st
import requests
import os
import json

st.set_page_config(
    page_title="Tâches Automatisées",
    page_icon="🕒",
    layout="wide"
)

# Constants
RAG_PROXY_URL = os.environ.get("RAG_PROXY_URL", "http://localhost:8000")

# Styles
st.markdown("""
<style>
.task-card {
    background-color: #1e2130;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 20px;
    border: 1px solid #333;
}
.task-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #333;
    padding-bottom: 10px;
    margin-bottom: 15px;
}
.status-active { color: #4CAF50; font-weight: bold; }
.status-inactive { color: #f44336; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🕒 Tâches Automatisées")
st.markdown("Gérez l'exécution en arrière-plan des processus de maintenance (Cron).")

# Fetch config
def get_cron_config():
    try:
        response = requests.get(f"{RAG_PROXY_URL}/admin/cron", timeout=5)
        if response.status_code == 200:
            return response.json().get("config", {})
        else:
            st.error(f"Erreur API: {response.text}")
    except Exception as e:
        st.error(f"Erreur de connexion au proxy: {e}")
    return {}

def update_cron_config(task_name, active, hour, minute):
    try:
        payload = {
            "task_name": task_name,
            "active": active,
            "hour": str(hour).zfill(2),
            "minute": str(minute).zfill(2)
        }
        response = requests.post(f"{RAG_PROXY_URL}/admin/cron", json=payload, timeout=5)
        if response.status_code == 200:
            st.success("Configuration sauvegardée avec succès.")
            return True
        else:
            st.error(f"Erreur lors de la sauvegarde: {response.text}")
    except Exception as e:
        st.error(f"Erreur de connexion: {e}")
    return False

def run_task_now(task_name):
    try:
        response = requests.post(f"{RAG_PROXY_URL}/admin/cron/{task_name}/run", timeout=5)
        if response.status_code == 200:
            st.success("Tâche lancée en arrière-plan.")
        else:
            st.error(f"Erreur de lancement: {response.text}")
    except Exception as e:
        st.error(f"Erreur de connexion: {e}")

config = get_cron_config()

# Task 1: RGPD Purge
st.markdown('<div class="task-card">', unsafe_allow_html=True)
st.markdown('<div class="task-header">', unsafe_allow_html=True)
st.subheader("🗑️ Purge RGPD Automatique")

rgpd_config = config.get("rgpd_purge", {})
is_active = rgpd_config.get("active", False)

if is_active:
    st.markdown('<span class="status-active">● ACTIF</span>', unsafe_allow_html=True)
else:
    st.markdown('<span class="status-inactive">● INACTIF</span>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("""
Cette tâche scanne la base de données vectorielle et les archives physiques pour supprimer les documents dont la durée de conservation a expiré.
""")

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    new_active = st.toggle("Activer la tâche", value=is_active, key="toggle_rgpd")

with col2:
    # Time selection
    current_hour = int(rgpd_config.get("hour", "03"))
    current_minute = int(rgpd_config.get("minute", "00"))
    
    time_col1, time_col2 = st.columns(2)
    with time_col1:
        new_hour = st.selectbox("Heure", options=list(range(24)), index=current_hour, format_func=lambda x: f"{x:02d}h", key="hour_rgpd")
    with time_col2:
        new_minute = st.selectbox("Minute", options=[0, 15, 30, 45], index=[0, 15, 30, 45].index(current_minute) if current_minute in [0, 15, 30, 45] else 0, format_func=lambda x: f"{x:02d}m", key="min_rgpd")

with col3:
    st.write("") # Spacing
    st.write("")
    if st.button("💾 Sauvegarder", key="save_rgpd", use_container_width=True):
        if update_cron_config("rgpd_purge", new_active, new_hour, new_minute):
            st.rerun()

st.markdown("---")
st.markdown("**Actions manuelles**")
if st.button("▶️ Lancer maintenant", key="run_rgpd"):
    run_task_now("rgpd_purge")

st.markdown('</div>', unsafe_allow_html=True)
