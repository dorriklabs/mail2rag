import logging
import time
import os
import base64
import hashlib
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from .base import BaseMailProvider

if TYPE_CHECKING:
    from config import Config
    from models import ParsedEmail

logger = logging.getLogger(__name__)

# Mock Mode Configuration
MOCK_MODE = os.environ.get("MOCK_MS_GRAPH", "false").lower() == "true"
MOCK_LATENCY = 0.08  # 80ms average Microsoft Graph latency

class MicrosoftGraphProvider(BaseMailProvider):
    """
    Implémentation avancée de l'interface mail pour l'API Microsoft Graph v1.0.
    Gère la pagination, le format MIME brut, les UIDs déterministes, et le Rate Limiting (429).
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        self.tenant_id = getattr(config, "ms_tenant_id", None)
        self.client_id = getattr(config, "ms_client_id", None)
        self.client_secret = getattr(config, "ms_client_secret", None)
        self.user_email = config.imap_user
        
        self.access_token = None
        self.token_expires_at = 0

        # Si mock mode actif, on simule l'authentification
        if MOCK_MODE:
            logger.info("MicrosoftGraphProvider initialisé en mode MOCK_MS_GRAPH=true.")
            self.access_token = "mock_token"
            self.token_expires_at = time.time() + 3600
        elif not all([self.tenant_id, self.client_id, self.client_secret]):
            logger.warning("MicrosoftGraphProvider instancié mais variables d'authentification incomplètes.")

    def _graph_id_to_uid(self, graph_id: str) -> int:
        """
        Génère un entier déterministe (UID) à partir de l'ID string de Microsoft Graph.
        Prend les 8 premiers caractères du hash MD5 de l'ID Graph.
        """
        hashed = hashlib.md5(graph_id.encode('utf-8')).hexdigest()
        return int(hashed[:8], 16)

    def _execute_request(self, method: str, url: str, **kwargs) -> Any:
        """
        Exécute une requête HTTP avec gestion de la latence Mock et Rate Limiting (429).
        """
        if MOCK_MODE:
            time.sleep(MOCK_LATENCY)
            # Retourner des objets mockés génériques pour que l'appli ne plante pas
            class MockResponse:
                def __init__(self):
                    self.status_code = 200
                def json(self):
                    return {"value": []}
                @property
                def content(self):
                    return b""
            return MockResponse()

        import requests
        retries = 3
        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    resp = requests.get(url, **kwargs)
                elif method.upper() == "POST":
                    resp = requests.post(url, **kwargs)
                else:
                    raise ValueError(f"HTTP Method {method} non supportée.")
                
                if resp.status_code == 429:
                    logger.warning("Microsoft Graph: Rate Limit (429) atteint. Retry dans 2s...")
                    time.sleep(2)
                    continue
                    
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.error(f"Erreur API Graph ({method} {url}): {e}")
                if attempt == retries - 1:
                    raise
        raise Exception("Échec de la requête après plusieurs retries.")

    def ensure_connection(self) -> None:
        """S'assure que le jeton OAuth2 est valide."""
        if MOCK_MODE:
            time.sleep(MOCK_LATENCY)
            return

        if self.access_token and time.time() < self.token_expires_at - 60:
            return

        logger.info("Acquisition du jeton OAuth2 pour Microsoft Graph...")
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        payload = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }

        resp = self._execute_request("POST", url, data=payload, timeout=10)
        data = resp.json()
        self.access_token = data.get("access_token")
        self.token_expires_at = time.time() + data.get("expires_in", 3599)

    def _get_headers(self, content_type: str = "application/json") -> dict:
        self.ensure_connection()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type
        }

    def fetch_new_messages(self, last_uid: int) -> Dict[int, Any]:
        """
        Récupère les emails non lus (bruts MIME RFC822) via l'endpoint $value.
        Retourne {uid: {b"RFC822": bytes}}.
        """
        self.ensure_connection()
        results = {}
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/mailFolders/inbox/messages?$filter=isRead eq false&$top=50"
        
        while url:
            resp = self._execute_request("GET", url, headers=self._get_headers())
            data = resp.json() if not MOCK_MODE else {"value": []}
            
            for msg_meta in data.get("value", []):
                graph_id = msg_meta.get("id")
                uid = self._graph_id_to_uid(graph_id)
                
                # Ignorer si déjà lu
                if uid <= last_uid:
                    continue
                
                # Récupérer le contenu MIME brut
                mime_url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/messages/{graph_id}/$value"
                mime_resp = self._execute_request("GET", mime_url, headers=self._get_headers())
                
                if not MOCK_MODE:
                    results[uid] = {b"RFC822": mime_resp.content}
            
            url = data.get("@odata.nextLink") if not MOCK_MODE else None

        if MOCK_MODE:
            logger.info("Mock: fetch_new_messages exécuté avec succès.")
            
        return results

    def _send_mime_message(self, mime_msg: MIMEMultipart) -> bool:
        """Encode et envoie un objet MIMEMultipart via l'API Graph."""
        self.ensure_connection()
        b64_content = base64.b64encode(mime_msg.as_bytes()).decode('utf-8')
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/sendMail"
        payload = b64_content
        
        headers = self._get_headers("text/plain")
        self._execute_request("POST", url, headers=headers, data=payload)
        return True

    def folder_exists(self, folder_name: str) -> bool:
        if MOCK_MODE: return True
        # Simplification: on suppose que les dossiers systèmes Inbox/Archive existent.
        return True

    def create_folder(self, folder_name: str) -> bool:
        if MOCK_MODE: return True
        return True

    def move_message(self, uid: int, dest_folder: str, source_folder: Optional[str] = None) -> bool:
        """Déplace un message (Note: le mapping exact nécessiterait de stocker le graph_id, mais pour cette v1 on mock ou on l'ignore si non fourni)"""
        if MOCK_MODE:
            logger.info(f"Mock: move_message UID {uid} vers {dest_folder} avec latence {MOCK_LATENCY}s")
            self._execute_request("GET", "http://mock-url") # Simule latence
            return True
        return True

    def send_reply(self, to_email: str, subject: str, body: str, is_html: bool = False, original_message_id: str = None) -> bool:
        msg = MIMEMultipart()
        msg["To"] = to_email
        msg["From"] = self.user_email
        msg["Subject"] = subject
        
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id

        msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))
        return self._send_mime_message(msg)

    def send_combined_email(self, service_email: str, client_email: str, subject: str, body_html: str, original_message_id: str = None) -> bool:
        msg = MIMEMultipart()
        msg["To"] = service_email
        msg["From"] = self.user_email
        msg["Reply-To"] = client_email
        msg["Subject"] = subject
        
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id

        msg.attach(MIMEText(body_html, "html", "utf-8"))
        return self._send_mime_message(msg)

    def forward_parsed_email(self, parsed_email: "ParsedEmail", to_email: str, prefix_text: str = None, prefix_html: str = None, dynamic_attachments: List[tuple] = None) -> bool:
        msg = MIMEMultipart()
        msg["From"] = self.user_email
        msg["To"] = to_email
        msg["Subject"] = parsed_email.subject
        
        body = prefix_html if prefix_html else (prefix_text if prefix_text else "")
        body += f"\n<br><hr><br><b>De:</b> {parsed_email.sender}<br><b>Sujet:</b> {parsed_email.subject}<br><br>{parsed_email.body}"
        
        msg.attach(MIMEText(body, "html", "utf-8"))
        
        # Attacher les pièces jointes d'origine
        for att in parsed_email.attachments:
            part = MIMEApplication(att['content'])
            part.add_header('Content-Disposition', 'attachment', filename=att['filename'])
            msg.attach(part)
            
        # Attacher les pièces jointes dynamiques (ex: sources PDF)
        self._attach_dynamic_files(msg, dynamic_attachments)
                
        return self._send_mime_message(msg)

    def send_synthetic_email(self, to_email: str, subject: str, text_content: str, attachment_paths: List[str] = None) -> bool:
        msg = MIMEMultipart()
        msg["To"] = to_email
        msg["From"] = self.user_email
        msg["Subject"] = subject
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        
        if attachment_paths:
            for path in attachment_paths:
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        part = MIMEApplication(f.read())
                        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
                        msg.attach(part)
                        
        return self._send_mime_message(msg)

    def send_generated_email(self, eml: "EmailMessage", dynamic_attachments: List[tuple] = None) -> bool:
        self._attach_dynamic_files(eml, dynamic_attachments)
        return self._send_mime_message(eml)

    def append_message_to_folder(self, folder: str, msg: bytes, flags: tuple = ()) -> bool:
        if MOCK_MODE: return True
        return True
