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
        self.config = config  # Store config for later use
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
            "Content-Type": "application/json",
            "accept": "application/json"
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
                data = r.json()
                # L'API retourne {"workspace": []} si le slug n'existe pas
                if isinstance(data, dict) and 'workspace' in data:
                    if data['workspace']: # Liste non vide = Existe
                        exists = True
                else:
                    # Fallback pour anciennes versions ou formats différents
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

    def update_workspace_settings(self, workspace_slug: str, system_prompt: str = None, 
                                   temperature: float = None, refusal_response: str = None) -> bool:
        """Met à jour les paramètres d'un workspace (Prompt, Température, Réponse de refus)."""
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}/update"
        
        payload = {}
        if system_prompt is not None:
            # AnythingLLM utilise 'openAiPrompt' pour le prompt système
            payload["openAiPrompt"] = system_prompt
        
        if temperature is not None:
            payload["openAiTemp"] = temperature
            
        if refusal_response is not None:
            payload["queryRefusalResponse"] = refusal_response
            
        if not payload:
            return True
            
        try:
            logger.info(f"Mise à jour paramètres Workspace '{workspace_slug}'...")
            r = self.session.post(url, json=payload, headers=self._get_headers())
            
            if r.status_code == 200:
                logger.info(f"✅ Paramètres '{workspace_slug}' mis à jour.")
                return True
            else:
                logger.error(f"❌ Échec update Workspace. Code: {r.status_code}, Réponse: {r.text}")
                return False
        except Exception as e:
            logger.error(f"Erreur API update workspace: {e}")
            return False

    def upload_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Upload un fichier et retourne sa location interne."""
        path_obj = Path(file_path)
        if not path_obj.exists(): return None

        url = f"{self.base_url}/document/upload"
        headers = {"Authorization": f"Bearer {self.api_key}", "accept": "application/json"}
        
        logger.debug(f"Début upload fichier : {path_obj.name}")

        try:
            with open(path_obj, 'rb') as f:
                files = {'file': f}
                # Timeout long (120s) pour les gros fichiers
                response = self.session.post(url, headers=headers, files=files, timeout=self.config.anythingllm_upload_timeout)
                
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

        # --- STRATÉGIE DUAL-TRY (Optimisée : Format Simple d'abord) ---

        # TENTATIVE 1 : Format "Liste Simple" (Standard actuel)
        # Format : { "adds": ["..."], "deletes": [] }
        payload_simple = {
            "adds": adds, 
            "deletes": deletes
        }
        
        try:
            logger.debug("Tentative Embedding Format 1 (Liste Simple)...")
            r = self.session.post(url, json=payload_simple, headers=self._get_headers())
            if r.status_code == 200:
                logger.debug("✅ Format 1 (Liste Simple) accepté.")
                return True
            else:
                logger.warning(f"⚠️ Format 1 refusé ({r.status_code}). Tentative Format 2...")
        except Exception as e:
            logger.warning(f"Erreur technique Format 1: {e}")

        # TENTATIVE 2 : Format "Liste d'Objets" (Legacy / Compatibilité)
        # Format : { "adds": [{"location": "..."}], "deletes": [] }
        payload_obj = {
            "adds": [{"location": p} for p in adds],
            "deletes": deletes
        }
        
        try:
            logger.debug("Tentative Embedding Format 2 (Objets)...")
            r = self.session.post(url, json=payload_obj, headers=self._get_headers())
            if r.status_code == 200:
                logger.debug("✅ Format 2 (Objets) accepté.")
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
            r = self.session.post(url, json=payload, headers=self._get_headers(), timeout=self.config.anythingllm_chat_timeout)
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

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """Liste tous les workspaces disponibles."""
        url = f"{self.base_url}/workspaces"
        logger.debug("Récupération de la liste des workspaces")
        try:
            r = self.session.get(url, headers=self._get_headers(), timeout=30)
            if r.status_code == 200:
                data = r.json()
                workspaces = data.get('workspaces', [])
                logger.info(f"✅ {len(workspaces)} workspaces trouvés")
                return workspaces
            logger.error(f"Erreur API list_workspaces {r.status_code}: {r.text}")
            return []
        except Exception as e:
            logger.error(f"Erreur technique list_workspaces: {e}")
            return []

    def list_documents(self, workspace_slug: str) -> List[Dict[str, Any]]:
        """Liste tous les documents d'un workspace."""
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}"
        logger.debug(f"Récupération des documents du workspace '{workspace_slug}'")
        try:
            r = self.session.get(url, headers=self._get_headers(), timeout=30)
            if r.status_code == 200:
                data = r.json()
                
                # DEBUG : Voir ce que l'API retourne exactement
                logger.debug(f"  DEBUG list_documents: type(data) = {type(data)}")
                logger.debug(f"  DEBUG list_documents: data = {str(data)[:500]}")
                
                # L'API peut retourner soit une liste directement, soit un dict avec 'workspace'
                if isinstance(data, list):
                    documents = data
                    logger.debug(f"  DEBUG: Format détecté = LISTE DIRECTE")
                elif isinstance(data, dict):
                    workspace_data = data.get('workspace', {})
                    logger.debug(f"  DEBUG: Format détecté = DICT, workspace_data type = {type(workspace_data)}")
                    
                    # workspace_data peut être soit un dict avec 'documents', soit directement une liste
                    if isinstance(workspace_data, list):
                        documents = workspace_data
                        logger.debug(f"  DEBUG: workspace_data est une liste directe")
                    elif isinstance(workspace_data, dict):
                        documents = workspace_data.get('documents', [])
                        logger.debug(f"  DEBUG: workspace_data est un dict")
                    else:
                        documents = []
                        logger.debug(f"  DEBUG: workspace_data est d'un type inconnu: {type(workspace_data)}")
                else:
                    documents = []
                    logger.debug(f"  DEBUG: Format INCONNU")
                
                logger.debug(f"  {len(documents)} documents trouvés dans '{workspace_slug}'")
                return documents
            logger.error(f"Erreur API list_documents {r.status_code}: {r.text}")
            return []
        except Exception as e:
            logger.error(f"Erreur technique list_documents: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def get_document_info(self, workspace_slug: str, doc_location: str) -> Optional[Dict[str, Any]]:
        """Récupère les métadonnées d'un document spécifique."""
        documents = self.list_documents(workspace_slug)
        for doc in documents:
            if doc.get('location') == doc_location or doc.get('name') == doc_location:
                return doc
        return None
