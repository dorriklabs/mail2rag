"""
Page 5 : Upload de fichiers
Permet l'upload direct de documents textes dans une collection.
"""

import streamlit as st
import requests
import os
from datetime import datetime
from utils import get_filtered_collections

st.set_page_config(page_title="Upload", page_icon="📤", layout="wide")

RAG_PROXY_URL = st.session_state.get("rag_proxy_url", "http://rag_proxy:8000")
TIKA_URL = os.environ.get("TIKA_URL", "http://tika:9998")

st.title("📤 Upload de Documents")

st.markdown("""
Cette page permet d'ajouter manuellement des documents textes volumineux 
directement dans le système RAG.
""")

collections = get_filtered_collections(RAG_PROXY_URL)
role = st.session_state.get("role", "user")

# Ajouter l'option de créer une nouvelle collection uniquement pour les admins
if role == "admin":
    options = ["-- Nouvelle Collection --"] + collections
else:
    options = collections

col1, col2 = st.columns(2)

with col1:
    selected_col = st.selectbox("Collection cible", options=options)
    
    if selected_col == "-- Nouvelle Collection --":
        target_collection = st.text_input("Nom de la nouvelle collection", "default-workspace")
        if target_collection and target_collection != "default-workspace":
            target_collection = target_collection.title()
    else:
        target_collection = selected_col

with col2:
    st.info("Formats supportés : Bureautique, PDF, Emails, Images (OCR), Textes...")

st.divider()

SUPPORTED_EXTENSIONS = [
    "txt", "md", "csv", "pdf", "doc", "docx", "xls", "xlsx", 
    "ppt", "pptx", "odt", "ods", "odp", "rtf", "html", "xml", 
    "eml", "msg", "png", "jpg", "jpeg", "tiff"
]

uploaded_file = st.file_uploader("Choisissez un fichier", type=SUPPORTED_EXTENSIONS)

if uploaded_file is not None:
    st.write(f"Fichier sélectionné : **{uploaded_file.name}** ({uploaded_file.size / 1024:.2f} Ko)")
    
    # Paramètres de chunking optionnels
    with st.expander("⚙️ Paramètres avancés"):
        chunk_size = st.number_input("Taille des chunks (caractères)", min_value=100, max_value=2000, value=800)
        chunk_overlap = st.number_input("Chevauchement (caractères)", min_value=0, max_value=500, value=100)
    
    if st.button("📤 Ingérer le document", type="primary"):
        with st.spinner("Lecture et envoi au RAG Proxy..."):
            try:
                # Détection du type de fichier et lecture du texte
                ext = uploaded_file.name.split('.')[-1].lower()
                
                if ext not in ["txt", "md", "csv"]:
                    # Extraction via Tika
                    with st.spinner("Extraction du texte avec Tika..."):
                        tika_response = requests.put(
                            f"{TIKA_URL}/tika",
                            data=uploaded_file.getvalue(),
                            headers={"Accept": "text/plain"},
                            timeout=60
                        )
                        if tika_response.status_code == 200:
                            content = tika_response.text
                        else:
                            st.error(f"❌ Erreur lors de l'extraction Tika ({tika_response.status_code})")
                            st.stop()
                else:
                    # Fichiers texte classiques
                    content = uploaded_file.getvalue().decode("utf-8")
                
                # Préparation des métadonnées
                metadata = {
                    "filename": uploaded_file.name,
                    "subject": "Manual Upload",
                    "sender": "Admin Dashboard",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "source": "Streamlit Upload"
                }
                
                # Envoi à l'API RAG Proxy
                payload = {
                    "collection": target_collection,
                    "text": content,
                    "metadata": metadata,
                    "chunk_size": int(chunk_size),
                    "chunk_overlap": int(chunk_overlap)
                }
                
                response = requests.post(
                    f"{RAG_PROXY_URL}/admin/ingest",
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("status") == "ok":
                        chunks = result.get("chunks_created", 0)
                        st.success(f"✅ Document ingéré avec succès ! {chunks} chunks créés dans '{target_collection}'.")
                    else:
                        st.error(f"❌ Erreur de l'API : {result.get('message')}")
                else:
                    st.error(f"❌ Erreur HTTP {response.status_code} : {response.text}")
                    
            except UnicodeDecodeError:
                st.error("Le fichier doit être encodé en UTF-8.")
            except Exception as e:
                st.error(f"Une erreur est survenue : {str(e)}")
