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
    def forward_parsed_email(self, parsed_email: "ParsedEmail", to_email: str) -> bool:
        """Transfère un email complet."""
        pass

    @abstractmethod
    def send_synthetic_email(self, to_email: str, subject: str, text_content: str, attachment_paths: List[str] = None) -> bool:
        """Envoie un email synthétique (avec pièces jointes)."""
        pass

    @abstractmethod
    def append_message_to_folder(self, folder: str, msg: bytes, flags: tuple = ()) -> bool:
        """Ajoute manuellement un message dans un dossier (ex: pour les brouillons)."""
        pass
