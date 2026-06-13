import logging
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from imapclient import IMAPClient
from pathlib import Path

from .base import BaseMailProvider

if TYPE_CHECKING:
    from config import Config
    from models import ParsedEmail

logger = logging.getLogger(__name__)

class ImapSmtpProvider(BaseMailProvider):
    def __init__(self, config: "Config") -> None:
        self.config = config
        self.server: Optional[IMAPClient] = None
        self.imap_timeout = getattr(config, "imap_timeout", 30)
        self.smtp_timeout = getattr(config, "smtp_timeout", 30)
        self.imap_folder = getattr(config, "imap_folder", "INBOX") or "INBOX"
        self.imap_search_criteria = (getattr(config, "imap_search_criteria", "UNSEEN") or "UNSEEN").strip()

    def _connect(self) -> None:
        try:
            logger.info("Connexion IMAP à %s:%s...", self.config.imap_server, self.config.imap_port)
            self.server = IMAPClient(self.config.imap_server, port=self.config.imap_port, ssl=True, timeout=self.imap_timeout)
            self.server.login(self.config.imap_user, self.config.imap_password)
            logger.debug("Authentification IMAP réussie.")
        except Exception as e:
            logger.error("Échec connexion IMAP : %s", e)
            self.server = None
            raise

    def ensure_connection(self) -> None:
        if self.server is None:
            self._connect()
            return
        try:
            self.server.noop()
        except Exception as e:
            logger.warning("Connexion IMAP perdue (%s), reconnexion...", e)
            self.server = None
            self._connect()

    def fetch_new_messages(self, last_uid: int) -> Dict[int, Any]:
        self.ensure_connection()
        self.server.select_folder(self.imap_folder)
        criteria = []
        if self.imap_search_criteria and self.imap_search_criteria.upper() != "ALL":
            criteria.append(self.imap_search_criteria)
        criteria.extend(["UID", f"{last_uid + 1}:*"])
        messages = self.server.search(criteria)
        if not messages:
            return {}
        return self.server.fetch(messages, ["RFC822"])

    def folder_exists(self, folder_name: str) -> bool:
        self.ensure_connection()
        return self.server.folder_exists(folder_name)

    def create_folder(self, folder_name: str) -> bool:
        self.ensure_connection()
        if not self.folder_exists(folder_name):
            self.server.create_folder(folder_name)
        return True

    def move_message(self, uid: int, dest_folder: str, source_folder: Optional[str] = None) -> bool:
        self.ensure_connection()
        if source_folder:
            self.server.select_folder(source_folder)
        else:
            self.server.select_folder(self.imap_folder)
        self.create_folder(dest_folder)
        self.server.move([uid], dest_folder)
        return True

    def send_reply(self, to_email: str, subject: str, body: str, is_html: bool = False, original_message_id: str = None) -> bool:
        msg = MIMEMultipart()
        msg["From"] = getattr(self.config, "smtp_from", None) or self.config.smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id
        msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))
        return self._send_message_smtp(msg, "send_reply")

    def send_combined_email(self, service_email: str, client_email: str, subject: str, body_html: str, original_message_id: str = None) -> bool:
        msg = MIMEMultipart()
        msg["From"] = getattr(self.config, "smtp_from", None) or self.config.smtp_user
        msg["To"] = service_email
        msg["Reply-To"] = client_email
        msg["Subject"] = subject
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        return self._send_message_smtp(msg, "send_combined_email")

    def forward_parsed_email(self, parsed_email: "ParsedEmail", to_email: str) -> bool:
        msg = MIMEMultipart()
        msg["From"] = getattr(self.config, "smtp_from", None) or self.config.smtp_user
        msg["To"] = to_email
        msg["Subject"] = f"Fwd: {parsed_email.subject}"
        body = f"--- Cet email a été transféré automatiquement par l'IA Mail2RAG ---\n\n{parsed_email.body}"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if parsed_email.msg.is_multipart():
            for part in parsed_email.msg.walk():
                if part.get_content_maintype() == "multipart" or part.get("Content-Disposition") is None:
                    continue
                msg.attach(part)
        return self._send_message_smtp(msg, "forward_parsed_email")

    def send_synthetic_email(self, to_email: str, subject: str, text_content: str, attachment_paths: List[str] = None) -> bool:
        msg = MIMEMultipart()
        msg["From"] = getattr(self.config, "smtp_from", None) or self.config.smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        if attachment_paths:
            import mimetypes
            from email.mime.application import MIMEApplication
            from email.mime.image import MIMEImage
            for path in attachment_paths:
                p = Path(path)
                if not p.is_file():
                    continue
                ctype, _ = mimetypes.guess_type(str(p))
                maintype = ctype.split("/")[0] if ctype else "application"
                with p.open("rb") as f:
                    content = f.read()
                if maintype == "image":
                    part = MIMEImage(content, name=p.name)
                else:
                    part = MIMEApplication(content, name=p.name)
                part.add_header("Content-Disposition", f"attachment; filename={p.name}")
                msg.attach(part)
        return self._send_message_smtp(msg, "send_synthetic_email")

    def _send_message_smtp(self, msg: MIMEMultipart, log_context: str) -> bool:
        try:
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=self.smtp_timeout) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error("Échec SMTP (%s): %s", log_context, e)
            return False

    def append_message_to_folder(self, folder: str, msg: bytes, flags: tuple = ()) -> bool:
        self.ensure_connection()
        self.create_folder(folder)
        self.server.append(folder, msg, flags=flags)
        return True

    def disconnect(self) -> None:
        if self.server:
            try:
                self.server.logout()
            except Exception:
                pass
            self.server = None
