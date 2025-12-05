import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple, TYPE_CHECKING
from urllib.parse import quote as urlquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)


class AnythingLLMClient:
    """
    Client pour l'API AnythingLLM.

    - Gère une session HTTP persistante avec retries automatiques.
    - Offre des méthodes de haut niveau pour :
      * vérifier/créer des workspaces
      * uploader des documents
      * mettre à jour les embeddings
      * envoyer des requêtes de chat
      * lister / supprimer des documents
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        self.base_url = config.anythingllm_base_url
        self.api_key = config.anythingllm_api_key

        # Timeout "par défaut" pour la plupart des appels AnythingLLM
        self._timeout_default = getattr(
            config,
            "anythingllm_chat_timeout",
            60,
        )

        if not self.api_key:
            logger.warning(
                "Aucune clé API AnythingLLM fournie (ANYTHINGLLM_API_KEY). "
                "Les appels API risquent d'échouer."
            )

        # Session HTTP avec stratégie de retry standard sur erreurs serveur
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,  # Attente : 1s, 2s, 4s...
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.debug("AnythingLLMClient initialisé vers %s", self.base_url)

    # ------------------------------------------------------------------ #
    # Helpers internes
    # ------------------------------------------------------------------ #
    def _json_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    def _auth_headers(self) -> Dict[str, str]:
        # Pour les uploads multipart où "Content-Type" est géré par requests
        return {
            "Authorization": f"Bearer {self.api_key}",
            "accept": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Workspaces
    # ------------------------------------------------------------------ #
    def ensure_workspace_exists(self, workspace_slug: str) -> bool:
        """
        Vérifie l'existence d'un workspace et le crée si nécessaire.

        Retourne:
            True si le workspace existe ou a été créé avec succès, False sinon.
        """
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}"

        logger.debug("Vérification existence workspace '%s'", workspace_slug)

        exists = False
        try:
            resp = self.session.get(
                url,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code == 200:
                data = resp.json()
                # L'API retourne {"workspace": []} si le slug n'existe pas
                if isinstance(data, dict) and "workspace" in data:
                    exists = bool(data["workspace"])
                else:
                    # Fallback pour anciennes versions ou formats différents
                    exists = True
        except Exception as e:
            logger.warning(
                "Erreur lors de la vérification du workspace '%s': %s",
                workspace_slug,
                e,
                exc_info=True,
            )

        if exists:
            logger.debug("Workspace '%s' existe déjà.", workspace_slug)
            return True

        # Création si inexistant
        create_url = f"{self.base_url}/workspace/new"
        payload = {"name": workspace_slug}

        try:
            logger.info("Création du workspace '%s'...", workspace_slug)
            resp = self.session.post(
                create_url,
                json=payload,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code in (200, 201):
                logger.info("✅ Workspace '%s' créé avec succès.", workspace_slug)
                return True

            logger.error(
                "❌ Échec création workspace '%s'. Code: %s, Réponse: %s",
                workspace_slug,
                resp.status_code,
                resp.text,
            )
            return False
        except Exception as e:
            logger.error(
                "Erreur API lors de la création du workspace '%s': %s",
                workspace_slug,
                e,
                exc_info=True,
            )
            return False

    def update_workspace_settings(
        self,
        workspace_slug: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        refusal_response: Optional[str] = None,
    ) -> bool:
        """
        Met à jour les paramètres d'un workspace (prompt système, température, réponse de refus).

        Si aucun paramètre n'est fourni, renvoie True sans effectuer d'appel.
        """
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}/update"

        payload: Dict[str, Any] = {}

        if system_prompt is not None:
            # AnythingLLM utilise 'openAiPrompt' pour le prompt système
            payload["openAiPrompt"] = system_prompt

        if temperature is not None:
            payload["openAiTemp"] = temperature

        if refusal_response is not None:
            payload["queryRefusalResponse"] = refusal_response

        if not payload:
            # Rien à mettre à jour
            return True

        try:
            logger.info(
                "Mise à jour des paramètres du workspace '%s'...",
                workspace_slug,
            )
            resp = self.session.post(
                url,
                json=payload,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code == 200:
                logger.info(
                    "✅ Paramètres du workspace '%s' mis à jour.",
                    workspace_slug,
                )
                return True

            logger.error(
                "❌ Échec update workspace '%s'. Code: %s, Réponse: %s",
                workspace_slug,
                resp.status_code,
                resp.text,
            )
            return False
        except Exception as e:
            logger.error(
                "Erreur API update workspace '%s': %s",
                workspace_slug,
                e,
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------ #
    # Documents
    # ------------------------------------------------------------------ #
    def upload_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """
        Upload un fichier vers AnythingLLM et retourne sa location interne.

        Args:
            file_path: chemin du fichier à envoyer

        Returns:
            location (str) ou None en cas d'échec.
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.error("Fichier introuvable pour upload: %s", path_obj)
            return None

        url = f"{self.base_url}/document/upload"

        logger.debug("Début upload fichier : %s", path_obj.name)

        try:
            with path_obj.open("rb") as f:
                files = {"file": f}
                resp = self.session.post(
                    url,
                    headers=self._auth_headers(),
                    files=files,
                    timeout=self.config.anythingllm_upload_timeout,
                )

            if resp.status_code != 200:
                logger.error(
                    "Upload échoué (%s): %s",
                    resp.status_code,
                    resp.text,
                )
                return None

            data = resp.json()
            loc: Optional[str] = None

            # Gestion robuste des différentes versions d'API
            if "location" in data:
                loc = data["location"]
            elif "documents" in data and data["documents"]:
                loc = data["documents"][0].get("location")

            if loc:
                logger.debug("Fichier uploadé avec succès à : %s", loc)
                return loc

            logger.warning(
                "Réponse upload inattendue (pas de location) : %s",
                str(data)[:500],
            )
            return None

        except Exception as e:
            logger.error(
                "Exception lors de l'upload du fichier '%s': %s",
                path_obj,
                e,
                exc_info=True,
            )
            return None

    def delete_document(self, location: str) -> bool:
        """
        Supprime un document du système (fonction admin).

        Args:
            location: location interne du document

        Returns:
            True si suppression OK, False sinon.
        """
        url = f"{self.base_url}/document/delete"
        payload = {"location": location}

        logger.debug("Demande de suppression document : %s", location)

        try:
            resp = self.session.post(
                url,
                json=payload,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code == 200:
                logger.info("Document '%s' supprimé avec succès.", location)
                return True

            logger.error(
                "Échec suppression document '%s'. Code: %s, Réponse: %s",
                location,
                resp.status_code,
                resp.text,
            )
            return False
        except Exception as e:
            logger.error(
                "Erreur technique lors de la suppression du document '%s': %s",
                location,
                e,
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------ #
    # Embeddings
    # ------------------------------------------------------------------ #
    def update_embeddings(
        self,
        workspace_slug: str,
        adds: Optional[List[str]] = None,
        deletes: Optional[List[str]] = None,
    ) -> bool:
        """
        Met à jour les vecteurs du workspace.

        Stratégie "dual-try" pour gérer les différences de format d'API :
        1. Format simple : {"adds": ["..."], "deletes": []}
        2. Format objets : {"adds": [{"location": "..."}], "deletes": []}
        """
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}/update-embeddings"

        adds = adds or []
        deletes = deletes or []

        logger.debug(
            "Mise à jour des embeddings pour '%s'. Ajouts: %d, Suppressions: %d",
            workspace_slug,
            len(adds),
            len(deletes),
        )

        # Tentative 1 : format simple
        payload_simple = {"adds": adds, "deletes": deletes}

        try:
            logger.debug(
                "Tentative update embeddings (format 1: liste simple) pour '%s'",
                workspace_slug,
            )
            resp = self.session.post(
                url,
                json=payload_simple,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code == 200:
                logger.debug("✅ Format 1 (liste simple) accepté.")
                return True

            logger.warning(
                "Format 1 refusé (%s). Réponse: %s. Tentative format 2...",
                resp.status_code,
                resp.text,
            )
        except Exception as e:
            logger.warning(
                "Erreur technique format 1 (embeddings) pour '%s': %s",
                workspace_slug,
                e,
                exc_info=True,
            )

        # Tentative 2 : format objets
        payload_obj = {
            "adds": [{"location": p} for p in adds],
            "deletes": deletes,
        }

        try:
            logger.debug(
                "Tentative update embeddings (format 2: objets) pour '%s'",
                workspace_slug,
            )
            resp = self.session.post(
                url,
                json=payload_obj,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code == 200:
                logger.debug("✅ Format 2 (objets) accepté.")
                return True

            logger.error(
                "❌ Échec définitif embeddings pour '%s'. Code: %s, Réponse: %s",
                workspace_slug,
                resp.status_code,
                resp.text,
            )
            return False
        except Exception as e:
            logger.error(
                "Erreur embeddings critique pour '%s': %s",
                workspace_slug,
                e,
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #
    def send_chat_query(
        self,
        workspace_slug: str,
        message: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Envoie une question à AnythingLLM (mode chat) et retourne (réponse, sources).

        Args:
            workspace_slug: slug du workspace
            message: contenu textuel de la question

        Returns:
            (texte de réponse, liste de sources)
        """
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}/chat"
        payload = {"message": message, "mode": "chat"}

        logger.debug("Envoi chat query vers workspace '%s'...", workspace_slug)

        try:
            resp = self.session.post(
                url,
                json=payload,
                headers=self._json_headers(),
                timeout=self.config.anythingllm_chat_timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("textResponse", "Pas de réponse.")
                sources = data.get("sources", []) or []
                logger.debug(
                    "Réponse chat reçue pour '%s'. Nombre de sources: %d",
                    workspace_slug,
                    len(sources),
                )
                return text, sources

            logger.error(
                "Erreur API chat (%s) pour '%s': %s",
                resp.status_code,
                workspace_slug,
                resp.text,
            )
            return f"Erreur API: {resp.status_code}", []
        except Exception as e:
            logger.error(
                "Erreur technique chat pour '%s': %s",
                workspace_slug,
                e,
                exc_info=True,
            )
            return f"Erreur technique: {e}", []

    # ------------------------------------------------------------------ #
    # Listing / Info
    # ------------------------------------------------------------------ #
    def list_workspaces(self) -> List[Dict[str, Any]]:
        """
        Liste tous les workspaces disponibles.

        Returns:
            Liste de dicts décrivant les workspaces.
        """
        url = f"{self.base_url}/workspaces"
        logger.debug("Récupération de la liste des workspaces...")

        try:
            resp = self.session.get(
                url,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code == 200:
                data = resp.json()
                workspaces = data.get("workspaces", []) or []
                logger.info("✅ %d workspaces trouvés", len(workspaces))
                return workspaces

            logger.error(
                "Erreur API list_workspaces (%s): %s",
                resp.status_code,
                resp.text,
            )
            return []
        except Exception as e:
            logger.error("Erreur technique list_workspaces: %s", e, exc_info=True)
            return []

    def list_documents(self, workspace_slug: str) -> List[Dict[str, Any]]:
        """
        Liste tous les documents d'un workspace.

        Returns:
            Liste de dicts décrivant les documents.
        """
        safe_slug = urlquote(workspace_slug)
        url = f"{self.base_url}/workspace/{safe_slug}"

        logger.debug(
            "Récupération des documents du workspace '%s'...",
            workspace_slug,
        )

        try:
            resp = self.session.get(
                url,
                headers=self._json_headers(),
                timeout=self._timeout_default,
            )
            if resp.status_code != 200:
                logger.error(
                    "Erreur API list_documents (%s) pour '%s': %s",
                    resp.status_code,
                    workspace_slug,
                    resp.text,
                )
                return []

            data = resp.json()
            logger.debug(
                "DEBUG list_documents: type(data)=%s, extrait=%s",
                type(data),
                str(data)[:500],
            )

            documents: List[Dict[str, Any]] = []

            if isinstance(data, list):
                # API renvoie directement la liste des documents
                documents = data
                logger.debug("Format détecté: liste directe")
            elif isinstance(data, dict):
                workspace_data = data.get("workspace", {})
                logger.debug(
                    "Format détecté: dict, type(workspace_data)=%s",
                    type(workspace_data),
                )

                if isinstance(workspace_data, list):
                    documents = workspace_data
                    logger.debug("workspace_data est une liste directe")
                elif isinstance(workspace_data, dict):
                    documents = workspace_data.get("documents", []) or []
                    logger.debug("workspace_data est un dict avec 'documents'")
                else:
                    logger.debug(
                        "workspace_data est d'un type inconnu: %s",
                        type(workspace_data),
                    )
            else:
                logger.debug("Format de réponse inconnu pour list_documents")

            logger.debug(
                "%d documents trouvés dans le workspace '%s'",
                len(documents),
                workspace_slug,
            )
            return documents

        except Exception as e:
            logger.error(
                "Erreur technique list_documents pour '%s': %s",
                workspace_slug,
                e,
                exc_info=True,
            )
            return []

    def get_document_info(
        self,
        workspace_slug: str,
        doc_location: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère les métadonnées d'un document spécifique dans un workspace.

        Args:
            workspace_slug: slug du workspace
            doc_location: location ou nom du document

        Returns:
            dict de métadonnées ou None si non trouvé.
        """
        documents = self.list_documents(workspace_slug)
        for doc in documents:
            if doc.get("location") == doc_location or doc.get("name") == doc_location:
                return doc
        return None
