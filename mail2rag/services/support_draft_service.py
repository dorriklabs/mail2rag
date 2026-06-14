"""
Service principal du mode Support Draft.

Responsabilités :
- Orchestration du workflow complet de traitement des demandes support
- Recherche RAG et calcul de confiance
- Génération de réponse avec style configuré
- Délégation de la création du draft
- Tracking d'utilisation pour SaaS
"""

import logging
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config
    from services.mail import MailService
    from services.draft_service import DraftService
    from services.router import RouterService
    from services.cleaner import CleanerService
    from services.email_renderer import EmailRenderer
    from services.usage_tracker import UsageTracker
    from models import ParsedEmail

logger = logging.getLogger(__name__)


# Seuils de confiance par défaut
DEFAULT_CONFIDENCE_THRESHOLDS = {
    "none": 0.3,
    "low": 0.5,
    "medium": 0.7,
}

# Templates de style par défaut
DEFAULT_RESPONSE_STYLE = {
    "tone": "professional",
    "language": "fr",
    "greeting": "Bonjour,",
    "signature": "Cordialement,\nL'équipe Support",
}


class SupportDraftService:
    """
    Service principal du mode Support Draft.
    
    Orchestre le workflow complet :
    1. Réception d'une demande client
    2. Recherche dans la KB
    3. Génération d'une réponse avec le style configuré
    4. Création d'un brouillon dans le dossier Drafts
    5. Déplacement de l'email vers "En cours"
    """

    def __init__(
        self,
        config: "Config",
        logger_instance: logging.Logger,
        mail_service: "MailService",
        draft_service: "DraftService",
        router: "RouterService",
        cleaner: "CleanerService",
        email_renderer: "EmailRenderer",
        usage_tracker: Optional["UsageTracker"] = None,
        notification_service: Optional["NotificationService"] = None,
    ):
        """
        Initialise le service Support Draft.
        
        Args:
            config: Configuration de l'application
            logger_instance: Logger pour les messages
            mail_service: Service mail pour les opérations IMAP/SMTP
            draft_service: Service de création de brouillons
            router: Service de routage (détermine le workspace)
            cleaner: Service de nettoyage du corps des emails
            email_renderer: Renderer de templates HTML
            usage_tracker: Tracker d'utilisation SaaS (optionnel)
        """
        self.config = config
        self.logger = logger_instance
        self.mail_service = mail_service
        self.draft_service = draft_service
        self.router = router
        self.cleaner = cleaner
        self.email_renderer = email_renderer
        self.usage_tracker = usage_tracker
        self.notification_service = notification_service
        
        # Chemin des prompts de style
        self.prompts_dir = Path(config.prompts_dir) / "response_prompts"
        
        # Cache des prompts chargés
        self._style_prompts: Dict[str, str] = {}

    def handle_support_request(self, email: "ParsedEmail") -> None:
        """
        Traite une demande de support entrante.
        
        Workflow complet :
        1. Détermine le workspace et charge sa config
        2. Extrait et nettoie la question client
        3. Recherche dans la KB via RAG Proxy
        4. Calcule le score de confiance
        5. Génère la réponse avec le style configuré
        6. Crée le brouillon dans Drafts
        7. Déplace l'email vers "En cours"
        
        Args:
            email: Email parsé contenant la demande client
        """
        self.logger.info(
            "🎫 [Support Draft] Traitement de la demande UID %s de %s",
            email.uid,
            email.sender,
        )
        
        try:
            # 1. Déterminer le workspace
            workspace = self.router.determine_workspace(email.email_data)
            ws_config = self.config.workspace_settings.get(workspace, {})
            
            self.logger.debug(
                "📁 Workspace: %s, Config: %s",
                workspace,
                list(ws_config.keys()),
            )
            
            # 2. Extraire et nettoyer la question
            cleaned_body = self.cleaner.clean_body(email.body, subject=email.subject)
            query = self._build_query(email.subject, cleaned_body)
            
            # 3. Rechercher dans la KB
            search_results, ai_response = self._search_and_generate(
                query=query,
                workspace=workspace,
                ws_config=ws_config,
            )
            
            # 4. Calculer la confiance
            confidence_score, confidence_level = self._calculate_confidence(
                search_results,
                ws_config.get("confidence_thresholds", DEFAULT_CONFIDENCE_THRESHOLDS),
            )
            
            self.logger.info(
                "🎯 Confiance: %.2f (%s) - %d sources trouvées",
                confidence_score,
                confidence_level,
                len(search_results),
            )
            
            # 5. Générer le contenu du brouillon
            draft_content = self._build_draft_content(
                email=email,
                ai_response=ai_response,
                sources=search_results,
                confidence_level=confidence_level,
                confidence_score=confidence_score,
                ws_config=ws_config,
            )
            
            # 6. Créer le brouillon ou envoyer l'email combiné
            message_id = self._extract_message_id(email.email_data)
            
            # Récupérer l'adresse du service cible depuis le ws_config ou routing.json
            service_email = ws_config.get("target_email") or self.router.semantic_dispatch_mapping.get(workspace)
            
            success = self.draft_service.create_draft(
                to_email=email.sender,
                subject=email.subject or "Votre demande",
                body_html=draft_content,
                in_reply_to=message_id,
                references=message_id,
                original_uid=email.uid,
                service_email=service_email,
            )
            
            if success:
                # 7. Déplacer vers "En cours"
                self.draft_service.move_to_processed(email.uid)
                
                # Tracking SaaS
                if self.usage_tracker:
                    self.usage_tracker.track_email_processed(workspace)
                    self.usage_tracker.track_draft_created(workspace)
                    if ai_response:
                        self.usage_tracker.track_llm_call(workspace)
                
                self.logger.info(
                    "✅ [Support Draft] Brouillon créé pour UID %s",
                    email.uid,
                )

                if self.notification_service:
                    self.notification_service.send_notification(
                        title="Draft IA prêt à être validé",
                        text=f"Un brouillon a été préparé en réponse à **{email.sender}**.\n\nSujet : *{email.subject}*",
                        facts={
                            "Expéditeur": email.sender,
                            "Sujet": email.subject,
                            "Workspace": workspace
                        }
                    )
            else:
                self.logger.error(
                    "❌ [Support Draft] Échec création brouillon UID %s",
                    email.uid,
                )
                
        except Exception as e:
            self.logger.error(
                "❌ [Support Draft] Erreur traitement UID %s: %s",
                email.uid,
                e,
                exc_info=True,
            )

    def generate_ai_suggestion_html(self, email: "ParsedEmail", workspace: str) -> tuple[Optional[str], Optional[str], Optional[bytes], Optional[str]]:
        """
        Génère un encart HTML stylisé contenant la suggestion IA pour un e-mail donné.
        Retourne un tuple: (html_content, ai_response_text, sources_html_bytes, confidence_label).
        Ceci est utile pour inclure la suggestion dans le corps d'un e-mail transféré.
        """
        try:
            ws_config = self.config.workspace_settings.get(workspace, {})
            cleaned_body = self.cleaner.clean_body(email.body, subject=email.subject)
            query = self._build_query(email.subject, cleaned_body)

            search_results, ai_response = self._search_and_generate(
                query=query,
                workspace=workspace,
                ws_config=ws_config,
            )

            if not ai_response:
                return None, None, None, None

            confidence_score, confidence_level = self._calculate_confidence(
                search_results,
                ws_config.get("confidence_thresholds", DEFAULT_CONFIDENCE_THRESHOLDS),
            )
            
            # Si l'IA n'est pas sûre, on s'efface pour ne pas polluer l'agent
            if confidence_level in ("none", "low"):
                self.logger.info("🔇 Confiance %s : Annulation de la suggestion IA pour ne pas polluer l'agent.", confidence_level)
                return None, None, None, None
            
            confidence_labels = {
                "none": "Faible",
                "low": "Faible",
                "medium": "Moy",
                "high": "Bon",
            }
            confidence_label = confidence_labels.get(confidence_level, "Moy")

            import html
            import os

            # Construire l'encart HTML avec CSS inline
            html_content = f"""
            <div style="font-family: Arial, sans-serif; background-color: #f8f9fa; border: 1px solid #0d6efd; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                <h3 style="color: #0d6efd; margin-top: 0; margin-bottom: 15px; border-bottom: 1px solid #dee2e6; padding-bottom: 5px;">🤖 Suggestion de réponse IA ({confidence_label})</h3>
                <div style="font-size: 14px; line-height: 1.5; color: #333; margin-bottom: 20px;">
                    {html.escape(ai_response.strip()).replace(chr(10), '<br>')}
                </div>
            """

            sources_bytes = None

            # Ajouter les sources si présentes sous forme de fichier HTML séparé
            if search_results:
                sources_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sources utilisées par l'IA</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; color: #333; }
        h2 { color: #0d6efd; border-bottom: 1px solid #dee2e6; padding-bottom: 5px; }
        .source-list { list-style: none; padding: 0; }
        .source-item { margin-bottom: 15px; background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #0d6efd; }
        .source-title { font-weight: bold; font-size: 15px; color: #0d6efd; text-decoration: none; }
        .score { background-color: #e9ecef; padding: 2px 6px; border-radius: 10px; font-size: 12px; margin-left: 10px; color: #495057; }
        .excerpt { color: #555; font-style: italic; margin-top: 10px; font-size: 14px; white-space: pre-wrap; }
    </style>
</head>
<body>
    <h2>📚 Sources utilisées par l'IA</h2>
    <ul class="source-list">
"""

                archive_base = os.getenv("ARCHIVE_BASE_URL", "http://localhost:9102").rstrip('/')

                for res in search_results[:3]:
                    metadata = res.get("metadata", {})
                    filename = metadata.get("filename", "Document inconnu")
                    secure_id = metadata.get("secure_id")

                    # Nettoyer l'en-tête technique s'il est présent
                    chunk_text = res.get("text", "")
                    if not chunk_text and "payload" in res:
                        chunk_text = res["payload"].get("text", "")

                    if "Résumé :" in chunk_text and "IMAP_UID :" in chunk_text:
                        parts = chunk_text.split("\n\n", 1)
                        if len(parts) > 1:
                            chunk_text = parts[1].strip()

                    chunk_excerpt = html.escape(chunk_text[:300] + "..." if len(chunk_text) > 300 else chunk_text)

                    file_link = None
                    if secure_id:
                        file_link = f"{archive_base}/{secure_id}/{filename}"
                    else:
                        file_link = (metadata.get("link") or 
                                     metadata.get("url") or 
                                     metadata.get("archive_url") or
                                     metadata.get("source_url"))

                    sources_html += "<li class='source-item'>"

                    if file_link:
                        sources_html += f"<a href='{file_link}' class='source-title' target='_blank'>{html.escape(filename)}</a>"
                    else:
                        sources_html += f"<span class='source-title'>{html.escape(filename)}</span>"

                    score_val = res.get("score", 0)
                    if isinstance(score_val, (float, int)):
                        if -1 <= score_val <= 1:
                            score_str = f"{int(score_val * 100)}%"
                        else:
                            score_str = f"{score_val:.2f}"
                    else:
                        score_str = str(score_val)

                    sources_html += f"<span class='score'>Score: {score_str}</span>"
                    sources_html += f"<div class='excerpt'>\"{chunk_excerpt}\"</div>"
                    sources_html += "</li>"

                sources_html += """
    </ul>
</body>
</html>
"""
                sources_bytes = sources_html.encode("utf-8")
                
                html_content += """
                <div style="border-top: 1px dashed #ced4da; padding-top: 15px; font-size: 13px;">
                    📚 <em>Les sources utilisées pour formuler cette réponse sont disponibles dans la pièce jointe <strong>sources_ia.html</strong>.</em>
                </div>
                """

            html_content += """
                <div style="margin-top: 15px; font-size: 13px; color: #198754; background-color: #d1e7dd; padding: 10px; border-radius: 5px; text-align: center;">
                    💡 <strong>Astuce :</strong> Double-cliquez sur la pièce jointe <strong>reponse_ia.eml</strong> pour ouvrir un brouillon propre et prêt à envoyer.
                </div>
            """
                
            html_content += "</div>"
            return html_content, ai_response, sources_bytes, confidence_label
            
        except Exception as e:
            self.logger.error("❌ Erreur lors de la génération de la suggestion HTML : %s", e)
            return None, None, None, None

    def _build_query(self, subject: str, body: str) -> str:
        # Utiliser uniquement le corps de l'email pour éviter de polluer 
        # le vecteur sémantique avec des mots clés génériques du sujet (ex: "permis de construire")
        if body and len(body.strip()) > 10:
            final_query = body.strip()
        else:
            final_query = subject.strip() if subject else "Demande non spécifiée"
            
        self.logger.info("🛠️ Query construite pour RAG: [%s]", final_query)
        return final_query

    def _search_and_generate(
        self,
        query: str,
        workspace: str,
        ws_config: Dict[str, Any],
    ) -> Tuple[List[Dict], str]:
        """
        Recherche dans la KB et génère une réponse.
        
        Args:
            query: Question du client
            workspace: Workspace cible
            ws_config: Configuration du workspace
            
        Returns:
            (search_results, ai_response)
        """
        try:
            # Appeler le RAG Proxy pour recherche + génération
            rag_url = self.config.rag_proxy_url.rstrip("/")
            
            # Construire le prompt système avec le style
            system_prompt = self._build_system_prompt(ws_config)
            
            payload = {
                "query": query,
                "collection": workspace,
                "top_k": 20,
                "final_k": 10,
                "generate": True,
                "system_prompt": system_prompt,
            }
            
            self.logger.debug("📡 Appel RAG Proxy: %s/chat", rag_url)
            
            response = requests.post(
                f"{rag_url}/chat",
                json=payload,
                timeout=self.config.rag_proxy_timeout,
            )
            
            if response.ok:
                data = response.json()
                sources = data.get("sources", [])
                ai_response = data.get("answer", "")
                
                return sources, ai_response
            else:
                self.logger.warning(
                    "⚠️ RAG Proxy a répondu %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return [], ""
                
        except Exception as e:
            self.logger.error(
                "❌ Erreur recherche RAG: %s",
                e,
                exc_info=True,
            )
            return [], ""

    def _build_system_prompt(self, ws_config: Dict[str, Any]) -> str:
        """
        Construit le prompt système avec le style configuré.
        
        Args:
            ws_config: Configuration du workspace
            
        Returns:
            Prompt système complet
        """
        style_config = ws_config.get("response_style", DEFAULT_RESPONSE_STYLE)
        tone = style_config.get("tone", "professional")
        
        # Charger le prompt de style
        style_prompt = self._load_style_prompt(tone)
        
        # Substituer les variables
        greeting = style_config.get("greeting", DEFAULT_RESPONSE_STYLE["greeting"])
        signature = style_config.get("signature", DEFAULT_RESPONSE_STYLE["signature"])
        language = style_config.get("language", DEFAULT_RESPONSE_STYLE["language"])
        
        return style_prompt.replace(
            "{{greeting}}", greeting
        ).replace(
            "{{signature}}", signature
        ).replace(
            "{{language}}", language
        )

    def _load_style_prompt(self, tone: str) -> str:
        """
        Charge le prompt de style correspondant au ton.
        
        Args:
            tone: Nom du ton (professional, friendly, concise, technical)
            
        Returns:
            Contenu du prompt
        """
        # Cache
        if tone in self._style_prompts:
            return self._style_prompts[tone]
        
        # Fichier personnalisé
        prompt_file = self.prompts_dir / f"{tone}.txt"
        
        if prompt_file.exists():
            try:
                content = prompt_file.read_text(encoding="utf-8")
                self._style_prompts[tone] = content
                return content
            except Exception as e:
                self.logger.warning(
                    "⚠️ Erreur lecture prompt %s: %s",
                    prompt_file,
                    e,
                )
        
        # Prompt par défaut
        default_prompt = self._default_style_prompt(tone)
        self._style_prompts[tone] = default_prompt
        return default_prompt

    def _default_style_prompt(self, tone: str) -> str:
        """Retourne un prompt de style par défaut."""
        prompts = {
            "professional": """Tu es un assistant de support technique professionnel.

STYLE DE RÉPONSE :
- Vouvoiement systématique
- Ton formel et courtois
- Phrases structurées et claires

STRUCTURE :
1. {{greeting}}
2. Réponse claire et détaillée (fournis toutes les informations pertinentes trouvées dans le contexte, même partielles)
3. Proposition d'aide complémentaire
4. {{signature}}

RÈGLES :
- Si le contexte ne donne qu'une partie de la réponse (ex: une hauteur maximale mais pas minimale), donne l'information disponible.
- Ne jamais inventer d'information.
- Répondre uniquement en {{language}}.
- Si le contexte ne contient VRAIMENT aucune information utile, propose de vérifier avec un expert.""",

            "friendly": """Tu es un assistant de support technique accessible et sympathique.

STYLE DE RÉPONSE :
- Tutoiement ou vouvoiement selon le message du client
- Ton chaleureux mais professionnel
- Phrases courtes et dynamiques

STRUCTURE :
1. {{greeting}} 👋
2. Reformulation empathique du problème
3. Solution claire étape par étape
4. {{signature}}""",

            "concise": """Tu es un assistant de support efficace.

STYLE DE RÉPONSE :
- Réponses courtes et directes
- Pas de formules superflues
- Listes à puces pour les étapes

STRUCTURE :
1. {{greeting}}
2. Réponse en 2-3 phrases max
3. {{signature}}""",

            "technical": """Tu es un expert technique.

STYLE DE RÉPONSE :
- Termes techniques appropriés
- Détails techniques si pertinents
- Expliquer le "pourquoi" technique

STRUCTURE :
1. {{greeting}}
2. Contexte technique rapide
3. Solution avec explication technique
4. {{signature}}""",
        }
        
        return prompts.get(tone, prompts["professional"])

    def _calculate_confidence(
        self,
        search_results: List[Dict],
        thresholds: Dict[str, float],
    ) -> Tuple[float, str]:
        """
        Calcule le score de confiance et le niveau.
        
        Args:
            search_results: Résultats de recherche avec scores
            thresholds: Seuils de confiance configurés
            
        Returns:
            (score: float, level: str)
        """
        if not search_results:
            return 0.0, "none"
        
        # Score moyen des top résultats
        scores = [r.get("score", 0) for r in search_results[:3]]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Déterminer le niveau
        none_threshold = thresholds.get("none", 0.3)
        low_threshold = thresholds.get("low", 0.5)
        medium_threshold = thresholds.get("medium", 0.7)
        
        if avg_score < none_threshold:
            level = "none"
        elif avg_score < low_threshold:
            level = "low"
        elif avg_score < medium_threshold:
            level = "medium"
        else:
            level = "high"
        
        return avg_score, level

    def _build_draft_content(
        self,
        email: "ParsedEmail",
        ai_response: str,
        sources: List[Dict],
        confidence_level: str,
        confidence_score: float,
        ws_config: Dict[str, Any],
    ) -> str:
        """
        Génère le contenu HTML complet du brouillon.
        
        Sélectionne le template selon le niveau de confiance.
        
        Args:
            email: Email original
            ai_response: Réponse générée par l'IA
            sources: Sources utilisées
            confidence_level: Niveau de confiance (none/low/medium/high)
            confidence_score: Score numérique
            ws_config: Configuration du workspace
            
        Returns:
            Contenu HTML du brouillon
        """
        style_config = ws_config.get("response_style", DEFAULT_RESPONSE_STYLE)
        
        # Préparer les sources pour le template
        formatted_sources = []
        for src in sources[:5]:  # Max 5 sources
            formatted_sources.append({
                "filename": src.get("metadata", {}).get("filename", "Document"),
                "score_percent": int(src.get("score", 0) * 100),
            })
        
        # Variables du template
        template_vars = {
            "client_email": email.sender,
            "original_subject": email.subject or "Sans sujet",
            "original_question": email.body or "",
            "ai_response": ai_response or "",
            "sources": formatted_sources,
            "confidence_percent": int(confidence_score * 100),
            "greeting": style_config.get("greeting", "Bonjour,"),
            "signature": style_config.get("signature", "Cordialement,"),
        }
        
        # Sélectionner le template selon le niveau de confiance
        template_name = f"support_draft_{confidence_level}.html"
        
        try:
            return self.email_renderer.render_template(
                template_name,
                **template_vars,
            )
        except Exception as e:
            self.logger.warning(
                "⚠️ Template %s non trouvé, utilisation du fallback: %s",
                template_name,
                e,
            )
            return self._fallback_template(template_vars, confidence_level)

    def _fallback_template(
        self,
        vars: Dict[str, Any],
        confidence_level: str,
    ) -> str:
        """Template de secours si le template principal n'existe pas."""
        confidence_colors = {
            "none": "#fff3cd",
            "low": "#fff3cd",
            "medium": "#d1ecf1",
            "high": "#d4edda",
        }
        
        confidence_icons = {
            "none": "⚠️",
            "low": "🔍",
            "medium": "✏️",
            "high": "✅",
        }
        
        confidence_texts = {
            "none": "Pas de correspondance - Réponse manuelle requise",
            "low": f"Suggestion partielle ({vars['confidence_percent']}%) - À compléter",
            "medium": f"Réponse suggérée ({vars['confidence_percent']}%) - À vérifier",
            "high": f"Réponse suggérée ({vars['confidence_percent']}%)",
        }
        
        color = confidence_colors.get(confidence_level, "#f8f9fa")
        icon = confidence_icons.get(confidence_level, "ℹ️")
        text = confidence_texts.get(confidence_level, "Réponse")
        
        ai_content = vars.get("ai_response", "")
        if not ai_content and confidence_level in ("none", "low"):
            ai_content = f"""<p>{vars['greeting']}</p>
<p><em>[Votre réponse ici]</em></p>
<p>{vars['signature'].replace(chr(10), '<br>')}</p>"""
        
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
    <div style="background: {color}; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px dashed #dc3545;">
        <h3 style="margin: 0;">{icon} {text}</h3>
        <p style="color: #dc3545; font-weight: bold; margin-top: 10px; margin-bottom: 0; font-size: 14px;">
            (⚠️ NOTE INTERNE IA : Cliquez sur ce bandeau et effacez-le avant d'envoyer votre réponse)
        </p>
    </div>
    
    <div style="margin-bottom: 20px;">
        {ai_content}
    </div>
    
    <hr style="border: 1px dashed #ccc;">
    
    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
        <h4>📩 Question du client :</h4>
        <p><strong>De :</strong> {vars['client_email']}</p>
        <p><strong>Sujet :</strong> {vars['original_subject']}</p>
        <blockquote style="border-left: 3px solid #007bff; padding-left: 15px;">
            {vars['original_question'].replace(chr(10), '<br>')}
        </blockquote>
    </div>
</body>
</html>"""

    def _extract_message_id(self, email_data: Dict) -> Optional[str]:
        """Extrait le Message-ID de l'email original."""
        try:
            raw = email_data.get(b"RFC822", b"")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            
            # Chercher le header Message-ID
            match = re.search(r"Message-ID:\s*<?([^>\s]+)>?", raw, re.IGNORECASE)
            if match:
                return f"<{match.group(1)}>"
        except Exception:
            pass
        
        return None
