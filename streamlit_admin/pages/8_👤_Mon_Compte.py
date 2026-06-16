import streamlit as st
from utils import load_users_config, save_users_config

st.set_page_config(page_title="Mon Compte", page_icon="👤", layout="centered")

if not st.session_state.get("authentication_status"):
    st.error("Veuillez vous connecter pour accéder à cette page.")
    st.stop()

st.title("👤 Mon Compte")
st.subheader("Modifier mon mot de passe")

authenticator = st.session_state.get("authenticator")

if authenticator:
    try:
        # Le widget reset_password de streamlit_authenticator modifie automatiquement
        # le dictionnaire config['credentials'] qu'on lui a passé à l'initialisation.
        if authenticator.reset_password(st.session_state["username"]):
            st.success("Votre mot de passe a été modifié avec succès.")
            
            # Recharger la config pour récupérer le nouveau hash et le sauvegarder
            config = load_users_config()
            # L'objet authenticator a modifié la config en mémoire
            # On récupère le dict credentials de l'authenticator
            config['credentials'] = authenticator.credentials
            
            save_users_config(config)
    except Exception as e:
        st.error(f"Erreur lors du changement de mot de passe : {e}")
else:
    st.error("L'authentificateur n'a pas pu être chargé.")

st.divider()
st.markdown(f"**Identifiant :** {st.session_state.get('username')}")
st.markdown(f"**Nom complet :** {st.session_state.get('name')}")
st.markdown(f"**Rôle :** {st.session_state.get('role')}")
