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
        notification_service=None,
        support_draft_service=None,
    ):
        self.config = config
        self.logger = logger_instance
        self.mail_service = mail_service
        self.cleaner = cleaner
        self.router = router
        self.notification_service = notification_service
        self.support_draft_service = support_draft_service

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
            
            # 1. Générer une suggestion IA si le service est disponible
            ai_suggestion_html = None
            dynamic_attachments = None
            if self.support_draft_service:
                # Résoudre le vrai nom du workspace (slug) pour le service cible
                target_workspace = self.router.determine_workspace({"from": target_email, "subject": "", "body": ""})
                # Prendre le premier si multiple
                target_workspace = target_workspace.split(",")[0] if "," in target_workspace else target_workspace
                
                self.logger.info("🤖 Dispatch IA : Génération d'une suggestion IA pour %s (workspace: %s)...", matched_folder, target_workspace)
                ai_suggestion_html, ai_text = self.support_draft_service.generate_ai_suggestion_html(email, target_workspace)
                
                if ai_text:
                    from email.message import EmailMessage
                    eml = EmailMessage()
                    eml["Subject"] = f"Re: {email.subject}"
                    eml["To"] = email.sender
                    
                    import email.utils
                    date_str = email.date or email.utils.formatdate(localtime=True)
                    draft_body = f"{ai_text.strip()}\n\n"
                    draft_body += f"Le {date_str}, {email.sender} a écrit :\n"
                    
                    if email.body:
                        quoted_body = "\n".join(f"> {line}" for line in email.body.split("\n"))
                        draft_body += f"{quoted_body}\n"
                        
                    eml.set_content(draft_body)
                    dynamic_attachments = [("reponse_ia.eml", eml.as_bytes(), "message/rfc822")]

            # 2. Transférer l'e-mail via SMTP avec la suggestion injectée en HTML et potentiellement la PJ dynamique
            forwarded = self.mail_service.forward_parsed_email(email, target_email, prefix_html=ai_suggestion_html, dynamic_attachments=dynamic_attachments)
            
            if forwarded:
                # 3. Archiver l'original dans IMAP pour ne plus le traiter
                archive_folder = getattr(self.config, "semantic_dispatch_archive_folder", "Dispatch-Archive")
                self.mail_service.move_message(email.uid, archive_folder)

                # 3. Notification Teams, Slack, Google Chat
                if self.notification_service:
                    self.notification_service.send_notification(
                        title="Nouveau courrier trié",
                        text=f"Le courrier de **{email.sender}** a été transféré au service **{matched_folder}**.\n\nSujet : *{email.subject}*",
                        facts={
                            "Expéditeur": email.sender,
                            "Sujet": email.subject,
                            "Service Cible": matched_folder
                        }
                    )
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
