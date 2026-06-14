import logging
import time
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from email.mime.multipart import MIMEMultipart

from .base import BaseMailProvider

if TYPE_CHECKING:
    from config import Config
    from models import ParsedEmail

logger = logging.getLogger(__name__)

class MicrosoftGraphProvider(BaseMailProvider):
    """
    Implémentation de l'interface mail pour l'API Microsoft Graph.
    Utilise MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET.
    (MVP: Polling + actions de base)
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        self.tenant_id = getattr(config, "ms_tenant_id", None)
        self.client_id = getattr(config, "ms_client_id", None)
        self.client_secret = getattr(config, "ms_client_secret", None)
        self.user_email = config.imap_user  # L'email surveillé sert d'identifiant d'utilisateur Graph
        
        self.access_token = None
        self.token_expires_at = 0

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            logger.warning("MicrosoftGraphProvider instancié mais variables d'authentification incomplètes.")

    def ensure_connection(self) -> None:
        """Gère le renouvellement du jeton OAuth2 Client Credentials."""
        import requests
        
        if self.access_token and time.time() < self.token_expires_at - 60:
            return  # Jeton encore valide

        logger.info("Acquisition du jeton OAuth2 pour Microsoft Graph...")
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        payload = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }

        try:
            resp = requests.post(url, data=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3599)
            self.token_expires_at = time.time() + expires_in
            logger.debug("Jeton Graph API acquis avec succès.")
        except Exception as e:
            logger.error("Échec de l'authentification Microsoft Graph : %s", e)
            self.access_token = None
            raise

    def _get_headers(self) -> dict:
        self.ensure_connection()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def fetch_new_messages(self, last_uid: int) -> Dict[int, Any]:
        """
        Interroge l'API Graph pour les nouveaux messages.
        Note: L'API Graph utilise des string IDs, mais Mail2RAG attend des UID entiers (IMAP).
        Pour cette v1, nous devrons adapter la logique ou mocker l'UID.
        """
        import requests
        # MVP: Pour l'instant on simule le retour ou on l'implémente partiellement.
        # L'implémentation complète nécessitera une conversion Graph ID <-> UID
        logger.debug("MicrosoftGraphProvider.fetch_new_messages() appelé (STUB)")
        return {}

    def folder_exists(self, folder_name: str) -> bool:
        logger.debug("MicrosoftGraphProvider.folder_exists(%s) (STUB)", folder_name)
        return True

    def create_folder(self, folder_name: str) -> bool:
        return True

    def move_message(self, uid: int, dest_folder: str, source_folder: Optional[str] = None) -> bool:
        logger.debug("MicrosoftGraphProvider.move_message(%s -> %s) (STUB)", uid, dest_folder)
        return True

    def send_reply(self, to_email: str, subject: str, body: str, is_html: bool = False, original_message_id: str = None) -> bool:
        logger.debug("MicrosoftGraphProvider.send_reply(%s) (STUB)", to_email)
        return True

    def forward_parsed_email(self, parsed_email: "ParsedEmail", to_email: str, prefix_text: str = None, prefix_html: str = None) -> bool:
        logger.debug("MicrosoftGraphProvider.forward_parsed_email(%s) (STUB)", to_email)
        return True

    def send_synthetic_email(self, to_email: str, subject: str, text_content: str, attachment_paths: List[str] = None) -> bool:
        logger.debug("MicrosoftGraphProvider.send_synthetic_email(%s) (STUB)", to_email)
        return True

    def append_message_to_folder(self, folder: str, msg: bytes, flags: tuple = ()) -> bool:
        logger.debug("MicrosoftGraphProvider.append_message_to_folder(%s) (STUB)", folder)
        return True
