import logging
import requests
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

class NotificationService:
    """Service d'envoi de notifications (Teams, etc.)."""
    
    def __init__(self, config: "Config"):
        self.config = config
        self.teams_webhook_url = getattr(config, "teams_webhook_url", None)

    def send_teams_notification(self, title: str, text: str, facts: Optional[dict] = None) -> bool:
        """
        Envoie une notification formatée vers un webhook Teams.
        Utilise le format 'MessageCard' historique, très robuste pour les webhooks simples.
        """
        if not self.teams_webhook_url:
            return False
            
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": title,
            "sections": [{
                "activityTitle": title,
                "text": text,
                "facts": [{"name": k, "value": v} for k, v in (facts or {}).items()]
            }]
        }

        try:
            resp = requests.post(self.teams_webhook_url, json=payload, timeout=5)
            resp.raise_for_status()
            logger.info("✅ Notification Teams envoyée avec succès : %s", title)
            return True
        except requests.exceptions.HTTPError as e:
            err_text = e.response.text if e.response is not None else str(e)
            logger.error("❌ Erreur HTTP Teams (Payload rejeté) : %s", err_text)
            return False
        except Exception as e:
            logger.error("❌ Erreur de connexion au Webhook Teams : %s", e)
            return False
