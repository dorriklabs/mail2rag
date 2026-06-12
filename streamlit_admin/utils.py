import json
import os
import requests
import streamlit as st

WORKSPACES_CONFIG_FILE = "/etc/mail2rag/workspaces_config.json"

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
    except Exception:
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
