import email
import re
from email.message import Message
from html import unescape
from typing import Any

from models import ParsedEmail
from services.utils import decode_email_header


class EmailParser:
    """
    Responsabilité : convertir la réponse IMAP brute en ParsedEmail.

    - construit l'objet email.message.Message
    - gère les encodages / charsets
    - choisit le bon corps (text/plain prioritaire, fallback sur HTML)
    - extrait les métadonnées utiles (sujet, from, to, cc, date, message-id)
    - détecte les emails synthétiques via l'en-tête X-Mail2RAG-Synthetic
    """

    def __init__(self, logger) -> None:
        self.logger = logger

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def parse(self, uid: int, message_data: Any) -> ParsedEmail:
        """
        Transforme un message IMAP brut (RFC822) en ParsedEmail.
        """
        msg = self._extract_message_object(uid, message_data)

        subject = decode_email_header(msg.get("Subject", ""))
        sender = decode_email_header(msg.get("From", ""))
        to_header = decode_email_header(msg.get("To", ""))
        cc_header = decode_email_header(msg.get("Cc", ""))
        real_date = msg.get("Date") or None
        msg_id = (msg.get("Message-ID") or "").strip() or None

        is_synthetic = msg.get("X-Mail2RAG-Synthetic", "").lower() == "true"

        if is_synthetic:
            self.logger.info(
                "📧 Email synthétique détecté UID %s | Sujet: %s",
                uid,
                subject,
            )
        else:
            self.logger.info(
                "📨 Traitement UID %s | Sujet: %s | De: %s",
                uid,
                subject,
                sender,
            )

        body = self._extract_body(uid, msg)

        return ParsedEmail(
            uid=uid,
            msg=msg,
            subject=subject,
            sender=sender,
            body=body,
            to=to_header or None,
            cc=cc_header or None,
            date=real_date,
            message_id=msg_id,
            is_synthetic=is_synthetic,
        )

    # ------------------------------------------------------------------ #
    # Helpers internes
    # ------------------------------------------------------------------ #
    def _extract_message_object(self, uid: int, message_data: Any) -> Message:
        """Récupère un objet email.message.Message à partir de la réponse IMAP."""
        if isinstance(message_data, dict):
            raw_msg = message_data.get(b"RFC822") or message_data.get("RFC822")
        else:
            raw_msg = message_data

        if raw_msg is None:
            self.logger.error(
                "UID %s : pas de section RFC822 dans message_data=%r",
                uid,
                message_data,
            )
            raise ValueError("Message IMAP sans section RFC822")

        if isinstance(raw_msg, (bytes, bytearray)):
            return email.message_from_bytes(raw_msg)
        if isinstance(raw_msg, Message):
            return raw_msg
        if isinstance(raw_msg, str):
            return email.message_from_string(raw_msg)

        raise TypeError(
            f"Type inattendu pour raw_msg (UID={uid}) : {type(raw_msg)}"
        )

    def _extract_body(self, uid: int, msg: Message) -> str:
        """
        Récupère le corps texte d'un message :
        - privilégie text/plain
        - fallback sur text/html (converti en texte)
        """
        if msg.is_multipart():
            plain_chunks = []
            html_chunks = []

            for part in msg.walk():
                ctype = (part.get_content_type() or "").lower()
                disp = (part.get("Content-Disposition") or "").lower()

                # Ignorer les pièces jointes
                if "attachment" in disp:
                    continue

                if ctype == "text/plain":
                    plain_chunks.append(self._decode_text_part(uid, part))
                elif ctype == "text/html":
                    html_chunks.append(self._decode_html_part(uid, part))

            if plain_chunks:
                return "".join(plain_chunks).strip()
            if html_chunks:
                return "".join(html_chunks).strip()
            return ""

        # Non-multipart
        ctype = (msg.get_content_type() or "").lower()
        if ctype == "text/plain":
            return self._decode_text_part(uid, msg).strip()
        if ctype == "text/html":
            return self._decode_html_part(uid, msg).strip()
        # Fallback
        return self._decode_text_part(uid, msg).strip()

    def _decode_part_with_charset(self, uid: int, part: Message) -> str:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""

        charset = part.get_content_charset() or "utf-8"

        try:
            return payload.decode(charset, errors="replace")
        except Exception:
            self.logger.warning(
                "Charset '%s' problématique, fallback utf-8/latin-1 pour UID %s",
                charset,
                uid,
            )

        for enc in ("utf-8", "latin-1"):
            try:
                return payload.decode(enc, errors="replace")
            except Exception:
                continue

        return ""

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Conversion simple HTML -> texte (sans dépendance externe)."""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return unescape(text).strip()

    def _decode_text_part(self, uid: int, part: Message) -> str:
        return self._decode_part_with_charset(uid, part)

    def _decode_html_part(self, uid: int, part: Message) -> str:
        html = self._decode_part_with_charset(uid, part)
        return self._html_to_text(html)
