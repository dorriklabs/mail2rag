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
        self.slack_webhook_url = getattr(config, "slack_webhook_url", None)
        self.google_chat_webhook_url = getattr(config, "google_chat_webhook_url", None)

    def send_notification(self, title: str, text: str, facts: Optional[dict] = None) -> bool:
        """
        Envoie une notification formatée vers tous les webhooks configurés (Teams, Slack, Google Chat).
        Retourne True si au moins une notification a été envoyée avec succès.
        """
        success = False
        if self.teams_webhook_url:
            success = self._send_teams(title, text, facts) or success
            
        if self.slack_webhook_url:
            success = self._send_slack(title, text, facts) or success
            
        if self.google_chat_webhook_url:
            success = self._send_google_chat(title, text, facts) or success
            
        return success

    def _send_teams(self, title: str, text: str, facts: Optional[dict] = None) -> bool:
        """
        Envoie une notification formatée vers un webhook Teams.
        Utilise le format 'MessageCard' historique, très robuste pour les webhooks simples.
        """
        if not self.teams_webhook_url:
            return False
            
        # Format Adaptive Card (requis pour les nouveaux Webhooks Teams / Power Automate)
        facts_list = [{"title": k, "value": v} for k, v in (facts or {}).items()]
        
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": title,
                                "weight": "Bolder",
                                "size": "Medium"
                            },
                            {
                                "type": "TextBlock",
                                "text": text,
                                "wrap": True
                            }
                        ] + ([{
                            "type": "FactSet",
                            "facts": facts_list
                        }] if facts_list else [])
                    }
                }
            ]
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

    def _send_slack(self, title: str, text: str, facts: Optional[dict] = None) -> bool:
        """Envoie une notification formatée vers un webhook Slack."""
        facts_text = "\n".join([f"*{k}*: {v}" for k, v in (facts or {}).items()])
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": title,
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{text}\n\n{facts_text}"
                    }
                }
            ]
        }
        try:
            resp = requests.post(self.slack_webhook_url, json=payload, timeout=5)
            resp.raise_for_status()
            logger.info("✅ Notification Slack envoyée avec succès : %s", title)
            return True
        except requests.exceptions.HTTPError as e:
            err_text = e.response.text if e.response is not None else str(e)
            logger.error("❌ Erreur HTTP Slack (Payload rejeté) : %s", err_text)
            return False
        except Exception as e:
            logger.error("❌ Erreur de connexion au Webhook Slack : %s", e)
            return False

    def _send_google_chat(self, title: str, text: str, facts: Optional[dict] = None) -> bool:
        """Envoie une notification formatée vers un webhook Google Chat."""
        widgets = [{"textParagraph": {"text": text}}]
        if facts:
            for k, v in facts.items():
                widgets.append({"keyValue": {"topLabel": k, "content": v}})
                
        payload = {
            "cards": [{
                "header": {"title": title},
                "sections": [{"widgets": widgets}]
            }]
        }
        try:
            resp = requests.post(self.google_chat_webhook_url, json=payload, timeout=5)
            resp.raise_for_status()
            logger.info("✅ Notification Google Chat envoyée avec succès : %s", title)
            return True
        except requests.exceptions.HTTPError as e:
            err_text = e.response.text if e.response is not None else str(e)
            logger.error("❌ Erreur HTTP Google Chat (Payload rejeté) : %s", err_text)
            return False
        except Exception as e:
            logger.error("❌ Erreur de connexion au Webhook Google Chat : %s", e)
            return False
