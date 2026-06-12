"""
Service de Dispatch Sémantique.
Analyse les emails, détermine le service cible via LLM, transfère l'email par SMTP,
puis déplace l'original dans un dossier d'archive IMAP.
"""
import logging
import requests
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from config import Config
    from services.mail import MailService
    from services.cleaner import CleanerService
    from services.router import RouterService
    from models import ParsedEmail

logger = logging.getLogger(__name__)

class DispatchService:
    """
    Détermine le service cible d'un email en utilisant l'IA,
    puis le déplace dans le dossier IMAP correspondant.
    """
    
    def __init__(
        self,
        config: "Config",
        logger_instance: logging.Logger,
        mail_service: "MailService",
        cleaner: "CleanerService",
        router: "RouterService",
    ):
        self.config = config
        self.logger = logger_instance
        self.mail_service = mail_service
        self.cleaner = cleaner
        self.router = router

    def handle_dispatch(self, email: "ParsedEmail") -> bool:
        """
        Analyse l'email, le transfère au bon service par SMTP, et l'archive en IMAP.
        Retourne True s'il a été traité, False s'il reste dans INBOX.
        """
        mapping = self.router.semantic_dispatch_mapping
        if not mapping:
            return False

        folders = list(mapping.keys())
        cleaned_body = self.cleaner.clean_body(email.body, subject=email.subject)
        predicted_folder = self._predict_folder(email.subject, cleaned_body, folders)
        
        if not predicted_folder or predicted_folder.upper() == "INBOX":
            self.logger.debug("Dispatch IA : Email %s reste dans INBOX", email.uid)
            return False
            
        # Tolérance sur la casse ou les espaces ajoutés par le LLM
        matched_folder = next((f for f in folders if f.lower() == predicted_folder.lower()), None)
            
        if matched_folder:
            target_email = mapping[matched_folder]
            self.logger.info("🎯 Dispatch IA : Transfert UID %s vers %s (%s)", email.uid, matched_folder, target_email)
            
            # 1. Transférer l'e-mail via SMTP
            forwarded = self.mail_service.forward_parsed_email(email, target_email)
            
            if forwarded:
                # 2. Archiver l'original dans IMAP pour ne plus le traiter
                archive_folder = getattr(self.config, "semantic_dispatch_archive_folder", "Dispatch-Archive")
                self.mail_service.move_message(email.uid, archive_folder)
                return True
            else:
                self.logger.error("❌ Dispatch IA : Échec du transfert SMTP pour l'UID %s. L'e-mail reste dans INBOX.", email.uid)
                return False
            
        self.logger.warning(
            "⚠️ Dispatch IA : Le LLM a répondu '%s' qui n'est pas dans %s. L'email reste dans INBOX.", 
            predicted_folder, 
            folders
        )
        return False

    def _predict_folder(self, subject: str, body: str, folders: list[str]) -> str:
        prompt = (
            "Tu es un assistant de tri strict et précis.\n"
            f"Ton rôle est de classer le mail suivant dans l'un de ces dossiers : {', '.join(folders)}, ou INBOX s'il ne correspond à aucun d'entre eux.\n"
            "Tu dois répondre UNIQUEMENT avec le nom exact du dossier, sans guillemets, sans politesse et sans ponctuation.\n\n"
            f"Sujet : {subject}\n"
            f"Message : {body[:1500]}"
        )
        
        try:
            payload = {
                "model": self.config.ai_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 20,
            }
            
            resp = requests.post(
                self.config.llm_api_url,
                json=payload,
                timeout=self.config.llm_timeout,
                headers={"Authorization": f"Bearer {self.config.ai_api_key}"}
            )
            
            if resp.ok:
                data = resp.json()
                choice = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                # Nettoyer d'éventuels points, guillemets, markdown, etc.
                choice = choice.strip(" \".'[]*`\n")
                return choice
            else:
                self.logger.error("Erreur HTTP Dispatch IA: %s", resp.text)
        except Exception as e:
            self.logger.error("Erreur Dispatch IA appel LLM: %s", e)
            
        return "INBOX"
