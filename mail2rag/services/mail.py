import logging
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from email.mime.multipart import MIMEMultipart

from .mail_providers.imap_provider import ImapSmtpProvider
from .mail_providers.microsoft_provider import MicrosoftGraphProvider

if TYPE_CHECKING:
    from config import Config
    from models import ParsedEmail

logger = logging.getLogger(__name__)

class MailService:
    """
    Service responsable des interactions avec la messagerie.
    Agit comme un Proxy/Factory vers l'implémentation choisie dans la config.
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        provider_name = getattr(config, "mail_provider", "imap")
        
        if provider_name == "msgraph":
            logger.info("Initialisation du MailService avec MicrosoftGraphProvider")
            self.provider = MicrosoftGraphProvider(config)
        else:
            logger.info("Initialisation du MailService avec ImapSmtpProvider")
            self.provider = ImapSmtpProvider(config)

    def ensure_connection(self) -> None:
        return self.provider.ensure_connection()

    def fetch_new_messages(self, last_uid: int) -> Dict[int, Any]:
        return self.provider.fetch_new_messages(last_uid)

    def folder_exists(self, folder_name: str) -> bool:
        return self.provider.folder_exists(folder_name)

    def create_folder(self, folder_name: str) -> bool:
        return self.provider.create_folder(folder_name)

    def move_message(self, uid: int, dest_folder: str, source_folder: Optional[str] = None) -> bool:
        return self.provider.move_message(uid, dest_folder, source_folder)

    def send_reply(self, to_email: str, subject: str, body: str, is_html: bool = False, original_message_id: str = None) -> bool:
        return self.provider.send_reply(to_email, subject, body, is_html, original_message_id)

    def forward_parsed_email(self, parsed_email: "ParsedEmail", to_email: str) -> bool:
        return self.provider.forward_parsed_email(parsed_email, to_email)

    def send_synthetic_email(self, to_email: str, subject: str, text_content: str, attachment_paths: List[str] = None) -> bool:
        return self.provider.send_synthetic_email(to_email, subject, text_content, attachment_paths)

    def append_message_to_folder(self, folder: str, msg: bytes, flags: tuple = ()) -> bool:
        return self.provider.append_message_to_folder(folder, msg, flags)

    def disconnect(self) -> None:
        if hasattr(self.provider, "disconnect"):
            self.provider.disconnect()

    @property
    def server(self):
        """Compatibilité descendante au cas où d'autres modules accèderaient encore à .server."""
        return getattr(self.provider, "server", None)
