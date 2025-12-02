import logging
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING, List

from imapclient import IMAPClient

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from config import Config


class MailService:
    """
    Service responsable des interactions IMAP/SMTP.

    - Connexion IMAP robuste avec reconnexion automatique.
    - Lecture des nouveaux messages à partir d'un UID donné.
    - Envoi de réponses ou d'emails synthétiques via SMTP.
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        self.server: Optional[IMAPClient] = None

        # Timeouts (en secondes).
        self.imap_timeout = getattr(config, "imap_timeout", 30)
        self.smtp_timeout = getattr(config, "smtp_timeout", 30)

        # Dossier IMAP à surveiller
        self.imap_folder = getattr(config, "imap_folder", "INBOX") or "INBOX"
        # Critère IMAP configurable (UNSEEN, ALL, ou critère avancé)
        self.imap_search_criteria = (
            getattr(config, "imap_search_criteria", "UNSEEN") or "UNSEEN"
        ).strip()

    # ------------------------------------------------------------------ #
    # IMAP (Réception des emails)
    # ------------------------------------------------------------------ #
    def _connect(self) -> None:
        """Établit une nouvelle connexion IMAP avec gestion d'erreurs fine."""
        try:
            logger.info(
                "Connexion IMAP à %s:%s (timeout=%ss, folder=%s)...",
                self.config.imap_server,
                self.config.imap_port,
                self.imap_timeout,
                self.imap_folder,
            )
            self.server = IMAPClient(
                self.config.imap_server,
                port=self.config.imap_port,
                ssl=True,
                timeout=self.imap_timeout,
            )
            self.server.login(self.config.imap_user, self.config.imap_password)
            logger.debug("Authentification IMAP réussie.")
        except IMAPClient.Error as e:
            logger.error("Échec connexion IMAP (protocole IMAP) : %s", e)
            self.server = None
            raise
        except (socket.timeout, socket.gaierror, OSError) as e:
            logger.error("Échec connexion IMAP (erreur réseau) : %s", e)
            self.server = None
            raise
        except Exception as e:
            logger.error(
                "Échec connexion IMAP (erreur inattendue) : %s", e, exc_info=True
            )
            self.server = None
            raise

    def ensure_connection(self) -> None:
        """
        Vérifie que la connexion IMAP est vivante, sinon tente une reconnexion.
        Laisse remonter les exceptions pour que la boucle principale puisse gérer.
        """
        if self.server is None:
            self._connect()
            return

        try:
            self.server.noop()
        except (IMAPClient.Error, socket.timeout, socket.error, OSError) as e:
            logger.warning(
                "Connexion IMAP perdue (%s), tentative de reconnexion...", e
            )
            self.server = None
            self._connect()

    def _build_search_criteria(self, last_uid: int) -> List[str]:
        """
        Construit la liste de critères IMAP à partir de la config et du last_uid.

        - IMAP_SEARCH_CRITERIA (ex: UNSEEN, ALL, critère avancé)
        - Filtre UID last_uid+1:* pour éviter de retraiter les anciens messages.
        """
        # Exemple: ["UNSEEN", "UID", "123:*"]
        criteria: List[str] = []

        user_criteria = (self.imap_search_criteria or "").strip()
        if user_criteria and user_criteria.upper() != "ALL":
            # On laisse IMAPClient splitter la chaîne (ex: 'UNSEEN FROM "foo"')
            criteria.append(user_criteria)

        # Filtre UID pour ne pas retraiter les anciens messages
        criteria.extend(["UID", f"{last_uid + 1}:*"])

        logger.debug("Critères IMAP utilisés pour la recherche : %r", criteria)
        return criteria

    def fetch_new_messages(self, last_uid: int) -> Dict[int, Any]:
        """
        Récupère les nouveaux messages dont l'UID est strictement supérieur à last_uid.

        Combine :
        - le critère IMAP configurable (IMAP_SEARCH_CRITERIA)
        - un filtre UID > last_uid côté client (sécurité supplémentaire)
        """
        self.ensure_connection()

        try:
            self.server.select_folder(self.imap_folder)
        except Exception as e:
            logger.error(
                "Erreur IMAP lors du select '%s' : %s",
                self.imap_folder,
                e,
                exc_info=True,
            )
            self.server = None
            raise

        criteria = self._build_search_criteria(last_uid)

        logger.debug("Recherche messages avec last_uid=%s", last_uid)
        try:
            messages = self.server.search(criteria)
        except Exception as e:
            logger.error("Erreur IMAP lors du search : %s", e, exc_info=True)
            self.server = None
            raise

        # Filtrage strict côté client pour éviter toute ré-ingestion
        new_uids = [uid for uid in messages if uid > last_uid]

        if new_uids:
            logger.info(
                "Trouvé %d nouveau(x) message(s) (UIDs: %s).",
                len(new_uids),
                new_uids,
            )
            try:
                return self.server.fetch(new_uids, ["RFC822"])
            except Exception as e:
                logger.error("Erreur IMAP lors du fetch : %s", e, exc_info=True)
                self.server = None
                raise

        if messages:
            logger.debug(
                "Aucun nouveau message > last_uid (UIDs retournés: %s).", messages
            )
        else:
            logger.debug("Aucun message correspondant aux critères IMAP.")
        return {}

    # ------------------------------------------------------------------ #
    # SMTP (Envoi des réponses)
    # ------------------------------------------------------------------ #
    def _send_message_smtp(self, msg: MIMEMultipart, log_context: str) -> bool:
        """
        Envoi générique d'un message SMTP avec gestion d'erreurs détaillée.
        Retourne True si succès, False sinon.
        """
        try:
            logger.debug(
                "Connexion SMTP à %s:%s (timeout=%ss) pour %s...",
                self.config.smtp_server,
                self.config.smtp_port,
                self.smtp_timeout,
                log_context,
            )
            with smtplib.SMTP(
                self.config.smtp_server,
                self.config.smtp_port,
                timeout=self.smtp_timeout,
            ) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)

            logger.info("✅ Email SMTP envoyé (%s)", log_context)
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error("❌ Échec authentification SMTP (%s) : %s", log_context, e)
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as e:
            logger.error("❌ Échec connexion SMTP (%s) : %s", log_context, e)
        except (socket.timeout, OSError) as e:
            logger.error("❌ Timeout / erreur réseau SMTP (%s) : %s", log_context, e)
        except smtplib.SMTPException as e:
            logger.error("❌ Erreur SMTP (%s) : %s", log_context, e, exc_info=True)
        except Exception as e:
            logger.error(
                "❌ Erreur SMTP inattendue (%s) : %s", log_context, e, exc_info=True
            )

        return False

    def send_reply(
        self,
        to_email: str,
        subject: str,
        body: str,
        is_html: bool = False,
    ) -> None:
        """
        Envoie une réponse à l'expéditeur original.
        """
        msg = MIMEMultipart()
        # Utiliser SMTP_FROM si renseigné, sinon smtp_user
        from_addr = getattr(self.config, "smtp_from", None) or self.config.smtp_user
        msg["From"] = from_addr
        msg["To"] = to_email
        msg["Subject"] = subject

        if is_html:
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg.attach(MIMEText(body, "plain", "utf-8"))

        self._send_message_smtp(msg, log_context=f"réponse à {to_email}")

    def send_synthetic_email(
        self,
        subject: str,
        body: str,
        attachment_paths: Optional[list] = None,
    ) -> bool:
        """
        Génère et envoie un email synthétique à la boîte RAG.
        Utilisé pour créer des emails à partir de documents uploadés manuellement.
        """
        from email.mime.base import MIMEBase
        from email import encoders
        import os

        msg = MIMEMultipart()
        from_addr = getattr(self.config, "smtp_from", None) or self.config.smtp_user
        msg["From"] = f"Mail2RAG System <{from_addr}>"
        msg["To"] = self.config.imap_user  # Envoi à soi-même (boîte RAG)
        msg["Subject"] = subject
        msg["X-Mail2RAG-Synthetic"] = "true"  # Header spécial pour identification

        # Corps du message
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Ajout des pièces jointes si fournies
        if attachment_paths:
            for file_path in attachment_paths:
                if not os.path.exists(file_path):
                    logger.warning("⚠️ Fichier introuvable pour PJ : %s", file_path)
                    continue

                try:
                    with open(file_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())

                    encoders.encode_base64(part)
                    filename = os.path.basename(file_path)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={filename}",
                    )
                    msg.attach(part)
                    logger.debug("📎 PJ attachée : %s", filename)
                except Exception as e:
                    logger.error(
                        "❌ Erreur attachement %s : %s",
                        file_path,
                        e,
                        exc_info=True,
                    )

        logger.debug("📧 Envoi email synthétique : %s", subject)
        success = self._send_message_smtp(
            msg, log_context=f"email synthétique '{subject}'"
        )
        return success
