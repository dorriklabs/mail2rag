import re
import time
from typing import Callable, List, Dict, Any, Tuple

import requests

from config import Config
from models import ParsedEmail
from services.anythingllm_client import AnythingLLMClient
from services.mail import MailService
from services.router import RouterService
from services.cleaner import CleanerService
from services.email_renderer import EmailRenderer
from services.utils import sanitize_filename


class ChatService:
    """
    Service responsable du mode CHAT/Q&A par email.
    """

    def __init__(
        self,
        config: Config,
        logger,
        client: AnythingLLMClient,
        mail_service: MailService,
        router: RouterService,
        cleaner: CleanerService,
        email_renderer: EmailRenderer,
        get_secure_id: Callable[[int], str],
    ) -> None:
        self.config = config
        self.logger = logger
        self.client = client
        self.mail_service = mail_service
        self.router = router
        self.cleaner = cleaner
        self.email_renderer = email_renderer
        self.get_secure_id = get_secure_id

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def handle_chat(self, email: ParsedEmail) -> None:
        """Traite un email en mode CHAT."""
        self.logger.debug("Mode CHAT détecté pour UID %s.", email.uid)

        clean_subject = self._normalize_subject(email.subject)
        if not clean_subject:
            clean_subject = "Votre question"

        workspace: str | None = None

        try:
            workspace = self.router.determine_workspace(email.email_data)
            self.client.ensure_workspace_exists(workspace)

            cleaned_body = self.cleaner.clean_body(email.body)
            query_content = cleaned_body if cleaned_body.strip() else (email.body or "")

            query_message = f"Sujet : {clean_subject}\n\nQuestion :\n{query_content}"

            # --- Stratégie de recherche : RAG Proxy (hybride) avec fallback AnythingLLM ---
            if self.config.use_rag_proxy_for_search:
                try:
                    self.logger.info(
                        "🔍 [RAG Proxy] Recherche hybride pour '%s'...", clean_subject
                    )
                    response_text, sources = self._search_via_rag_proxy(
                        query_message, workspace
                    )
                except Exception as e:
                    # Fallback propre sur AnythingLLM
                    self.logger.error(
                        "Erreur lors de l'utilisation du RAG Proxy, "
                        "fallback vers AnythingLLM. Détail: %s",
                        e,
                        exc_info=True,
                    )
                    self.logger.info(
                        "🔍 [AnythingLLM] Recherche vectorielle (fallback) pour '%s'...",
                        clean_subject,
                    )
                    response_text, sources = self.client.send_chat_query(
                        workspace, query_message
                    )
            else:
                self.logger.info(
                    "🔍 [AnythingLLM] Recherche vectorielle pour '%s'...",
                    clean_subject,
                )
                response_text, sources = self.client.send_chat_query(
                    workspace, query_message
                )

            # Sauvegarde optionnelle du chat (log-only, non indexé)
            if self.config.save_chat_history:
                self._archive_chat_session(
                    email=email,
                    workspace=workspace,
                    clean_subject=clean_subject,
                    query_content=query_content,
                    response_text=response_text,
                )

            html_body = self.email_renderer.render_chat_response(
                response_text=response_text,
                sources=sources,
                archive_base_url=self.config.archive_base_url,
                workspace=workspace,
            )

            reply_subject = f"Réponse à votre question - {clean_subject}"
            self.mail_service.send_reply(
                email.sender, reply_subject, html_body, is_html=True
            )

        except Exception as e:
            self.logger.error("Erreur Chat : %s", e, exc_info=True)
            error_details = (
                f"Workspace : {workspace or 'indéterminé'}\n"
                f"UID : {email.uid}\n"
                f"Sujet : {email.subject}\n\n"
                f"Erreur : {e}"
            )
            error_html = self.email_renderer.render_crash_report(
                error_message=error_details
            )
            error_subject = f"Erreur technique lors du chat - {clean_subject}"
            self.mail_service.send_reply(
                email.sender, error_subject, error_html, is_html=True
            )

    # ------------------------------------------------------------------ #
    # Archivage des conversations
    # ------------------------------------------------------------------ #
    def _archive_chat_session(
        self,
        email: ParsedEmail,
        workspace: str,
        clean_subject: str,
        query_content: str,
        response_text: str,
    ) -> None:
        """Sauvegarde la conversation (question + réponse) dans l'archive."""
        try:
            self.logger.info("💾 Archivage du Chat (UID %s) demandé.", email.uid)

            secure_id = self.get_secure_id(email.uid)
            secure_folder = self.config.archive_path / secure_id
            secure_folder.mkdir(parents=True, exist_ok=True)

            safe_subject = (
                sanitize_filename(email.subject, self.config.max_filename_length)
                or "Chat_Session"
            )

            chat_filename = f"CHAT_{safe_subject}.txt"
            chat_path = secure_folder / chat_filename

            real_date = time.strftime("%Y-%m-%d %H:%M")

            with chat_path.open("w", encoding="utf-8") as f:
                f.write(f"Sujet : {email.subject}\n")
                f.write(f"Workspace : {workspace}\n")
                f.write(f"UID : {email.uid}\n")
                f.write(f"Date : {real_date}\n")
                f.write("-" * 30 + "\n\n")
                f.write("QUESTION ORIGINALE :\n")
                f.write(email.body or "")
                f.write("\n\n" + "-" * 30 + "\n\n")
                f.write("QUESTION NETTOYÉE POUR LE LLM :\n")
                f.write(query_content or "")
                f.write("\n\n" + "-" * 30 + "\n\n")
                f.write("RÉPONSE IA :\n")
                f.write(response_text or "")

            self.logger.info(
                "💾 Chat archivé (non indexé) dans %s",
                chat_path,
            )
        except Exception as e:
            self.logger.error(
                "⚠️ Erreur lors de l'archivage du chat : %s",
                e,
                exc_info=True,
            )

    # ------------------------------------------------------------------ #
    # RAG Proxy + LM Studio
    # ------------------------------------------------------------------ #
    def _search_via_rag_proxy(
        self,
        query: str,
        workspace: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Recherche via RAG Proxy puis génération de réponse via LLM."""
        chunks = self._rag_proxy_search(query)
        sources, context_text = self._build_context_from_chunks(chunks)
        response_text = self._generate_answer_from_context(
            query=query,
            workspace=workspace,
            context_text=context_text,
        )
        return response_text, sources

    def _rag_proxy_search(self, query: str) -> List[Dict[str, Any]]:
        """Appelle l'endpoint /rag du RAG Proxy."""
        rag_url = f"{self.config.rag_proxy_url}/rag"
        payload = {
            "query": query,
            "top_k": 20,
            "final_k": 5,
            "use_bm25": True,
        }

        try:
            self.logger.debug("Appel RAG Proxy: %s", rag_url)
            resp = requests.post(
                rag_url,
                json=payload,
                timeout=self.config.rag_proxy_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            chunks = data.get("chunks", []) or []
            self.logger.info(
                "RAG Proxy a retourné %d chunks pertinents.",
                len(chunks),
            )
            return chunks
        except Exception as e:
            self.logger.error(
                "Erreur lors de la recherche RAG Proxy: %s", e, exc_info=True
            )
            # On laisse remonter pour permettre un fallback contrôlé dans handle_chat
            raise

    @staticmethod
    def _build_context_from_chunks(
        chunks: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Construit la liste des sources et le contexte texte à partir des chunks."""
        sources: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        for chunk in chunks:
            text = chunk.get("text", "")
            meta = chunk.get("metadata", {}) or {}
            score = float(chunk.get("score", 0.0))

            source_title = meta.get("title", "Document inconnu")

            sources.append(
                {
                    "title": source_title,
                    "text": text,
                    "score": score,
                    "metadata": meta,
                }
            )

            context_parts.append(
                f"--- Document: {source_title} (Score: {score:.2f}) ---\n"
                f"{text}\n"
            )

        context_text = "\n".join(context_parts)
        return sources, context_text

    def _generate_answer_from_context(
        self,
        query: str,
        workspace: str,
        context_text: str,
    ) -> str:
        """Appelle le LLM (LM Studio) pour générer une réponse à partir du contexte."""
        try:
            system_prompt = (
                self.config.workspace_prompts.get(workspace)
                or self.config.default_system_prompt
                or (
                    "Tu es un assistant utile qui répond aux questions en "
                    "utilisant UNIQUEMENT le contexte fourni ci-dessous. "
                    "Si la réponse n'est pas dans le contexte, dis-le poliment."
                )
            )

            user_prompt = (
                f"CONTEXTE:\n{context_text}\n\n"
                f"QUESTION:\n{query}\n\n"
                f"RÉPONSE:"
            )

            llm_payload: Dict[str, Any] = {
                "model": self.config.ai_model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.config.default_llm_temperature,
                "max_tokens": 1000,
            }

            self.logger.debug("Appel LLM Generation: %s", self.config.llm_api_url)
            llm_resp = requests.post(
                self.config.llm_api_url,
                json=llm_payload,
                timeout=self.config.llm_timeout,
            )
            llm_resp.raise_for_status()
            llm_data = llm_resp.json()

            choices = llm_data.get("choices") or []
            if not choices:
                self.logger.error(
                    "Réponse LLM sans 'choices': %s", str(llm_data)[:500]
                )
                return self.config.default_refusal_response or (
                    "Je n'ai pas pu générer de réponse à partir du contexte."
                )

            return choices[0].get("message", {}).get("content", "").strip() or (
                self.config.default_refusal_response
                or "Je n'ai pas pu générer de réponse à partir du contexte."
            )
        except Exception as e:
            self.logger.error(
                "Erreur lors de la génération LLM: %s",
                e,
                exc_info=True,
            )
            raise

    # ------------------------------------------------------------------ #
    # Utilitaires
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_subject(subject: str | None) -> str:
        """Supprime le préfixe Chat: ou Question: du sujet."""
        subject = (subject or "").strip()
        return re.sub(r"(?i)^(chat|question)\s*:\s*", "", subject).strip()
