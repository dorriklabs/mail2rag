import streamlit as st
import yaml
import os
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader

st.set_page_config(page_title="Gestion Utilisateurs", page_icon="👥", layout="wide")

if st.session_state.get("role") != "admin":
    st.error("Accès refusé. Vous devez être administrateur.")
    st.stop()

STATE_DIR = "/state"
USERS_FILE = os.path.join(STATE_DIR, "users.yaml")

def load_config():
    with open(USERS_FILE) as file:
        return yaml.load(file, Loader=SafeLoader)

def save_config(config):
    with open(USERS_FILE, 'w') as file:
        yaml.dump(config, file, default_flow_style=False)

config = load_config()

st.title("👥 Gestion des Utilisateurs")

tab_list, tab_create = st.tabs(["Liste des Utilisateurs", "Créer un Utilisateur"])

with tab_list:
    st.subheader("Utilisateurs existants")
    users = config['credentials'].get('usernames', {})
    
    for username, details in users.items():
        with st.expander(f"👤 {username} ({details.get('role', 'user')})"):
            c1, c2 = st.columns(2)
            c1.text_input("Nom", value=details.get('name', ''), key=f"name_{username}", disabled=True)
            c1.text_input("Email", value=details.get('email', ''), key=f"email_{username}", disabled=True)
            
            new_role = c2.selectbox("Rôle", ["user", "admin"], index=0 if details.get('role', 'user') == 'user' else 1, key=f"role_{username}")
            
            st.markdown("#### Règles (Rules)")
            rules = details.get('rules', {})
            allowed_workspaces = st.text_input("Workspaces autorisés (séparés par virgule)", 
                                             value=",".join(rules.get('allowed_workspaces', [])),
                                             key=f"ws_{username}",
                                             help="Laissez vide pour autoriser tous les workspaces.")
            
            new_pwd = st.text_input("Nouveau mot de passe (laisser vide pour ne pas modifier)", type="password", key=f"pwd_{username}")
            
            col_action1, col_action2 = st.columns([1, 4])
            with col_action1:
                if st.button("💾 Sauvegarder", key=f"save_{username}"):
                    ws_list = [w.strip() for w in allowed_workspaces.split(",") if w.strip()]
                    config['credentials']['usernames'][username]['role'] = new_role
                    if 'rules' not in config['credentials']['usernames'][username]:
                        config['credentials']['usernames'][username]['rules'] = {}
                    config['credentials']['usernames'][username]['rules']['allowed_workspaces'] = ws_list
                    
                    if new_pwd:
                        config['credentials']['usernames'][username]['password'] = stauth.Hasher([new_pwd]).generate()[0]
                    
                    save_config(config)
                    st.success("Modifications sauvegardées !")
                    st.rerun()
            
            with col_action2:
                if username != "admin":
                    if st.button("🗑️ Supprimer", key=f"del_{username}", type="primary"):
                        del config['credentials']['usernames'][username]
                        save_config(config)
                        st.success(f"Utilisateur {username} supprimé !")
                        st.rerun()
                else:
                    st.info("L'administrateur principal ne peut pas être supprimé.")

with tab_create:
    st.subheader("Créer un nouvel utilisateur")
    with st.form("new_user_form"):
        new_username = st.text_input("Identifiant (sans espace)")
        new_name = st.text_input("Nom complet")
        new_email = st.text_input("Email")
        new_password = st.text_input("Mot de passe provisoire", type="password")
        new_role_val = st.selectbox("Rôle", ["user", "admin"])
        
        submit = st.form_submit_button("Créer l'utilisateur")
        
        if submit:
            if not new_username or not new_password or not new_email:
                st.error("L'identifiant, l'email et le mot de passe sont obligatoires.")
            elif new_username in users:
                st.error("Cet identifiant existe déjà.")
            else:
                hashed_pwd = stauth.Hasher([new_password]).generate()[0]
                config['credentials']['usernames'][new_username] = {
                    "email": new_email,
                    "name": new_name,
                    "password": hashed_pwd,
                    "role": new_role_val,
                    "rules": {"allowed_workspaces": []}
                }
                save_config(config)
                st.success(f"Utilisateur {new_username} créé avec succès !")
                st.rerun()
