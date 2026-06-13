"""
Mail2RAG - Admin Dashboard
Interface d'administration Streamlit pour le système RAG
"""

import streamlit as st
import os
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
log_path = os.getenv("LOG_PATH", "/var/log/mail2rag/admin.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
file_handler = RotatingFileHandler(
    log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler],
    force=True
)
logging.info("Streamlit Admin Started - Logs Centralisés Activés")

# Configuration de la page (doit être le premier appel Streamlit)
st.set_page_config(
    page_title="Mail2RAG Admin",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configuration des URLs depuis variables d'environnement
RAG_PROXY_URL = os.getenv("RAG_PROXY_URL", "http://rag_proxy:8000")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

if "rag_proxy_url" not in st.session_state:
    st.session_state.rag_proxy_url = RAG_PROXY_URL
if "qdrant_url" not in st.session_state:
    st.session_state.qdrant_url = QDRANT_URL

STATE_DIR = "/state"
USERS_FILE = os.path.join(STATE_DIR, "users.yaml")

def init_users_file():
    if not os.path.exists(STATE_DIR):
        os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        admin_name = os.getenv("ADMIN_NAME", "Admin")
        admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "change_me_securely")
        hashed_pwd = stauth.Hasher.hash(admin_password)
        
        default_config = {
            "credentials": {
                "usernames": {
                    "admin": {
                        "email": admin_email,
                        "name": admin_name,
                        "password": hashed_pwd,
                        "role": "admin",
                        "rules": {"allowed_workspaces": []}
                    }
                }
            },
            "cookie": {
                "expiry_days": 30,
                "key": os.getenv("COOKIE_KEY", "default_secret_key"),
                "name": "mail2rag_dashboard"
            },
            "pre-authorized": {
                "emails": []
            }
        }
        with open(USERS_FILE, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)

init_users_file()

with open(USERS_FILE) as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

def home_page():
    st.title("📧 Mail2RAG - Dashboard")
    st.header("🏠 Accueil")
    st.markdown("""
    ### Bienvenue sur le Dashboard Mail2RAG !
    Ce dashboard offre des fonctionnalités avancées selon votre profil :
    
    #### 💬 Chat RAG & Recherche
    - Interface de recherche intelligente
    - Sources citées avec liens
    
    #### 📄 Gestion Documents & Upload
    - Liste complète avec filtres
    - Importation de nouveaux documents
    """)
    
    if st.session_state.get("role") == "admin":
        st.markdown("""
        #### ⚙️ Administration (Accès Admin)
        - Statistiques globales (Overview)
        - Configuration RAG et système
        - Gestion des tâches automatiques
        - Gestion des utilisateurs
        """)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📚 Collections", "...", "Chargement...")
        with col2:
            st.metric("📄 Documents", "...", "Chargement...")
        with col3:
            st.metric("🔍 Index BM25", "...", "Chargement...")

    st.info("💡 **Tip:** Utilisez le menu latéral pour naviguer entre les pages.")
    st.divider()
    st.caption("Mail2RAG Dashboard v1.0 - Powered by RAG Proxy & Streamlit")


# Stockage de l'authenticator pour accès global (ex: Mon Compte)
st.session_state["authenticator"] = authenticator

# Login widget
authenticator.login(location="main")

if st.session_state["authentication_status"]:
    st.sidebar.write(f"Bienvenue **{st.session_state['name']}**")
    authenticator.logout('Déconnexion', 'sidebar')
    
    # Store user role and rules in session
    username = st.session_state["username"]
    role = config['credentials']['usernames'].get(username, {}).get('role', 'user')
    rules = config['credentials']['usernames'].get(username, {}).get('rules', {})
    st.session_state["role"] = role
    st.session_state["user_rules"] = rules

    st.sidebar.divider()
    st.sidebar.subheader("🔗 Services")
    st.sidebar.text(f"RAG Proxy: {RAG_PROXY_URL}")
    st.sidebar.text(f"Qdrant: {QDRANT_URL}")

    # Définition des pages
    p_home = st.Page(home_page, title="Accueil", icon="🏠", default=True)
    p_overview = st.Page("pages/1_📊_Overview.py", title="Overview", icon="📊")
    p_documents = st.Page("pages/2_📄_Documents.py", title="Documents", icon="📄")
    p_chat = st.Page("pages/3_💬_Chat.py", title="Chat RAG", icon="💬")
    p_admin = st.Page("pages/4_⚙️_Admin.py", title="Administration", icon="⚙️")
    p_upload = st.Page("pages/5_📤_Upload.py", title="Upload", icon="📤")
    p_taches = st.Page("pages/6_🕒_Taches_Auto.py", title="Tâches Auto", icon="🕒")
    p_users = st.Page("pages/7_👥_Utilisateurs.py", title="Utilisateurs", icon="👥")
    p_compte = st.Page("pages/8_👤_Mon_Compte.py", title="Mon Compte", icon="👤")
    p_audit = st.Page("pages/9_📊_Audit.py", title="Journal d'Audit", icon="📊")

    # Routing
    if role == "admin":
        pg = st.navigation({
            "Principal": [p_home, p_documents, p_chat, p_upload],
            "Mon Profil": [p_compte],
            "Administration": [p_overview, p_admin, p_taches, p_users, p_audit]
        })
    else:
        pg = st.navigation({
            "Principal": [p_home, p_documents, p_chat, p_upload],
            "Mon Profil": [p_compte]
        })
        
    pg.run()

elif st.session_state["authentication_status"] is False:
    st.error('Nom d\'utilisateur ou mot de passe incorrect')
elif st.session_state["authentication_status"] is None:
    st.warning('Veuillez vous connecter pour accéder au dashboard')
