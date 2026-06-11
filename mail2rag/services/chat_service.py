import os
import re
import time
from typing import Callable, List, Dict, Any, Tuple

import requests

from config import Config
from models import ParsedEmail
from services.mail import MailService
from services.router import RouterService
from services.cleaner import CleanerService
from services.email_renderer import EmailRenderer
from services.utils import sanitize_filename

# Check if we should use LiteLLM Gateway
_USE_LLM_GATEWAY = os.getenv("LLM_PROVIDER", "lmstudio").lower() not in ("lmstudio", "")


class ChatService:
    """
    Service responsable du mode CHAT/Q&A par email.
    """

    def __init__(
        self,
        config: Config,
        logger,
        mail_service: MailService,
        router: RouterService,
        cleaner: CleanerService,
        email_renderer: EmailRenderer,
        get_secure_id: Callable[[int], str],
    ) -> None:
        self.config = config
        self.logger = logger
        self.mail_service = mail_service
        self.router = router
        self.cleaner = cleaner
        self.email_renderer = email_renderer
        self.get_secure_id = get_secure_id
        
        # Initialize LLM Client for gateway providers
        self.llm_client = None
        if _USE_LLM_GATEWAY:
            from services.llm_client import get_llm_client
            self.llm_client = get_llm_client(config)
            logger.info(f"LLMClient initialisé pour ChatService (provider: {os.getenv('LLM_PROVIDER')})")

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

            cleaned_body = self.cleaner.clean_body(email.body, subject=email.subject)
            query_content = cleaned_body if cleaned_body.strip() else (email.body or "")
            
            # Extraction collection spécifique du corps (syntaxe: dossier : xxx ou collection : xxx)
            collection_to_search = self._extract_collection_from_body(query_content, workspace)
            
            # Nettoyer la query en retirant la ligne de collection si présente
            query_content_cleaned = self._remove_collection_line(query_content)

            query_message = f"Sujet : {clean_subject}\n\nQuestion :\n{query_content_cleaned}"

            # Recherche via RAG Proxy (hybride)
            self.logger.info(
                "🔍 [RAG Proxy] Recherche hybride pour '%s' dans collection '%s'...", 
                clean_subject, collection_to_search
            )
            response_text, sources = self._search_via_rag_proxy(
                query_message, collection_to_search
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
        collection: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Recherche via RAG Proxy puis génération de réponse via LLM."""
        chunks = self._rag_proxy_search(query, collection)
        sources, context_text = self._build_context_from_chunks(chunks)
        response_text = self._generate_answer_from_context(
            query=query,
            workspace=collection,
            context_text=context_text,
        )
        return response_text, sources

    def _rag_proxy_search(self, query: str, collection: str = None) -> List[Dict[str, Any]]:
        """Appelle l'endpoint /rag du RAG Proxy."""
        rag_url = f"{self.config.rag_proxy_url}/rag"
        payload = {
            "query": query,
            "top_k": 20,
            "final_k": 5,
            "use_bm25": True,
        }
        
        # Ajouter la collection si spécifiée
        if collection:
            payload["collection"] = collection

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
            
            # Logging détaillé des stats RAG Proxy
            debug_info = data.get("debug_info")
            if debug_info:
                timings = debug_info.get("timings", {})
                counts = debug_info.get("counts", {})
                total_time = debug_info.get("total_time", 0)
                
                self.logger.info(
                    "🔍 [RAG Proxy] Succès (%.3fs) | Qdrant: %d docs (%.3fs) | BM25: %d docs (%.3fs) | Reranked: %d docs (%.3fs)",
                    total_time,
                    counts.get("vector_found", 0),
                    timings.get("vector_search", 0),
                    counts.get("bm25_found", 0),
                    timings.get("bm25_search", 0),
                    counts.get("final_results", len(chunks)),
                    timings.get("reranking", 0)
                )
            else:
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

    def _build_context_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Construit la liste des sources et le contexte texte à partir des chunks."""
        sources: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        for chunk in chunks:
            text = chunk.get("text", "")
            meta = chunk.get("metadata", {}) or {}
            score = float(chunk.get("score", 0.0))

            source_title = meta.get("title") or meta.get("filename") or meta.get("subject") or "Document inconnu"
            
            # --- Enrichissement des métadonnées pour les liens ---
            # On essaie d'extraire l'UID du nom de fichier pour retrouver le secure_id
            # Format attendu : "custom-documents/{UID}_{Sujet}.txt-uuid.json" ou juste "{UID}_{Sujet}.txt"
            filename = source_title
            if "/" in filename:
                filename = filename.split("/")[-1] # Garder la partie après le dernier /
            
            # Nettoyer les suffixes de métadonnées (ex: -uuid.json)
            # On cherche le pattern {UID}_ au début du nom
            uid_match = re.match(r'^(\d+)_', filename)
            
            if uid_match:
                try:
                    uid = int(uid_match.group(1))
                    secure_id = self.get_secure_id(uid)
                    
                    # On enrichit les métadonnées
                    meta["secure_id"] = secure_id
                    
                    # On nettoie le nom de fichier pour l'affichage et le lien
                    # Si le fichier finit par .json (métadonnées), on retire le suffixe UUID+JSON.
                    clean_filename = re.sub(r'-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.json$', '', filename)
                    meta["filename"] = clean_filename
                    
                except Exception as e:
                    self.logger.warning("Erreur enrichissement metadata pour %s: %s", filename, e)

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
        """Appelle le LLM pour générer une réponse à partir du contexte."""
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
            
            # Limiter le contexte pour éviter les dépassements de tokens
            max_context_tokens = getattr(self.config, "llm_max_context_tokens", 6000)
            effective_context_tokens = max(max_context_tokens - 2000, 2000)
            max_context_chars = effective_context_tokens * 2
            
            if len(context_text) > max_context_chars:
                self.logger.warning(
                    "⚠️ Contexte tronqué: %d chars → %d chars (limite: %d tokens effectifs)",
                    len(context_text), max_context_chars, effective_context_tokens
                )
                context_text = context_text[:max_context_chars] + "\n\n[... contexte tronqué ...]"

            user_prompt = (
                f"CONTEXTE:\n{context_text}\n\n"
                f"QUESTION:\n{query}\n\n"
                f"RÉPONSE:"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # Use LLMClient if gateway is enabled
            if self.llm_client:
                self.logger.debug("Appel LLM via Gateway")
                content = self.llm_client.chat(
                    messages=messages,
                    temperature=self.config.default_llm_temperature,
                    max_tokens=1000,
                    timeout=self.config.llm_timeout,
                )
                
                if not content:
                    return self.config.default_refusal_response or (
                        "Je n'ai pas pu générer de réponse à partir du contexte."
                    )
                return content
            
            # Direct HTTP for LM Studio
            llm_payload: Dict[str, Any] = {
                "model": self.config.ai_model_name,
                "messages": messages,
                "temperature": self.config.default_llm_temperature,
                "max_tokens": 1000,
            }

            self.logger.debug("Appel LLM Generation: %s", self.config.llm_api_url)
            llm_resp = requests.post(
                self.config.llm_api_url,
                json=llm_payload,
                timeout=self.config.llm_timeout,
            )
            
            if llm_resp.status_code != 200:
                self.logger.error(
                    "Erreur LLM (HTTP %d): %s",
                    llm_resp.status_code,
                    llm_resp.text[:500]
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
    
    # Pattern pour détecter la ligne de collection dans le corps
    # Syntaxe supportée: "dossier : xxx", "collection : xxx", "workspace : xxx"
    COLLECTION_PATTERN = re.compile(
        r"^\s*(?:dossier|collection|workspace)\s*:\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE
    )
    
    def _extract_collection_from_body(self, body: str, default_workspace: str) -> str:
        """
        Extrait le nom de collection du corps de l'email.
        
        Syntaxe supportée:
            - dossier : nom-collection
            - collection : nom-collection
            - workspace : nom-collection
        
        Args:
            body: Corps de l'email
            default_workspace: Workspace par défaut si aucune collection spécifiée
            
        Returns:
            Nom de la collection ou workspace par défaut
        """
        if not body:
            return default_workspace
            
        match = self.COLLECTION_PATTERN.search(body)
        if match:
            collection = match.group(1).strip()
            self.logger.info(f"📂 Collection spécifiée dans le corps: '{collection}'")
            return collection
            
        return default_workspace
    
    def _remove_collection_line(self, body: str) -> str:
        """
        Retire la ligne de spécification de collection du corps.
        
        Cela évite que la ligne "dossier : xxx" soit incluse dans la question.
        """
        if not body:
            return body
            
        return self.COLLECTION_PATTERN.sub("", body).strip()
