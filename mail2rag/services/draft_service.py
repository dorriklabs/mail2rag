"""
Service de création de brouillons IMAP pour le mode Support Draft.

Responsabilités :
- Création de drafts dans le dossier Drafts IMAP
- Gestion des headers de threading (In-Reply-To, References)
- Déplacement des emails vers dossier "En cours"
- Détection automatique du nom du dossier Drafts
"""

import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config
    from services.mail import MailService

logger = logging.getLogger(__name__)


# Noms de dossiers Drafts courants (ordre de priorité)
DRAFT_FOLDER_CANDIDATES = [
    "Drafts",
    "Draft",
    "Brouillons",
    "INBOX.Drafts",
    "[Gmail]/Brouillons",
    "[Gmail]/Drafts",
]

# Noms de dossiers pour emails traités
PROCESSED_FOLDER_DEFAULT = "En cours"


class DraftService:
    """
    Service de création de brouillons IMAP.
    
    Permet de créer des brouillons de réponse dans la boîte mail
    du client, avec les headers appropriés pour le threading email.
    """

    def __init__(
        self,
        config: "Config",
        logger_instance: logging.Logger,
        mail_service: "MailService",
    ):
        """
        Initialise le service de brouillons.
        
        Args:
            config: Configuration de l'application
            logger_instance: Logger pour les messages
            mail_service: Service mail pour les opérations IMAP
        """
        self.config = config
        self.logger = logger_instance
        self.mail_service = mail_service
        
        # Configuration des dossiers
        self.drafts_folder = getattr(config, "imap_drafts_folder", "") or ""
        self.processed_folder = (
            getattr(config, "imap_processed_folder", "") 
            or PROCESSED_FOLDER_DEFAULT
        )
        
        # Cache du dossier Drafts détecté
        self._detected_drafts_folder: Optional[str] = None

    def create_draft(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        original_uid: Optional[int] = None,
    ) -> bool:
        """
        Crée un brouillon dans le dossier Drafts IMAP.
        
        Args:
            to_email: Destinataire (le client ayant posé la question)
            subject: Sujet (Re: préfixé automatiquement si absent)
            body_html: Corps HTML du brouillon
            in_reply_to: Message-ID de l'email original
            references: Chaîne de Message-IDs pour threading
            original_uid: UID de l'email original (pour tracking)
            
        Returns:
            True si création réussie, False sinon
        """
        try:
            # Préparer le sujet
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
            
            # Construire le message MIME
            msg = MIMEMultipart("alternative")
            msg["From"] = self.config.imap_user
            msg["To"] = to_email
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=self._get_domain())
            
            # Headers de threading pour réponse correcte
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
            if references:
                msg["References"] = references
            elif in_reply_to:
                msg["References"] = in_reply_to
            
            # Header personnalisé pour identifier les drafts Mail2RAG
            msg["X-Mail2RAG-Draft"] = "true"
            msg["X-Mail2RAG-OriginalUID"] = str(original_uid) if original_uid else ""
            msg["X-Mail2RAG-CreatedAt"] = datetime.utcnow().isoformat()
            
            # Corps du message (HTML)
            html_part = MIMEText(body_html, "html", "utf-8")
            msg.attach(html_part)
            
            # Trouver le dossier Drafts
            drafts_folder = self._find_drafts_folder()
            if not drafts_folder:
                self.logger.error(
                    "❌ Impossible de trouver le dossier Drafts IMAP"
                )
                return False
            
            # Créer le brouillon via IMAP APPEND
            success = self._append_to_drafts(msg, drafts_folder)
            
            if success:
                self.logger.info(
                    "📝 Brouillon créé dans '%s' pour %s (sujet: %s)",
                    drafts_folder,
                    to_email,
                    subject[:50],
                )
            
            return success
            
        except Exception as e:
            self.logger.error(
                "❌ Erreur lors de la création du brouillon: %s",
                e,
                exc_info=True,
            )
            return False

    def move_to_processed(self, uid: int) -> bool:
        """
        Déplace un email vers le dossier 'En cours'.
        
        Crée le dossier s'il n'existe pas.
        
        Args:
            uid: UID de l'email à déplacer
            
        Returns:
            True si déplacement réussi, False sinon
        """
        try:
            self.mail_service.ensure_connection()
            server = self.mail_service.server
            
            if not server:
                self.logger.error("❌ Connexion IMAP non disponible")
                return False
            
            # Créer le dossier si nécessaire
            if not self._folder_exists(self.processed_folder):
                self._create_folder(self.processed_folder)
            
            # Sélectionner INBOX (source)
            source_folder = self.mail_service.imap_folder
            server.select_folder(source_folder)
            
            # Déplacer l'email
            try:
                # Essayer MOVE (extension IMAP)
                server.move([uid], self.processed_folder)
                self.logger.info(
                    "📨 Email UID %s déplacé vers '%s'",
                    uid,
                    self.processed_folder,
                )
                return True
            except Exception:
                # Fallback: COPY + DELETE
                server.copy([uid], self.processed_folder)
                server.delete_messages([uid])
                server.expunge()
                self.logger.info(
                    "📨 Email UID %s copié+supprimé vers '%s'",
                    uid,
                    self.processed_folder,
                )
                return True
                
        except Exception as e:
            self.logger.error(
                "❌ Erreur lors du déplacement de l'email UID %s: %s",
                uid,
                e,
                exc_info=True,
            )
            return False

    def _find_drafts_folder(self) -> Optional[str]:
        """
        Détecte automatiquement le nom du dossier Drafts.
        
        Vérifie d'abord la config, puis parcourt les candidats courants.
        
        Returns:
            Nom du dossier Drafts ou None si non trouvé
        """
        # Utiliser le cache si disponible
        if self._detected_drafts_folder:
            return self._detected_drafts_folder
        
        # Configuration explicite
        if self.drafts_folder:
            self._detected_drafts_folder = self.drafts_folder
            return self.drafts_folder
        
        try:
            self.mail_service.ensure_connection()
            server = self.mail_service.server
            
            if not server:
                return None
            
            # Lister les dossiers existants
            folders = server.list_folders()
            folder_names = [f[2] for f in folders]  # (flags, delimiter, name)
            
            self.logger.debug("Dossiers IMAP disponibles: %s", folder_names)
            
            # Chercher parmi les candidats
            for candidate in DRAFT_FOLDER_CANDIDATES:
                if candidate in folder_names:
                    self._detected_drafts_folder = candidate
                    self.logger.info(
                        "✅ Dossier Drafts détecté: '%s'",
                        candidate,
                    )
                    return candidate
                
                # Recherche insensible à la casse
                for folder in folder_names:
                    if folder.lower() == candidate.lower():
                        self._detected_drafts_folder = folder
                        self.logger.info(
                            "✅ Dossier Drafts détecté (case-insensitive): '%s'",
                            folder,
                        )
                        return folder
            
            self.logger.warning(
                "⚠️ Aucun dossier Drafts trouvé parmi: %s",
                DRAFT_FOLDER_CANDIDATES,
            )
            return None
            
        except Exception as e:
            self.logger.error(
                "❌ Erreur lors de la détection du dossier Drafts: %s",
                e,
                exc_info=True,
            )
            return None

    def _append_to_drafts(
        self,
        message: MIMEMultipart,
        drafts_folder: str,
    ) -> bool:
        """
        Ajoute un message au dossier Drafts IMAP avec le flag \\Draft.
        
        Args:
            message: Message MIME à ajouter
            drafts_folder: Nom du dossier Drafts
            
        Returns:
            True si succès, False sinon
        """
        try:
            self.mail_service.ensure_connection()
            server = self.mail_service.server
            
            if not server:
                return False
            
            # APPEND avec flags \Draft et \Seen
            server.append(
                drafts_folder,
                message.as_bytes(),
                flags=["\\Draft", "\\Seen"],
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "❌ Erreur IMAP APPEND vers '%s': %s",
                drafts_folder,
                e,
                exc_info=True,
            )
            return False

    def _folder_exists(self, folder_name: str) -> bool:
        """Vérifie si un dossier IMAP existe."""
        try:
            self.mail_service.ensure_connection()
            server = self.mail_service.server
            
            if not server:
                return False
            
            folders = server.list_folders()
            folder_names = [f[2] for f in folders]
            return folder_name in folder_names
            
        except Exception:
            return False

    def _create_folder(self, folder_name: str) -> bool:
        """Crée un dossier IMAP."""
        try:
            self.mail_service.ensure_connection()
            server = self.mail_service.server
            
            if not server:
                return False
            
            server.create_folder(folder_name)
            self.logger.info("📁 Dossier IMAP '%s' créé", folder_name)
            return True
            
        except Exception as e:
            self.logger.error(
                "❌ Erreur lors de la création du dossier '%s': %s",
                folder_name,
                e,
            )
            return False

    def _get_domain(self) -> str:
        """Extrait le domaine de l'adresse email configurée."""
        email = self.config.imap_user or ""
        if "@" in email:
            return email.split("@")[1]
        return "mail2rag.local"
