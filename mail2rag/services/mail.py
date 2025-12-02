import logging
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from imapclient import IMAPClient

logger = logging.getLogger(__name__)


class MailService:
    def __init__(self, config):
        self.config = config
        self.server = None

        # Timeouts (en secondes). Si le Config n'a pas ces attributs,
        # on utilise des valeurs raisonnables par défaut.
        self.imap_timeout = getattr(config, "imap_timeout", 30)
        self.smtp_timeout = getattr(config, "smtp_timeout", 30)

    # ============================
    #  IMAP (Réception des emails)
    # ============================
    def _connect(self):
        """Établit une nouvelle connexion IMAP avec gestion d'erreurs fine."""
        try:
            logger.info(
                f"Connexion IMAP à {self.config.imap_server}:"
                f"{self.config.imap_port} (timeout={self.imap_timeout}s)..."
            )
            # timeout est supporté par IMAPClient (propage vers la socket interne)
            self.server = IMAPClient(
                self.config.imap_server,
                port=self.config.imap_port,
                ssl=True,
                timeout=self.imap_timeout,
            )
            self.server.login(self.config.imap_user, self.config.imap_password)
            logger.debug("Authentification IMAP réussie.")
        except IMAPClient.Error as e:
            logger.error(f"Échec connexion IMAP (protocole IMAP) : {e}")
            self.server = None
            raise
        except (socket.timeout, socket.gaierror, OSError) as e:
            logger.error(f"Échec connexion IMAP (erreur réseau) : {e}")
            self.server = None
            raise
        except Exception as e:
            logger.error(f"Échec connexion IMAP (erreur inattendue) : {e}", exc_info=True)
            self.server = None
            raise

    def ensure_connection(self):
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
            logger.warning(f"Connexion IMAP perdue ({e}), tentative de reconnexion...")
            self.server = None
            self._connect()

    def fetch_new_messages(self, last_uid):
        """
        Récupère les nouveaux messages dont l'UID est strictement supérieur à last_uid.
        Peut lever une exception en cas d'erreur IMAP, gérée par la boucle principale.
        """
        self.ensure_connection()

        try:
            self.server.select_folder("INBOX")
        except Exception as e:
            logger.error(f"Erreur IMAP lors du select INBOX : {e}", exc_info=True)
            # On invalide la connexion pour forcer une reconnexion au prochain tour
            self.server = None
            raise

        logger.debug(f"Recherche messages avec UID > {last_uid}")
        try:
            # Certains serveurs retournent le dernier UID même si on demande UID+1:*
            messages = self.server.search(["UID", f"{last_uid + 1}:*"])
        except Exception as e:
            logger.error(f"Erreur IMAP lors du search : {e}", exc_info=True)
            self.server = None
            raise

        # Filtrage strict côté client pour éviter de re-télécharger le dernier message
        new_uids = [uid for uid in messages if uid > last_uid]

        if new_uids:
            logger.info(
                f"Trouvé {len(new_uids)} nouveau(x) message(s) "
                f"(UIDs: {new_uids})."
            )
            try:
                return self.server.fetch(new_uids, ["RFC822"])
            except Exception as e:
                logger.error(f"Erreur IMAP lors du fetch : {e}", exc_info=True)
                self.server = None
                raise
        else:
            if messages:
                logger.debug(f"Ignoré {len(messages)} message(s) (UID <= {last_uid}).")
            else:
                logger.debug("Aucun nouveau message.")
            return {}

    # ===========================
    #  SMTP (Envoi des réponses)
    # ===========================
    def _send_message_smtp(self, msg, log_context: str) -> bool:
        """
        Envoi générique d'un message SMTP avec gestion d'erreurs détaillée.
        Retourne True si succès, False sinon.
        """
        try:
            logger.debug(
                f"Connexion SMTP à {self.config.smtp_server}:"
                f"{self.config.smtp_port} (timeout={self.smtp_timeout}s) "
                f"pour {log_context}..."
            )
            # Utilisation d'un context manager pour garantir la fermeture
            with smtplib.SMTP(
                self.config.smtp_server,
                self.config.smtp_port,
                timeout=self.smtp_timeout,
            ) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)

            logger.info(f"✅ Email envoyé ({log_context})")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(
                f"❌ Échec authentification SMTP ({log_context}) : {e}"
            )
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as e:
            logger.error(
                f"❌ Échec connexion SMTP ({log_context}) : {e}"
            )
        except (socket.timeout, OSError) as e:
            logger.error(
                f"❌ Timeout / erreur réseau SMTP ({log_context}) : {e}"
            )
        except smtplib.SMTPException as e:
            logger.error(
                f"❌ Erreur SMTP ({log_context}) : {e}",
                exc_info=True,
            )
        except Exception as e:
            logger.error(
                f"❌ Erreur SMTP inattendue ({log_context}) : {e}",
                exc_info=True,
            )

        return False

    def send_reply(self, to_email, subject, body, is_html=False):
        """
        Envoie une réponse à l'expéditeur original.
        """
        msg = MIMEMultipart()
        msg["From"] = self.config.smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject

        if is_html:
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg.attach(MIMEText(body, "plain", "utf-8"))

        self._send_message_smtp(msg, log_context=f"réponse à {to_email}")

    def send_synthetic_email(self, subject, body, attachment_paths=None):
        """
        Génère et envoie un email synthétique à la boîte RAG.
        Utilisé pour créer des emails à partir de documents uploadés manuellement.
        """
        from email.mime.base import MIMEBase
        from email import encoders
        import os

        msg = MIMEMultipart()
        msg["From"] = f"Mail2RAG System <{self.config.smtp_user}>"
        msg["To"] = self.config.imap_user  # Envoi à soi-même (boîte RAG)
        msg["Subject"] = subject
        msg["X-Mail2RAG-Synthetic"] = "true"  # Header spécial pour identification

        # Corps du message
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Ajout des pièces jointes si fournies
        if attachment_paths:
            for file_path in attachment_paths:
                if not os.path.exists(file_path):
                    logger.warning(f"⚠️ Fichier introuvable pour PJ : {file_path}")
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
                    logger.debug(f"   📎 PJ attachée : {filename}")
                except Exception as e:
                    logger.error(
                        f"❌ Erreur attachement {file_path}: {e}",
                        exc_info=True,
                    )

        logger.debug(f"📧 Envoi email synthétique : {subject}")
        success = self._send_message_smtp(
            msg, log_context=f"email synthétique '{subject}'"
        )
        return success
