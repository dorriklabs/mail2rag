import time
import logging
import requests
import json
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple
from urllib.parse import quote as urlquote

logger = logging.getLogger(__name__)

class AnythingLLMClient:
    """
    Client robuste pour l'API AnythingLLM avec gestion de session, retries
    et compatibilité multi-versions pour l'embedding.
    """
    def __init__(self, config):
        self.base_url = config.anythingllm_base_url
        self.api_key = config.anythingllm_api_key
        
        # Session Persistante avec Retry automatique sur erreurs serveur
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1, # Attente : 1s, 2s, 4s...
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        logger.debug(f"Client API initialisé vers {self.base_url}")

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def ensure_workspace_exists(self, workspace_slug: str) -> bool:
        """Vérifie l'existence d'un workspace et le crée si nécessaire."""
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}"
        
        logger.debug(f"Check existence Workspace : {workspace_slug}")
        
        exists = False
        try:
            r = self.session.get(url, headers=self._get_headers())
            if r.status_code == 200:
                exists = True
        except Exception: 
            pass

        if exists:
            logger.debug(f"Workspace '{workspace_slug}' existe déjà.")
            return True

        # Création si inexistant
        create_url = f"{self.base_url}/workspace/new"
        # On envoie le nom, AnythingLLM génère le slug interne
        payload = {"name": workspace_slug} 
        
        try:
            logger.info(f"Création du Workspace '{workspace_slug}'...")
            r = self.session.post(create_url, json=payload, headers=self._get_headers())
            
            if r.status_code in [200, 201]:
                logger.info(f"✅ Workspace '{workspace_slug}' créé avec succès.")
                return True
            else:
                logger.error(f"❌ Échec création Workspace. Code: {r.status_code}, Réponse: {r.text}")
                return False
        except Exception as e:
            logger.error(f"Erreur API workspace: {e}")
            return False

    def upload_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Upload un fichier et retourne sa location interne."""
        path_obj = Path(file_path)
        if not path_obj.exists(): return None

        url = f"{self.base_url}/document/upload"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        logger.debug(f"Début upload fichier : {path_obj.name}")

        try:
            with open(path_obj, 'rb') as f:
                files = {'file': f}
                # Timeout long (120s) pour les gros fichiers
                response = self.session.post(url, headers=headers, files=files, timeout=120)
                
            if response.status_code != 200:
                logger.error(f"Upload échoué ({response.status_code}): {response.text}")
                return None

            data = response.json()
            loc = None
            
            # Gestion robuste des différentes versions d'API
            if 'location' in data: 
                loc = data['location']
            elif 'documents' in data and data['documents']: 
                loc = data['documents'][0].get('location')
            
            if loc:
                logger.debug(f"Fichier uploadé avec succès à : {loc}")
                return loc
            else:
                logger.warning(f"Réponse upload inattendue (pas de location) : {data}")
                return None

        except Exception as e:
            logger.error(f"Exception Upload: {e}")
            return None

    def update_embeddings(self, workspace_slug: str, adds: List[str] = None, deletes: List[str] = None) -> bool:
        """
        Met à jour les vecteurs du workspace.
        Utilise une stratégie 'Dual-Try' pour gérer les différences de format d'API.
        """
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}/update-embeddings"
        
        adds = adds or []
        deletes = deletes or []
        
        logger.debug(f"Mise à jour embeddings pour '{workspace_slug}'. Ajouts: {len(adds)}")

        # --- STRATÉGIE DUAL-TRY (Format Objet vs Format Simple) ---

        # TENTATIVE 1 : Format "Liste d'Objets" (Requis par certaines versions Docker)
        # Format : { "adds": [{"location": "..."}], "deletes": [] }
        payload_obj = {
            "adds": [{"location": p} for p in adds],
            "deletes": deletes
        }
        
        try:
            logger.debug("Tentative Embedding Format 1 (Objets)...")
            r = self.session.post(url, json=payload_obj, headers=self._get_headers())
            if r.status_code == 200:
                logger.debug("✅ Format 1 accepté.")
                return True
            else:
                logger.warning(f"⚠️ Format 1 refusé ({r.status_code}). Tentative Format 2...")
        except Exception as e:
            logger.warning(f"Erreur technique Format 1: {e}")

        # TENTATIVE 2 : Format "Liste Simple" (Requis par les versions récentes/Desktop)
        # Format : { "adds": ["..."], "deletes": [] }
        payload_simple = {
            "adds": adds, 
            "deletes": deletes
        }
        
        try:
            logger.debug("Tentative Embedding Format 2 (Liste Simple)...")
            r = self.session.post(url, json=payload_simple, headers=self._get_headers())
            if r.status_code == 200:
                logger.debug("✅ Format 2 accepté.")
                return True
            
            # Si tout échoue
            logger.error(f"❌ Échec définitif Embeddings (Code {r.status_code}). Réponse Serveur : {r.text}")
            return False
        except Exception as e:
            logger.error(f"Erreur Embeddings critique : {e}")
            return False

    def send_chat_query(self, workspace_slug: str, message: str) -> Tuple[str, List]:
        """Envoie une question et retourne (Réponse, Liste des Sources)."""
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}/chat"
        payload = {"message": message, "mode": "chat"}
        
        logger.debug(f"Envoi Chat Query vers '{workspace_slug}'...")
        
        try:
            # Timeout 60s pour laisser le temps à l'IA de répondre
            r = self.session.post(url, json=payload, headers=self._get_headers(), timeout=60)
            if r.status_code == 200:
                data = r.json()
                text = data.get('textResponse', 'Pas de réponse.')
                sources = data.get('sources', [])
                logger.debug(f"Réponse Chat reçue. Sources: {len(sources)}")
                return text, sources
            
            logger.error(f"Erreur API Chat {r.status_code}: {r.text}")
            return f"Erreur API: {r.status_code}", []
        except Exception as e:
            logger.error(f"Erreur technique Chat: {e}")
            return f"Erreur technique: {e}", []

    def delete_document(self, location: str) -> bool:
        """Supprime un document du système (Fonction Admin)."""
        url = f"{self.base_url}/document/delete"
        payload = {"location": location}
        logger.debug(f"Demande suppression doc : {location}")
        try:
            r = self.session.post(url, json=payload, headers=self._get_headers())
            return r.status_code == 200
        except Exception: return False
