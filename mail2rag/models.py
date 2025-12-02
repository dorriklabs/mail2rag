from dataclasses import dataclass
from email.message import Message
from typing import Optional, Dict


@dataclass
class ParsedEmail:
    """
    Représentation normalisée d'un email IMAP.

    Contient les principaux champs utilisés par Mail2RAG :
    - métadonnées (uid, sujet, expéditeur, destinataires, date, message-id)
    - corps texte nettoyé (plain ou HTML converti)
    - drapeau synthétique (emails injectés par programme)
    - message brut (pour parcours multipart / pièces jointes)
    """
    uid: int
    msg: Message

    subject: str
    sender: str
    body: str

    to: Optional[str]
    cc: Optional[str]
    date: Optional[str]
    message_id: Optional[str]

    is_synthetic: bool = False

    @property
    def email_data(self) -> Dict[str, str]:
        """
        Vue minimale utilisée par le Router :
        sujet, expéditeur, corps.
        """
        return {
            "subject": self.subject or "",
            "from": self.sender or "",
            "body": self.body or "",
        }
