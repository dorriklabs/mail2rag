import time
import email
import re
from html import unescape
from pathlib import Path
import queue
import threading
from typing import Any, Dict, List, Optional, Tuple

from config import Config
from client import AnythingLLMClient
from services.mail import MailService
from services.router import RouterService
from services.processor import DocumentProcessor
from services.cleaner import CleanerService
from services.maintenance import MaintenanceService
from services.utils import decode_email_header, sanitize_filename, truncate_log
from services.state_manager import StateManager
from services.email_renderer import EmailRenderer
from services.support_qa import SupportQAService  # NEW


HTML_TAG_RE = re.compile(r'<[^>]+>')
WHITESPACE_RE = re.compile(r'\s+')


class Mail2RAGApp:
    def __init__(self) -> None:
        """
        Application principale Mail2RAG.
        Orchestration de la récupération des emails, de leur traitement
        (ingestion ou chat) et de l'intégration avec AnythingLLM / RAG Proxy.
        """
        self.config = Config()
        self.logger = self.config.setup_logging()

        self.client = AnythingLLMClient(self.config)
        self.mail_service = MailService(self.config)
        self.router = RouterService(self.config)
        self.processor = DocumentProcessor(self.config)
        self.cleaner = CleanerService(self.config)
        self.maintenance_service = MaintenanceService(
            self.config, self.client, self.router, self.mail_service
        )
        self.support_qa_service = SupportQAService(self.config)  # NEW

        # Templates / état
        template_dir = Path(__file__).parent / "templates"
        self.state_manager = StateManager(self.config.state_path, self.logger)
        self.state_lock = threading.Lock()

        # Chargement de l'état persistant de manière résiliente
        try:
            loaded_state = self.state_manager.load_state()
            if isinstance(loaded_state, dict):
                self.state: Dict[str, Any] = loaded_state
            else:
                self.logger.warning(
                    "Format d'état invalide, initialisation d'un état vide."
                )
                self.state = {}
        except Exception as e:
            self.logger.error(
                f"Impossible de charger l'état, utilisation d'un état vide : {e}",
                exc_info=True,
            )
            self.state = {}

        self.email_renderer = EmailRenderer(template_dir)

        # Concurrence : file de tâches + workers
        self.task_queue: "queue.Queue[Tuple[int, Any]]" = queue.Queue(
            maxsize=self.config.worker_queue_size
        )
        self.workers: List[threading.Thread] = []
        self._start_workers()

    # -------------------------------------------------------------------------
    #  WORKERS
    # -------------------------------------------------------------------------
    def _start_workers(self) -> None:
        worker_count = max(1, int(self.config.worker_count))
        for i in range(worker_count):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"mail2rag-worker-{i+1}",
                daemon=True,
            )
            t.start()
            self.workers.append(t)
        self.logger.info(
            "Démarré %d worker(s) de traitement (queue max=%d).",
            len(self.workers),
            self.config.worker_queue_size,
        )

    def _worker_loop(self) -> None:
        while True:
            uid, message_data = self.task_queue.get()
            try:
                self.logger.debug("[Worker] Début traitement UID %s", uid)
                self.process_email(uid, message_data)
                self.logger.debug("[Worker] Fin traitement UID %s", uid)
            except Exception as e:
                self.logger.error(
                    "[Worker] Erreur lors du traitement UID %s : %s",
                    uid,
                    e,
                    exc_info=True,
                )
            finally:
                self.task_queue.task_done()

    # -------------------------------------------------------------------------
    #  TRAITEMENT D'UN EMAIL
    # -------------------------------------------------------------------------
    def process_email(self, uid: int, message_data: Any) -> None:
        """
        Traite un email (mode CHAT ou ingestion RAG).
        `message_data` vient de MailService.fetch_new_messages
        et ressemble à {b"RFC822": raw_bytes}.
        """
        # 1) Récupération des bytes de l'email
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
            return

        # 2) Construction de l'objet email.message.Message
        if isinstance(raw_msg, (bytes, bytearray)):
            msg = email.message_from_bytes(raw_msg)
        else:
            # On suppose que c'est déjà un email.message.Message
            msg = raw_msg

        subject = decode_email_header(msg.get("Subject", ""))
        sender = decode_email_header(msg.get("From", ""))

        # ---------------------------------------------------------------------
        # Détection d'email synthétique
        # ---------------------------------------------------------------------
        is_synthetic = msg.get("X-Mail2RAG-Synthetic", "").lower() == "true"
        if is_synthetic:
            self.logger.info(
                "📧 Email synthétique détecté UID %s | Sujet: %s", uid, subject
            )
        else:
            self.logger.info(
                "📨 Traitement UID %s | Sujet: %s | De: %s",
                uid,
                subject,
                sender,
            )

        # ---------------------------------------------------------------------
        # Helpers locaux pour décoder correctement les parts texte / HTML
        # ---------------------------------------------------------------------
        def _decode_part_with_charset(part: Any) -> str:
            """Décode une part MIME en respectant son charset."""
            if part is None:
                return ""

            payload = part.get_payload(decode=True)
            if payload is None:
                return ""

            charset = part.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except LookupError:
                # Charset inconnu
                self.logger.warning(
                    "Charset inconnu '%s', fallback utf-8 pour UID %s",
                    charset,
                    uid,
                )
                try:
                    return payload.decode("utf-8", errors="replace")
                except Exception:
                    try:
                        return payload.decode("latin-1", errors="replace")
                    except Exception:
                        return ""
            except Exception:
                # Dernier recours : latin-1
                try:
                    return payload.decode("latin-1", errors="replace")
                except Exception:
                    return ""

        def _html_to_text(html: str) -> str:
            """Conversion simple HTML -> texte (sans dépendance externe)."""
            text = HTML_TAG_RE.sub(" ", html)  # Supprimer les balises
            text = WHITESPACE_RE.sub(" ", text)  # Normaliser les espaces
            return unescape(text).strip()

        def _decode_text_part(part: Any) -> str:
            """Décoder une part text/plain."""
            return _decode_part_with_charset(part)

        def _decode_html_part(part: Any) -> str:
            """Décoder une part text/html et la convertir en texte brut."""
            html = _decode_part_with_charset(part)
            return _html_to_text(html)

        # ---------------------------------------------------------------------
        # Extraction du corps du message (gestion charset + fallback HTML)
        # ---------------------------------------------------------------------
        body = ""

        if msg.is_multipart():
            plain_chunks: List[str] = []
            html_chunks: List[str] = []

            for part in msg.walk():
                ctype = (part.get_content_type() or "").lower()
                disp = (part.get("Content-Disposition") or "").lower()

                # Ignorer les pièces jointes
                if "attachment" in disp:
                    continue

                if ctype == "text/plain":
                    plain_chunks.append(_decode_text_part(part))
                elif ctype == "text/html":
                    html_chunks.append(_decode_html_part(part))

            if plain_chunks:
                body = "".join(plain_chunks)
            elif html_chunks:
                body = "".join(html_chunks)
        else:
            ctype = (msg.get_content_type() or "").lower()
            if ctype == "text/plain":
                body = _decode_text_part(msg)
            elif ctype == "text/html":
                body = _decode_html_part(msg)
            else:
                body = _decode_text_part(msg)

        email_data = {"subject": subject, "from": sender, "body": body}

        # ---------------------------------------------------------------------
        # MODE CHAT
        # ---------------------------------------------------------------------
        subj_lower = (subject or "").lower()
        if subj_lower.startswith(("chat:", "question:")):
            self._handle_chat(uid, sender, subject, body, email_data)
            return

        # ---------------------------------------------------------------------
        # MODE INGESTION
        # ---------------------------------------------------------------------
        try:
            # 1. Détermination du Workspace
            workspace = self.router.determine_workspace(email_data)

            safe_subject = sanitize_filename(
                subject, self.config.max_filename_length
            )
            if not safe_subject:
                safe_subject = self.config.default_subject

            files_to_upload: List[str] = []

            # Génération ou récupération du secure_id (opaque) avec verrou
            with self.state_lock:
                secure_id = self.state_manager.get_or_create_secure_id(
                    self.state, uid
                )

            # Création du dossier sécurisé dans l'archive
            secure_folder = self.config.archive_path / secure_id
            secure_folder.mkdir(parents=True, exist_ok=True)

            # 2. Préparation du Body (Nettoyage / Réécriture Q/R éventuelle)
            ws_cfg = self.config.workspace_settings.get(workspace, {})
            use_qa_rewrite = bool(ws_cfg.get("qa_rewrite", False))

            if use_qa_rewrite:
                self.logger.info(
                    "🧠 Réécriture Q/R support activée pour UID %s "
                    "dans workspace '%s'",
                    uid,
                    workspace,
                )
                try:
                    cleaned_body = self.support_qa_service.rewrite_to_qa(
                        subject=subject, sender=sender, raw_body=body
                    )
                except Exception as e:
                    self.logger.error(
                        "Erreur réécriture Q/R support (UID %s), "
                        "fallback vers nettoyage classique : %s",
                        uid,
                        e,
                        exc_info=True,
                    )
                    cleaned_body = self.cleaner.clean_body(body)
            else:
                cleaned_body = self.cleaner.clean_body(body)

            # 2b. Générer résumé ou aperçu de l'email
            if self.config.enable_email_summary:
                try:
                    self.logger.info(
                        "📝 Génération résumé IA pour UID %s...", uid
                    )
                    email_summary = (
                        self.support_qa_service.generate_email_summary(
                            subject=subject, cleaned_body=cleaned_body
                        )
                    )
                except Exception as e:
                    self.logger.warning(
                        "⚠️ Échec génération résumé IA pour UID %s : %s",
                        uid,
                        e,
                    )
                    email_summary = self._extract_preview(cleaned_body)
            else:
                email_summary = self._extract_preview(cleaned_body)

            body_filename = f"{uid}_{safe_subject}.txt"
            body_path = secure_folder / body_filename

            # Extraction métadonnées
            real_date = msg.get("Date") or time.strftime("%Y-%m-%d %H:%M")
            to_header = decode_email_header(msg.get("To"))
            cc_header = decode_email_header(msg.get("Cc"))
            msg_id = msg.get("Message-ID", "").strip()

            with open(body_path, "w", encoding="utf-8") as f:
                f.write(f"Sujet : {subject}\n")
                f.write(f"De : {sender}\n")
                if to_header:
                    f.write(f"À : {to_header}\n")
                if cc_header:
                    f.write(f"Cc : {cc_header}\n")
                f.write(f"Date : {real_date}\n")
                if msg_id:
                    f.write(f"Message-ID : {msg_id}\n")
                f.write(f"IMAP_UID : {uid}\n")
                f.write(f"Workspace : {workspace}\n")
                if email_summary:
                    f.write(f"Résumé : {email_summary}\n")
                if is_synthetic:
                    f.write(
                        "Source : Email synthétique "
                        "(Upload manuel AnythingLLM)\n"
                    )
                f.write("-" * 30 + "\n\n")
                f.write(cleaned_body)

            files_to_upload.append(str(body_path))

            # 3. Traitement des Pièces Jointes
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_maintype() == "multipart":
                        continue
                    if part.get("Content-Disposition") is None:
                        continue

                    filename = part.get_filename()
                    if not filename:
                        continue
                    filename = decode_email_header(filename)

                    # Filtrage via CleanerService
                    content = part.get_payload(decode=True)
                    if not self.cleaner.is_valid_attachment(filename, content):
                        continue

                    safe_pj_name = (
                        f"{uid}_"
                        f"{sanitize_filename(filename, self.config.max_filename_length)}"
                    )
                    filepath = secure_folder / safe_pj_name

                    self.logger.debug("Sauvegarde PJ: %s", filepath.name)
                    with open(filepath, "wb") as f:
                        f.write(content)

                    public_link = (
                        f"{self.config.archive_base_url}/"
                        f"{secure_id}/{filepath.name}"
                    )
                    ext = Path(filename).suffix.lower()

                    # Analyse Documentaire (OCR/Vision)
                    if ext in {".png", ".jpg", ".jpeg", ".pdf"}:
                        analysis_text = self.processor.analyze_document(
                            str(filepath)
                        )
                        if analysis_text:
                            analysis_path = (
                                secure_folder
                                / f"{safe_pj_name}_analysis.txt"
                            )
                            with open(
                                analysis_path, "w", encoding="utf-8"
                            ) as f:
                                f.write(
                                    "Source Document (Lien) : "
                                    f"{public_link}\n"
                                )
                                f.write(
                                    "Email Parent (Sujet) : "
                                    f"{subject}\n"
                                )
                                f.write(f"Date Email : {real_date}\n")
                                f.write("-" * 30 + "\n")
                                f.write(analysis_text)

                            files_to_upload.append(str(analysis_path))
                            self.logger.info(
                                "Optimisation : Upload de l'analyse "
                                "uniquement pour %s",
                                filename,
                            )
                        else:
                            files_to_upload.append(str(filepath))
                    else:
                        files_to_upload.append(str(filepath))

            # 4. Upload vers AnythingLLM
            uploaded_locs: List[str] = []
            for f_path in files_to_upload:
                loc = self.client.upload_file(f_path)
                if loc:
                    uploaded_locs.append(loc)

            # 5. Indexation (Embeddings) et Notification
            if uploaded_locs:
                # S'assurer que le workspace existe avant d'indexer
                self.client.ensure_workspace_exists(workspace)

                success = self.client.update_embeddings(
                    workspace, adds=uploaded_locs
                )

                if success:
                    self.logger.info(
                        "✅ Succès : %d docs indexés dans '%s'",
                        len(uploaded_locs),
                        workspace,
                    )

                    # Ne pas envoyer d'email de confirmation pour les synthétiques
                    if not is_synthetic:
                        files_list: List[str] = []
                        for file in sorted(secure_folder.iterdir()):
                            if file.is_file():
                                files_list.append(file.name)

                        html_report = (
                            self.email_renderer.render_ingestion_success(
                                workspace=workspace,
                                files=files_list,
                                archive_url=(
                                    f"{self.config.archive_base_url}/"
                                    f"{secure_id}/"
                                ),
                                email_summary=email_summary,
                            )
                        )
                        notif_subject = f"Ingestion réussie - {subject}"

                        self.mail_service.send_reply(
                            sender, notif_subject, html_report, is_html=True
                        )

                        # Auto-rebuild BM25 index en arrière-plan (non-bloquant)
                        threading.Thread(
                            target=self._trigger_bm25_rebuild,
                            name="bm25-auto-rebuild",
                            daemon=True,
                        ).start()
                else:
                    self.logger.error(
                        "❌ Échec indexation dans le workspace '%s'.",
                        workspace,
                    )
                    if not is_synthetic:
                        error_html = (
                            self.email_renderer.render_ingestion_error()
                        )
                        notif_subject = f"Erreur d'indexation - {subject}"
                        self.mail_service.send_reply(
                            sender, notif_subject, error_html, is_html=True
                        )
            else:
                self.logger.info("Aucun document pertinent à indexer.")
                if not is_synthetic:
                    info_html = self.email_renderer.render_ingestion_info(
                        subject=subject
                    )
                    notif_subject = f"Aucun document indexé - {subject}"
                    self.mail_service.send_reply(
                        sender, notif_subject, info_html, is_html=True
                    )

        except Exception as e:
            self.logger.error(
                "🔥 Erreur critique ingestion : %s", e, exc_info=True
            )
            if not is_synthetic:
                crash_html = self.email_renderer.render_crash_report(
                    error_message=str(e)
                )
                notif_subject = (
                    "Erreur technique lors de l'ingestion - " f"{subject}"
                )
                self.mail_service.send_reply(
                    sender, notif_subject, crash_html, is_html=True
                )

    # -------------------------------------------------------------------------
    #  UTILITAIRES
    # -------------------------------------------------------------------------
    def _extract_preview(
        self, text: str, max_lines: int = 2, max_chars: int = 300
    ) -> str:
        """
        Renvoie un petit aperçu du texte (quelques lignes / caractères).
        Utilisé comme fallback pour le résumé d'email.
        """
        if not text:
            return ""

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return ""

        preview = "\n".join(lines[:max_lines])
        if len(preview) > max_chars:
            preview = preview[:max_chars].rstrip() + "..."
        return preview

    # -------------------------------------------------------------------------
    #  MODE CHAT
    # -------------------------------------------------------------------------
    def _handle_chat(
        self,
        uid: int,
        sender: str,
        subject: str,
        body: str,
        email_data: Dict[str, str],
    ) -> None:
        self.logger.debug("Mode CHAT détecté.")

        # Nettoyer le sujet pour enlever "Chat:" / "Question:" au début
        clean_subject = re.sub(
            r"(?i)^(chat|question)\s*:\s*", "", subject or ""
        ).strip()
        if not clean_subject:
            clean_subject = "Votre question"

        workspace: Optional[str] = None

        try:
            workspace = self.router.determine_workspace(email_data)
            self.client.ensure_workspace_exists(workspace)

            # Nettoyage du corps pour éviter disclaimers / historiques / quotes
            cleaned_body = self.cleaner.clean_body(body)
            query_content = cleaned_body if cleaned_body.strip() else body

            # Contexte enrichi pour le LLM
            query_message = (
                f"Sujet : {clean_subject}\n\nQuestion :\n{query_content}"
            )

            # Choix du moteur de recherche (RAG Proxy ou AnythingLLM)
            if self.config.use_rag_proxy_for_search:
                self.logger.info(
                    "🔍 [RAG Proxy] Recherche hybride pour '%s'...",
                    clean_subject,
                )
                response_text, sources = self._search_via_rag_proxy(
                    query_message, workspace
                )
            else:
                self.logger.info(
                    "🔍 [AnythingLLM] Recherche vectorielle pour '%s'...",
                    clean_subject,
                )
                response_text, sources = self.client.send_chat_query(
                    workspace, query_message
                )

            # --- SAUVEGARDE OPTIONNELLE (log-only, NON indexé) ---
            if self.config.save_chat_history:
                try:
                    self.logger.info(
                        "💾 Archivage du Chat (UID %s) demandé.", uid
                    )

                    # 1. Créer dossier secure (protégé par le verrou)
                    with self.state_lock:
                        secure_id = (
                            self.state_manager.get_or_create_secure_id(
                                self.state, uid
                            )
                        )
                    secure_folder = self.config.archive_path / secure_id
                    secure_folder.mkdir(parents=True, exist_ok=True)

                    # 2. Créer fichier de conversation
                    safe_subject = sanitize_filename(
                        subject, self.config.max_filename_length
                    )
                    if not safe_subject:
                        safe_subject = "Chat_Session"

                    chat_filename = f"CHAT_{safe_subject}.txt"
                    chat_path = secure_folder / chat_filename

                    real_date = time.strftime("%Y-%m-%d %H:%M")

                    with open(chat_path, "w", encoding="utf-8") as f:
                        f.write(f"Sujet : {subject}\n")
                        f.write(f"Workspace : {workspace}\n")
                        f.write(f"UID : {uid}\n")
                        f.write(f"Date : {real_date}\n")
                        f.write("-" * 30 + "\n\n")
                        f.write("QUESTION ORIGINALE :\n")
                        f.write(body or "")
                        f.write("\n\n" + "-" * 30 + "\n\n")
                        f.write("QUESTION NETTOYÉE POUR LE LLM :\n")
                        f.write(query_content or "")
                        f.write("\n\n" + "-" * 30 + "\n\n")
                        f.write("RÉPONSE IA :\n")
                        f.write(response_text or "")

                    self.logger.info(
                        "💾 Chat archivé (non indexé) dans %s", chat_path
                    )

                except Exception as e:
                    self.logger.error(
                        "⚠️ Erreur lors de l'archivage du chat : %s",
                        e,
                        exc_info=True,
                    )

            html_body = self.email_renderer.render_chat_response(
                response_text=response_text,
                sources=sources,
                archive_base_url=self.config.archive_base_url,
                workspace=workspace,
            )

            reply_subject = f"Réponse à votre question - {clean_subject}"
            self.mail_service.send_reply(
                sender, reply_subject, html_body, is_html=True
            )

        except Exception as e:
            self.logger.error("Erreur Chat : %s", e, exc_info=True)
            error_details = (
                f"Workspace : {workspace or 'indéterminé'}\n"
                f"UID : {uid}\n"
                f"Sujet : {subject}\n\n"
                f"Erreur : {e}"
            )
            error_html = self.email_renderer.render_crash_report(
                error_message=error_details
            )
            error_subject = (
                f"Erreur technique lors du chat - {clean_subject}"
            )
            self.mail_service.send_reply(
                sender, error_subject, error_html, is_html=True
            )

    def _search_via_rag_proxy(
        self, query: str, workspace: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Effectue une recherche via RAG Proxy (BM25 + Rerank) puis génère
        la réponse via LM Studio.
        """
        import requests

        # 1. Recherche RAG Proxy
        try:
            rag_url = f"{self.config.rag_proxy_url}/rag"
            payload: Dict[str, Any] = {
                "query": query,
                "top_k": 20,
                "final_k": 5,
                "use_bm25": True,
                "workspace": workspace,
            }

            timeout = getattr(self.config, "rag_proxy_timeout", 30)
            self.logger.debug("Appel RAG Proxy: %s", rag_url)
            resp = requests.post(rag_url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()

            chunks = data.get("chunks", [])
            sources: List[Dict[str, Any]] = []
            context_parts: List[str] = []

            for chunk in chunks:
                text = chunk.get("text", "")
                meta = chunk.get("metadata", {}) or {}
                score = chunk.get("score", 0.0)

                # Formatage source pour email_renderer
                source_title = meta.get("title", "Document inconnu")

                sources.append(
                    {
                        "title": source_title,
                        "text": text,
                        "score": score,
                    }
                )

                context_parts.append(
                    f"--- Document: {source_title} (Score: {score:.2f}) ---\n"
                    f"{text}\n"
                )

            context_text = "\n".join(context_parts)
            self.logger.info(
                "RAG Proxy a retourné %d chunks pertinents.", len(chunks)
            )

        except Exception as e:
            self.logger.error(
                "Erreur lors de la recherche RAG Proxy: %s", e, exc_info=True
            )
            raise

        # 2. Génération LM Studio
        try:
            system_prompt = (
                "Tu es un assistant utile qui répond aux questions en "
                "utilisant UNIQUEMENT le contexte fourni ci-dessous. Si la "
                "réponse n'est pas dans le contexte, dis-le poliment."
            )

            # Charger prompt spécifique si existe
            if workspace in self.config.workspace_prompts:
                system_prompt = self.config.workspace_prompts[workspace]
            elif self.config.default_system_prompt:
                system_prompt = self.config.default_system_prompt

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

            timeout = getattr(self.config, "llm_timeout", 60)
            self.logger.debug("Appel LLM Generation: %s", self.config.llm_api_url)
            llm_resp = requests.post(
                self.config.llm_api_url, json=llm_payload, timeout=timeout
            )
            llm_resp.raise_for_status()
            llm_data = llm_resp.json()

            response_text = llm_data["choices"][0]["message"]["content"]

            return response_text, sources

        except Exception as e:
            self.logger.error(
                "Erreur lors de la génération LLM: %s", e, exc_info=True
            )
            raise

    def _trigger_bm25_rebuild(self) -> None:
        """
        Hook pour lancer un rebuild BM25 en arrière-plan.

        Actuellement, MaintenanceService n'expose pas de méthode dédiée
        pour reconstruire un index BM25, donc on se contente de logguer l'appel.
        """
        try:
            self.logger.info(
                "Hook rebuild BM25 appelé, mais aucune implémentation "
                "spécifique n'est configurée dans MaintenanceService. "
                "Aucune action réalisée."
            )
        except Exception as e:
            self.logger.error(
                "Erreur lors du hook de rebuild BM25 : %s", e, exc_info=True
            )

    # -------------------------------------------------------------------------
    #  BOUCLE PRINCIPALE
    # -------------------------------------------------------------------------
    def run(self) -> None:
        self.logger.info("Démarrage Mail2RAG (Logs Nettoyés)...")

        # --- MAINTENANCE CHECK ---
        # Appliquer la configuration des workspaces (Prompts + température + refus)
        self.maintenance_service.apply_workspace_configuration()

        if self.config.sync_on_start:
            # Nettoyer l'archive si demandé (avant resync)
            if self.config.cleanup_archive_before_sync:
                self.maintenance_service.cleanup_archive()

            self.maintenance_service.sync_all()
            self.maintenance_service.sync_from_anythingllm()

        with self.state_lock:
            last_uid = int(self.state.get("last_uid", 0))
        self.logger.debug("État initial : last_uid=%s", last_uid)

        try:
            while True:
                try:
                    response = self.mail_service.fetch_new_messages(last_uid)
                    if not isinstance(response, dict):
                        if response is not None:
                            self.logger.warning(
                                "fetch_new_messages n'a pas retourné "
                                "un dict, valeur=%r",
                                response,
                            )
                        response = {}

                    if response:
                        raw_dump = str(response)
                        clean_dump = truncate_log(
                            raw_dump,
                            self.config.log_truncate_head,
                            self.config.log_truncate_tail,
                            self.config.log_max_line_length,
                        )
                        self.logger.debug(
                            "DEBUG: Réponse brute reçue : \n%s", clean_dump
                        )
                        self.logger.debug(
                            "DEBUG: Les UIDs reçus sont : %s",
                            list(response.keys()),
                        )

                    for uid, data in response.items():
                        self.logger.debug(
                            "DEBUG: Analyse UID %s. Est-ce que %s > %s ? %s",
                            uid,
                            uid,
                            last_uid,
                            uid > last_uid,
                        )

                        if uid > last_uid:
                            # On pousse le message dans la file des workers.
                            self.logger.debug(
                                "Envoi UID %s dans la file de traitement.",
                                uid,
                            )
                            self.task_queue.put((uid, data))

                            # Mise à jour de last_uid + state.json sous verrou
                            with self.state_lock:
                                last_uid = uid
                                self.state["last_uid"] = last_uid
                                self.state_manager.save_state(self.state)
                        else:
                            self.logger.debug(
                                "UID %s ignoré (<= %s)", uid, last_uid
                            )

                except Exception as e:
                    self.logger.error("Erreur boucle : %s", e, exc_info=True)
                    time.sleep(10)

                time.sleep(self.config.poll_interval)
        except KeyboardInterrupt:
            self.logger.info("Arrêt utilisateur.")


if __name__ == "__main__":
    app = Mail2RAGApp()
    app.run()
