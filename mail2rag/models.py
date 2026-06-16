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

from typing import List, Dict, Any
from pydantic import BaseModel, Field

class ExtractedPage(BaseModel):
    page_number: int
    page_hash: str
    text: str
    char_count: int
    quality_score: float
    extraction_method: str  # 'pymupdf', 'tika', 'mixed'
    vision_used: bool
    source_type: str        # ex: 'pdf_scan'
    metadata: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

class ExtractedDocument(BaseModel):
    schema_version: str = "1.0"
    document_id: str
    filename: str
    file_hash: str
    total_pages: int
    source_type: str
    pages: List[ExtractedPage]
    global_metadata: Dict[str, Any] = Field(default_factory=dict)
