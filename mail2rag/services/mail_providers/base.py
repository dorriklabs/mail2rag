from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from email.mime.multipart import MIMEMultipart

if TYPE_CHECKING:
    from models import ParsedEmail

class BaseMailProvider(ABC):
    """
    Interface commune pour tous les fournisseurs de messagerie (IMAP, Microsoft Graph, etc.).
    """

    @abstractmethod
    def ensure_connection(self) -> None:
        """S'assure que la connexion est active, reconnexion si nécessaire."""
        pass

    @abstractmethod
    def fetch_new_messages(self, last_uid: int) -> Dict[int, Any]:
        """Récupère les nouveaux messages depuis last_uid."""
        pass

    @abstractmethod
    def folder_exists(self, folder_name: str) -> bool:
        """Vérifie l'existence d'un dossier."""
        pass

    @abstractmethod
    def create_folder(self, folder_name: str) -> bool:
        """Crée un dossier."""
        pass

    @abstractmethod
    def move_message(self, uid: int, dest_folder: str, source_folder: Optional[str] = None) -> bool:
        """Déplace un message d'un dossier à un autre."""
        pass

    @abstractmethod
    def send_reply(self, to_email: str, subject: str, body: str, is_html: bool = False, original_message_id: str = None) -> bool:
        """Envoie une réponse à un email."""
        pass

    @abstractmethod
    def send_combined_email(self, service_email: str, client_email: str, subject: str, body_html: str, original_message_id: str = None) -> bool:
        """Envoie un email combiné au service cible avec l'adresse du client en Reply-To."""
        pass

    @abstractmethod
    def forward_parsed_email(self, parsed_email: "ParsedEmail", to_email: str, prefix_text: str = None, prefix_html: str = None, dynamic_attachments: List[tuple] = None) -> bool:
        """
        Transfère un email parsé vers une nouvelle adresse.
        Si prefix_text ou prefix_html est fourni, il sera injecté au début du message transféré.
        dynamic_attachments permet d'ajouter des PJ générées à la volée (ex: sources PDF).
        """
        pass

    @abstractmethod
    def send_synthetic_email(self, to_email: str, subject: str, text_content: str, attachment_paths: List[str] = None) -> bool:
        """Envoie un email synthétique (avec pièces jointes)."""
        pass

    @abstractmethod
    def send_generated_email(self, eml: "EmailMessage", dynamic_attachments: List[tuple] = None) -> bool:
        """Envoie un objet EmailMessage pré-généré, avec d'éventuelles pièces jointes supplémentaires."""
        pass

    def _attach_dynamic_files(self, msg, dynamic_attachments: List[tuple]) -> None:
        """Helper DRY pour ajouter des pièces jointes dynamiques à un objet MIME/EmailMessage."""
        if not dynamic_attachments:
            return
        from email.mime.application import MIMEApplication
        for filename, content, mimetype in dynamic_attachments:
            part = MIMEApplication(content)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)

    @abstractmethod
    def append_message_to_folder(self, folder: str, msg: bytes, flags: tuple = ()) -> bool:
        """Ajoute manuellement un message dans un dossier (ex: pour les brouillons)."""
        pass
