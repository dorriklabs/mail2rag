import time
from pathlib import Path
from typing import Callable, List, Optional

from config import Config
from models import ParsedEmail
from services.ragproxy_client import RAGProxyClient
from services.mail import MailService
from services.router import RouterService
from services.processor import DocumentProcessor
from services.cleaner import CleanerService
from services.email_renderer import EmailRenderer
from services.support_qa import SupportQAService
from services.utils import sanitize_filename, decode_email_header


class IngestionService:
    """
    Service responsable de l'ingestion des emails via RAG Proxy.
    """

    def __init__(
        self,
        config: Config,
        logger,
        mail_service: MailService,
        router: RouterService,
        processor: DocumentProcessor,
        cleaner: CleanerService,
        support_qa_service: SupportQAService,
        email_renderer: EmailRenderer,
        get_secure_id: Callable[[int], str],
        trigger_bm25_rebuild: Callable[[Optional[str]], None],
    ) -> None:
        self.config = config
        self.logger = logger
        self.mail_service = mail_service
        self.router = router
        self.processor = processor
        self.cleaner = cleaner
        self.support_qa_service = support_qa_service
        self.email_renderer = email_renderer
        self.get_secure_id = get_secure_id
        self.trigger_bm25_rebuild = trigger_bm25_rebuild
        
        # RAG Proxy client
        self.ragproxy_client = RAGProxyClient(
            base_url=config.rag_proxy_url,
            timeout=config.rag_proxy_timeout,
        )
        self.logger.info("✅ RAG Proxy ingestion enabled")

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def ingest_email(self, email: ParsedEmail) -> None:
        """Pipeline complet d'ingestion RAG pour un email non-CHAT."""
        try:
            workspace = self.router.determine_workspace(email.email_data)

            safe_subject = sanitize_filename(
                email.subject, self.config.max_filename_length
            ) or self.config.default_subject

            # Identifiant opaque d'archive
            secure_id = self.get_secure_id(email.uid)
            secure_folder = self.config.archive_path / secure_id
            secure_folder.mkdir(parents=True, exist_ok=True)

            # Corps nettoyé / éventuelle réécriture Q/R
            cleaned_body = self._prepare_body_for_ingestion(email, workspace)

            # Résumé d'email (IA ou fallback simple)
            email_summary = self._build_email_summary(email, cleaned_body)

            # Fichier texte principal (email)
            body_path = self._write_email_body_file(
                email=email,
                workspace=workspace,
                cleaned_body=cleaned_body,
                email_summary=email_summary,
                secure_folder=secure_folder,
                safe_subject=safe_subject,
            )

            files_to_upload: List[str] = [str(body_path)]

            # Pièces jointes & analyses documentaires
            attachment_files = self._process_attachments(
                email=email,
                workspace=workspace,
                secure_folder=secure_folder,
                secure_id=secure_id,
            )
            files_to_upload.extend(attachment_files)

            # Upload + embeddings + notifications
            self._upload_and_index(
                email=email,
                workspace=workspace,
                files_to_upload=files_to_upload,
                secure_folder=secure_folder,
                secure_id=secure_id,
                email_summary=email_summary,
            )

        except Exception as e:
            self.logger.error("🔥 Erreur critique ingestion : %s", e, exc_info=True)
            if not email.is_synthetic:
                crash_html = self.email_renderer.render_crash_report(
                    error_message=str(e)
                )
                notif_subject = (
                    f"Erreur technique lors de l'ingestion - {email.subject}"
                )
                self.mail_service.send_reply(
                    email.sender, notif_subject, crash_html, is_html=True
                )

    # ------------------------------------------------------------------ #
    # Corps / résumé
    # ------------------------------------------------------------------ #
    def _prepare_body_for_ingestion(
        self,
        email: ParsedEmail,
        workspace: str,
    ) -> str:
        """Nettoyage ou réécriture Q/R du corps selon la config."""
        ws_cfg = self.config.workspace_settings.get(workspace, {})
        use_qa_rewrite = bool(ws_cfg.get("qa_rewrite", False))

        if not use_qa_rewrite:
            return self.cleaner.clean_body(email.body)

        self.logger.info(
            "🧠 Réécriture Q/R support activée pour UID %s dans workspace '%s'",
            email.uid,
            workspace,
        )
        try:
            return self.support_qa_service.rewrite_to_qa(
                subject=email.subject,
                sender=email.sender,
                raw_body=email.body,
            )
        except Exception as e:
            self.logger.error(
                "Erreur réécriture Q/R support (UID %s), "
                "fallback vers nettoyage classique : %s",
                email.uid,
                e,
                exc_info=True,
            )
            return self.cleaner.clean_body(email.body)

    def _build_email_summary(
        self,
        email: ParsedEmail,
        cleaned_body: str,
    ) -> Optional[str]:
        """Génère un résumé IA ou un aperçu simple."""
        if not cleaned_body:
            return None

        if not self.config.enable_email_summary:
            return self._extract_preview(cleaned_body)

        try:
            self.logger.info("📝 Génération résumé IA pour UID %s...", email.uid)
            return self.support_qa_service.generate_email_summary(
                subject=email.subject,
                cleaned_body=cleaned_body,
            )
        except Exception as e:
            self.logger.warning("⚠️ Échec génération résumé IA : %s", e)
            return self._extract_preview(cleaned_body)

    @staticmethod
    def _extract_preview(
        text: str,
        max_lines: int = 2,
        max_chars: int = 300,
    ) -> str:
        """Petit aperçu des premières lignes du texte."""
        if not text:
            return ""

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return ""

        preview = "\n".join(lines[:max_lines])
        if len(preview) > max_chars:
            preview = preview[:max_chars].rstrip() + "..."
        return preview

    # ------------------------------------------------------------------ #
    # Fichier principal d'email
    # ------------------------------------------------------------------ #
    def _write_email_body_file(
        self,
        email: ParsedEmail,
        workspace: str,
        cleaned_body: str,
        email_summary: Optional[str],
        secure_folder: Path,
        safe_subject: str,
    ) -> Path:
        """Crée le fichier texte contenant l'email (métadonnées + corps)."""
        body_filename = f"{email.uid}_{safe_subject}.txt"
        body_path = secure_folder / body_filename

        real_date = email.date or time.strftime("%Y-%m-%d %H:%M")

        with body_path.open("w", encoding="utf-8") as f:
            f.write(f"Sujet : {email.subject}\n")
            f.write(f"De : {email.sender}\n")
            if email.to:
                f.write(f"À : {email.to}\n")
            if email.cc:
                f.write(f"Cc : {email.cc}\n")
            f.write(f"Date : {real_date}\n")
            if email.message_id:
                f.write(f"Message-ID : {email.message_id}\n")
            f.write(f"IMAP_UID : {email.uid}\n")
            f.write(f"Workspace : {workspace}\n")
            if email_summary:
                f.write(f"Résumé : {email_summary}\n")
            if email.is_synthetic:
                f.write(
                    "Source : Email synthétique (Upload manuel)\n"
                )
            f.write("-" * 30 + "\n\n")
            f.write(cleaned_body)

        return body_path

    # ------------------------------------------------------------------ #
    # Pièces jointes / analyse documentaire
    # ------------------------------------------------------------------ #
    def _process_attachments(
        self,
        email: ParsedEmail,
        workspace: str,  # réservé pour usages futurs
        secure_folder: Path,
        secure_id: str,
    ) -> List[str]:
        """Traite les pièces jointes et retourne les chemins à uploader."""
        msg = email.msg
        if not msg.is_multipart():
            return []

        files_to_upload: List[str] = []

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            filename = decode_email_header(filename)
            content = part.get_payload(decode=True)

            # Filtrage via CleanerService
            if not self.cleaner.is_valid_attachment(filename, content):
                continue

            safe_pj_name = (
                f"{email.uid}_"
                f"{sanitize_filename(filename, self.config.max_filename_length)}"
            )
            filepath = secure_folder / safe_pj_name

            self.logger.debug(
                "Sauvegarde pièce jointe UID %s : %s",
                email.uid,
                filepath.name,
            )

            with filepath.open("wb") as f:
                f.write(content)

            public_link = (
                f"{self.config.archive_base_url}/{secure_id}/{filepath.name}"
            )
            ext = Path(filename).suffix.lower()

            if ext in {".png", ".jpg", ".jpeg", ".pdf"}:
                analysis_text = self.processor.analyze_document(str(filepath))
                if analysis_text:
                    analysis_path = secure_folder / f"{safe_pj_name}_analysis.txt"
                    with analysis_path.open("w", encoding="utf-8") as f:
                        f.write(f"Source Document (Lien) : {public_link}\n")
                        f.write(
                            f"Email Parent (Sujet) : {email.subject}\n"
                        )
                        real_date = email.date or time.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        f.write(f"Date Email : {real_date}\n")
                        f.write("-" * 30 + "\n")
                        f.write(analysis_text)

                    files_to_upload.append(str(analysis_path))
                    self.logger.info(
                        "Optimisation : Upload de l'analyse uniquement pour %s",
                        filename,
                    )
                else:
                    files_to_upload.append(str(filepath))
            else:
                files_to_upload.append(str(filepath))

        return files_to_upload

    # ------------------------------------------------------------------ #
    # Upload / indexation / notifications
    # ------------------------------------------------------------------ #
    def _upload_and_index(
        self,
        email: ParsedEmail,
        workspace: str,
        files_to_upload: List[str],
        secure_folder: Path,
        secure_id: str,
        email_summary: Optional[str],
    ) -> None:
        """Upload, embeddings, notifications et hook BM25."""
        if not files_to_upload:
            self.logger.info("Aucun document pertinent à indexer.")
            if not email.is_synthetic:
                info_html = self.email_renderer.render_ingestion_info(
                    subject=email.subject
                )
                notif_subject = f"Aucun document indexé - {email.subject}"
                self.mail_service.send_reply(
                    email.sender, notif_subject, info_html, is_html=True
                )
            return

        # Ingestion via RAG Proxy
        success, indexed_count = self._upload_via_ragproxy(
            email=email,
            workspace=workspace,
            files_to_upload=files_to_upload,
            secure_id=secure_id,
        )
        
        if not success:
            self.logger.error("❌ Échec indexation '%s'.", workspace)
            if not email.is_synthetic:
                error_html = self.email_renderer.render_ingestion_error()
                notif_subject = f"Erreur d'indexation - {email.subject}"
                self.mail_service.send_reply(
                    email.sender, notif_subject, error_html, is_html=True
                )
            return

        self.logger.info(
            "✅ Succès : %d document(s)/chunk(s) indexé(s) dans '%s'",
            indexed_count,
            workspace,
        )

        if email.is_synthetic:
            return

        # Email de confirmation avec résumé + liste des fichiers
        files_list = sorted(
            [f.name for f in secure_folder.iterdir() if f.is_file()]
        )

        html_report = self.email_renderer.render_ingestion_success(
            workspace=workspace,
            files=files_list,
            archive_url=f"{self.config.archive_base_url}/{secure_id}/",
            email_summary=email_summary,
        )
        notif_subject = f"Ingestion réussie - {email.subject}"
        self.mail_service.send_reply(
            email.sender, notif_subject, html_report, is_html=True
        )

        # Auto-rebuild BM25 index en arrière-plan (non-bloquant)
        if self.config.auto_rebuild_bm25:
            import threading

            self.logger.debug(
                "Déclenchement auto-rebuild BM25 (AUTO_REBUILD_BM25=true)."
            )
            threading.Thread(
                target=self.trigger_bm25_rebuild,
                args=(workspace,),
                name="bm25-auto-rebuild",
                daemon=True,
            ).start()
        else:
            self.logger.debug(
                "Auto-rebuild BM25 désactivé (AUTO_REBUILD_BM25=false)."
            )
    
    # ------------------------------------------------------------------ #
    # Upload helper (RAG Proxy)
    # ------------------------------------------------------------------ #
    def _upload_via_ragproxy(
        self,
        email: ParsedEmail,
        workspace: str,
        files_to_upload: List[str],
        secure_id: str = None,
    ) -> tuple[bool, int]:
        """
        Upload et indexation via RAG Proxy avec chunking intelligent.
        
        Returns:
            (success, total_chunks) - total_chunks = nombre de chunks créés
        """
        total_chunks = 0
        errors = 0
        
        for file_path in files_to_upload:
            try:
                # Extraction du texte depuis le fichier
                text_content = self._extract_text_from_file(file_path)
                
                if not text_content or not text_content.strip():
                    self.logger.warning(f"Fichier vide ou non-textuel ignoré : {file_path}")
                    continue
                
                # Métadonnées enrichies
                filename = Path(file_path).name
                metadata = {
                    "uid": str(email.uid),
                    "subject": email.subject,
                    "sender": email.sender,
                    "date": email.date or time.strftime("%Y-%m-%d %H:%M"),
                    "filename": filename,
                }
                
                # Ajouter le lien d'archive si disponible
                if secure_id and self.config.archive_base_url:
                    metadata["archive_url"] = f"{self.config.archive_base_url}/{secure_id}/{filename}"
                
                # Ajout métadonnées email optionnelles
                if email.to:
                    metadata["to"] = email.to
                if email.cc:
                    metadata["cc"] = email.cc
                if email.message_id:
                    metadata["message_id"] = email.message_id
                
                # Ingestion via RAG Proxy
                result = self.ragproxy_client.ingest_document(
                    collection=workspace,
                    text=text_content,
                    metadata=metadata,
                    chunk_size=self.config.chunk_size,
                    chunk_overlap=self.config.chunk_overlap,
                )
                
                if result.get("status") == "ok":
                    chunks_count = result.get("chunks_created", 0)
                    total_chunks += chunks_count
                    self.logger.info(
                        f"Document ingéré : {Path(file_path).name} → {chunks_count} chunks"
                    )
                else:
                    self.logger.error(
                        f"Échec ingestion de {Path(file_path).name} : {result.get('message')}"
                    )
                    errors += 1
                    
            except Exception as e:
                self.logger.error(
                    f"Exception lors de l'ingestion de {file_path} : {e}",
                    exc_info=True,
                )
                errors += 1
        
        # Succès si au moins un document a été ingéré
        success = total_chunks > 0
        
        if errors > 0:
            self.logger.warning(
                f"Ingestion terminée avec {errors} erreur(s), {total_chunks} chunks créés"
            )
        
        return success, total_chunks
    
    def _extract_text_from_file(self, file_path: str) -> str:
        """
        Extrait le contenu texte d'un fichier.
        
        Pour les fichiers .txt, lit directement.
        Pour les autres, retourne le contenu si déjà du texte.
        
        Args:
            file_path: Chemin du fichier
            
        Returns:
            Contenu textuel ou chaîne vide
        """
        try:
            path = Path(file_path)
            
            # Lire directement les fichiers texte
            if path.suffix.lower() in {".txt", ".md", ".html", ".xml", ".json", ".csv"}:
                return path.read_text(encoding="utf-8", errors="ignore")
            
            # Pour les autres, essayer de lire quand même (peut-être déjà du texte analysé)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                # Vérifier que c'est du texte lisible (pas du binaire)
                if len(content) > 0 and content.isprintable() or '\n' in content:
                    return content
            except:
                pass
            
            # Si ce n'est pas du texte, retourner vide
            # (les fichiers analysés comme _analysis.txt seront traités séparément)
            self.logger.debug(f"Fichier non-textuel : {path.name}")
            return ""
            
        except Exception as e:
            self.logger.error(f"Erreur extraction texte de {file_path} : {e}")
            return ""
