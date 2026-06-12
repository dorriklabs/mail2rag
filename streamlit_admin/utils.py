import json
import os
import requests
import streamlit as st

WORKSPACES_CONFIG_FILE = "/etc/mail2rag/workspaces_config.json"

def fix_encoding(text):
    """Corrige les problèmes de décodage (Mojibake) où l'UTF-8 a été lu comme du Latin-1."""
    if not isinstance(text, str):
        return text
    try:
        if "Ã" in text:
            return text.encode('latin1').decode('utf-8')
    except Exception:
        pass
    return text

def get_filtered_collections(rag_proxy_url: str):
    """Récupère les collections depuis le backend et les filtre selon les droits de l'utilisateur (ACL)."""
    try:
        response = requests.get(f"{rag_proxy_url}/admin/collections", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                all_cols = [c["name"] for c in data.get("collections", [])]
                
                role = st.session_state.get("role", "user")
                rules = st.session_state.get("user_rules", {})
                allowed = rules.get("allowed_workspaces", [])
                
                if role == "admin" and not allowed:
                    return all_cols
                if "*" in allowed:
                    return all_cols
                    
                return [c for c in all_cols if c in allowed]
        return []
    except Exception as e:
        import traceback
        st.sidebar.error(f"Erreur get_filtered_collections: {e}\n{traceback.format_exc()}")
        return []

def load_workspaces_config():
    """Charge la configuration des workspaces depuis le fichier JSON."""
    if os.path.exists(WORKSPACES_CONFIG_FILE):
        try:
            with open(WORKSPACES_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_workspaces_config(config):
    """Sauvegarde la configuration des workspaces."""
    with open(WORKSPACES_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

import yaml
from yaml.loader import SafeLoader
from datetime import datetime

STATE_DIR = "/state"
USERS_FILE = os.path.join(STATE_DIR, "users.yaml")
AUDIT_FILE = os.path.join(STATE_DIR, "audit.jsonl")

def load_users_config():
    """Charge la configuration des utilisateurs."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as file:
            return yaml.load(file, Loader=SafeLoader)
    return {}

def save_users_config(config):
    """Sauvegarde la configuration des utilisateurs."""
    with open(USERS_FILE, 'w') as file:
        yaml.dump(config, file, default_flow_style=False)

def log_audit_event(user: str, source: str, query: str, workspaces: str):
    """Enregistre un événement dans le journal d'audit."""
    try:
        if not os.path.exists(STATE_DIR):
            os.makedirs(STATE_DIR, exist_ok=True)
            
        event = {
            "timestamp": datetime.now().isoformat(),
            "user": user,
            "source": source,
            "workspaces": workspaces,
            "query": query
        }
        
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Erreur d'écriture dans le log d'audit: {e}")
