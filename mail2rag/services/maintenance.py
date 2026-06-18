import hashlib
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from config import Config
from services.router import RouterService
from services.mail import MailService
from services.ragproxy_client import RAGProxyClient

logger = logging.getLogger(__name__)


class MaintenanceService:
    """
    Service de maintenance / synchronisation entre l'archive locale
    et le système RAG.

    Important :
    - sync_all() est une opération de maintenance lourde.
    - Elle réindexe les fichiers .txt présents dans l'archive locale.
    - Elle doit rester désactivée au démarrage normal.
    """

    TEST_MARKERS = (
        "test-mock-id@dsiatlantic.com",
        "<test-mock-id@dsiatlantic.com>",
    )

    METADATA_RE = re.compile(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$")

    def __init__(
        self,
        config: Config,
        router: RouterService,
        mail_service: MailService,
    ) -> None:
        self.config = config
        self.router = router
        self.mail_service = mail_service
        self.ragproxy_client = RAGProxyClient(
            base_url=config.rag_proxy_url,
            timeout=config.rag_proxy_timeout,
        )

    # ------------------------------------------------------------------ #
    # Archive locale
    # ------------------------------------------------------------------ #
    def cleanup_archive(self) -> None:
        """
        Supprime TOUS les dossiers dans l'archive.

        Sécurité :
        - Refuse par défaut de supprimer sans confirmation explicite.
        - Pour autoriser :
          CONFIRM_ARCHIVE_CLEANUP=I_UNDERSTAND_DELETE_ARCHIVE
        """
        archive_path = self.config.archive_path

        if not archive_path.exists():
            logger.info("📂 Dossier d'archive inexistant, rien à nettoyer.")
            return

        confirm = os.getenv("CONFIRM_ARCHIVE_CLEANUP", "")
        allow_unsafe = self._env_bool("ALLOW_UNSAFE_ARCHIVE_CLEANUP", False)

        if confirm != "I_UNDERSTAND_DELETE_ARCHIVE" and not allow_unsafe:
            logger.error(
                "❌ Nettoyage archive refusé par sécurité. "
                "Définir CONFIRM_ARCHIVE_CLEANUP=I_UNDERSTAND_DELETE_ARCHIVE "
                "pour autoriser la suppression."
            )
            return

        logger.warning(
            "🗑️ NETTOYAGE DE L'ARCHIVE : suppression irréversible des dossiers..."
        )

        try:
            folder_count = sum(
                1 for item in archive_path.iterdir() if item.is_dir()
            )

            for item in archive_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                    logger.debug("   🗑️ Supprimé : %s", item.name)

            logger.info("✅ Archive nettoyée : %d dossiers supprimés.", folder_count)

        except Exception as e:
            logger.error("❌ Erreur lors du nettoyage de l'archive : %s", e)
            raise

    # ------------------------------------------------------------------ #
    # Resynchronisation archive -> RAG Proxy
    # ------------------------------------------------------------------ #
    def sync_all(self) -> None:
        """
        Parcourt l'archive locale et réingère les documents .txt via RAG Proxy.

        Cette version utilise :
        - document_key stable ;
        - content_hash SHA256 ;
        - recherche directe par métadonnées dans RAG Proxy ;
        - plus aucune recherche sémantique approximative par filename.
        """
        archive_path = self.config.archive_path

        logger.warning(
            "🔄 SYNC_ALL : démarrage resynchronisation archive -> RAG."
        )

        if not archive_path.exists():
            logger.warning("⚠️ Dossier d'archive introuvable. Rien à synchroniser.")
            return

        dry_run = self._env_bool("RESYNC_DRY_RUN", False)
        if dry_run:
            logger.warning(
                "🧪 RESYNC_DRY_RUN=true : simulation uniquement, aucune suppression/ingestion."
            )

        block_test_documents = self._env_bool("RESYNC_BLOCK_TEST_DOCUMENTS", True)
        reindex_changed = self._env_bool("RESYNC_REINDEX_CHANGED", True)
        delete_stale_before_reindex = self._env_bool(
            "RESYNC_DELETE_STALE_BEFORE_REINDEX",
            True,
        )
        compat_filename_fallback = self._env_bool(
            "RESYNC_COMPAT_FILENAME_FALLBACK",
            True,
        )
        enforce_known_workspaces = self._env_bool(
            "RESYNC_ENFORCE_KNOWN_WORKSPACES",
            False,
        )

        valid_workspaces = self._known_workspaces()

        count_folders = 0
        count_indexed = 0
        count_skipped_existing = 0
        count_skipped_test = 0
        count_skipped_invalid_workspace = 0
        count_deleted_stale = 0
        count_dry_run_actions = 0
        count_errors = 0

        folders = sorted(
            [item for item in archive_path.iterdir() if item.is_dir()],
            key=lambda p: p.name,
        )

        logger.info("📦 Dossiers d'archive détectés : %d", len(folders))

        for folder in folders:
            secure_id = folder.name
            count_folders += 1

            logger.info("📂 Traitement archive : %s", secure_id)

            folder_workspace = self._determine_workspace_from_folder(folder)

            txt_files = sorted(
                [
                    f for f in folder.iterdir()
                    if f.is_file()
                    and f.suffix.lower() == ".txt"
                    and not f.name.startswith(".")
                ],
                key=lambda p: p.name,
            )

            if not txt_files:
                logger.debug("   ℹ️ Aucun fichier .txt dans %s", secure_id)
                continue

            for file_path in txt_files:
                try:
                    text_content = file_path.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )

                    if not text_content.strip():
                        logger.debug("   ⏭️ Fichier vide ignoré : %s", file_path.name)
                        continue

                    archive_metadata = self._extract_archive_metadata(text_content)

                    if block_test_documents and self._looks_like_test_document(
                        file_path=file_path,
                        text=text_content,
                        metadata=archive_metadata,
                    ):
                        count_skipped_test += 1
                        logger.warning(
                            "   🧪 Document de test ignoré : %s/%s",
                            secure_id,
                            file_path.name,
                        )
                        continue

                    workspace = self._normalize_workspace(
                        archive_metadata.get("workspace") or folder_workspace
                    )

                    if not workspace:
                        count_skipped_invalid_workspace += 1
                        logger.warning(
                            "   ⚠️ Workspace introuvable, fichier ignoré : %s/%s",
                            secure_id,
                            file_path.name,
                        )
                        continue

                    if valid_workspaces and workspace not in valid_workspaces:
                        message = (
                            f"Workspace inconnu '{workspace}' pour "
                            f"{secure_id}/{file_path.name}"
                        )

                        if enforce_known_workspaces:
                            count_skipped_invalid_workspace += 1
                            logger.warning("   ⛔ %s. Fichier ignoré.", message)
                            continue

                        logger.warning(
                            "   ⚠️ %s. Ingestion autorisée car "
                            "RESYNC_ENFORCE_KNOWN_WORKSPACES=false.",
                            message,
                        )

                    content_hash = self._sha256(text_content)
                    document_key = self._document_key(
                        workspace=workspace,
                        secure_id=secure_id,
                        filename=file_path.name,
                    )

                    existence = self._check_document_existence(
                        workspace=workspace,
                        document_key=document_key,
                        content_hash=content_hash,
                        secure_id=secure_id,
                        filename=file_path.name,
                        compat_filename_fallback=compat_filename_fallback,
                    )

                    if existence["exists"] and existence["same_hash"] is True:
                        count_skipped_existing += 1
                        logger.info(
                            "   ⏭️ Déjà indexé et inchangé : %s",
                            file_path.name,
                        )
                        continue

                    if existence["exists"] and existence["same_hash"] is False:
                        if not reindex_changed:
                            count_skipped_existing += 1
                            logger.warning(
                                "   ⚠️ Document existant mais hash différent. "
                                "Réindexation désactivée : %s",
                                file_path.name,
                            )
                            continue

                        if delete_stale_before_reindex:
                            if dry_run:
                                count_dry_run_actions += 1
                                logger.warning(
                                    "   🧪 DRY-RUN : aurait supprimé ancienne version avant réindexation : %s",
                                    file_path.name,
                                )
                            else:
                                deleted = self._delete_existing_document(
                                    workspace=workspace,
                                    document_key=document_key,
                                    secure_id=secure_id,
                                    filename=file_path.name,
                                    used_legacy_match=existence.get("used_legacy_match", False),
                                )
                                count_deleted_stale += deleted

                    elif existence["exists"] and existence["same_hash"] is None:
                        # Cas ancien : document existant sans content_hash.
                        # Par défaut, on évite de dupliquer.
                        count_skipped_existing += 1
                        logger.warning(
                            "   ⚠️ Document existant sans content_hash, ignoré pour éviter doublon : %s",
                            file_path.name,
                        )
                        continue

                    if dry_run:
                        count_dry_run_actions += 1
                        logger.warning(
                            "   🧪 DRY-RUN : aurait indexé collection=%s fichier=%s document_key=%s",
                            workspace,
                            file_path.name,
                            document_key,
                        )
                        continue

                    metadata = self._build_ingestion_metadata(
                        workspace=workspace,
                        secure_id=secure_id,
                        file_path=file_path,
                        content_hash=content_hash,
                        document_key=document_key,
                        archive_metadata=archive_metadata,
                    )

                    logger.info(
                        "   ⬆️ Ingestion : collection=%s fichier=%s",
                        workspace,
                        file_path.name,
                    )

                    result = self.ragproxy_client.ingest_document(
                        collection=workspace,
                        text=text_content,
                        metadata=metadata,
                        chunk_size=getattr(self.config, "chunk_size", 800),
                        chunk_overlap=getattr(self.config, "chunk_overlap", 100),
                    )

                    if result.get("status") == "ok":
                        count_indexed += 1
                        logger.info(
                            "   ✅ Indexé : %s (%d chunks)",
                            file_path.name,
                            int(result.get("chunks_created", 0) or 0),
                        )
                    else:
                        count_errors += 1
                        logger.error(
                            "   ❌ Échec ingestion %s : %s",
                            file_path.name,
                            result.get("message", "erreur inconnue"),
                        )

                except Exception as e:
                    count_errors += 1
                    logger.error(
                        "❌ Erreur réingestion %s/%s : %s",
                        secure_id,
                        file_path.name,
                        e,
                        exc_info=True,
                    )

        logger.info(
            "🎉 Synchronisation terminée : "
            "%d dossiers, %d indexés, %d déjà présents, "
            "%d tests ignorés, %d workspaces invalides, "
            "%d anciens supprimés, %d actions dry-run, %d erreurs.",
            count_folders,
            count_indexed,
            count_skipped_existing,
            count_skipped_test,
            count_skipped_invalid_workspace,
            count_deleted_stale,
            count_dry_run_actions,
            count_errors,
        )

    def _check_document_existence(
        self,
        workspace: str,
        document_key: str,
        content_hash: str,
        secure_id: str,
        filename: str,
        compat_filename_fallback: bool,
    ) -> Dict[str, Any]:
        """
        Vérifie l'existence du document.

        Priorité :
        1. document_key + content_hash ;
        2. fallback exact filename + secure_id pour anciens chunks.
        """
        result = self.ragproxy_client.document_exists(
            collection=workspace,
            document_key=document_key,
            content_hash=content_hash,
            filters={},
        )

        if result.get("status") == "ok" and result.get("exists"):
            return {
                "exists": True,
                "same_hash": result.get("same_hash"),
                "used_legacy_match": False,
                "matches": result.get("matches", []),
            }

        if not compat_filename_fallback:
            return {
                "exists": False,
                "same_hash": False,
                "used_legacy_match": False,
                "matches": [],
            }

        legacy = self.ragproxy_client.search_by_metadata(
            collection=workspace,
            filters={
                "filename": filename,
                "secure_id": secure_id,
            },
            limit=10000,
            with_text=False,
        )

        if legacy.get("status") != "ok" or int(legacy.get("count", 0) or 0) == 0:
            return {
                "exists": False,
                "same_hash": False,
                "used_legacy_match": False,
                "matches": [],
            }

        matches = legacy.get("matches", [])
        hashes = {
            (m.get("metadata") or {}).get("content_hash")
            for m in matches
            if (m.get("metadata") or {}).get("content_hash") is not None
        }

        if not hashes:
            same_hash = None
        else:
            same_hash = hashes == {content_hash}

        return {
            "exists": True,
            "same_hash": same_hash,
            "used_legacy_match": True,
            "matches": matches,
        }

    def _delete_existing_document(
        self,
        workspace: str,
        document_key: str,
        secure_id: str,
        filename: str,
        used_legacy_match: bool,
    ) -> int:
        """
        Supprime les anciens chunks avant réindexation pour éviter les doublons.
        """
        if used_legacy_match:
            filters = {
                "filename": filename,
                "secure_id": secure_id,
            }
        else:
            filters = {
                "document_key": document_key,
            }

        result = self.ragproxy_client.delete_by_metadata(
            collection=workspace,
            filters=filters,
        )

        deleted = int(result.get("deleted_count", 0) or 0)

        if deleted:
            logger.info(
                "   🧹 Ancienne version supprimée : %d chunks pour %s",
                deleted,
                filename,
            )

        return deleted

    def _determine_workspace_from_folder(self, folder: Path) -> str:
        """
        Détermine le workspace d'un dossier d'archive.

        Ordre :
        1. ligne 'Workspace :' dans un fichier .txt ;
        2. routage via sujet/expéditeur/body ;
        3. fallback vers default_workspace uniquement si
           RESYNC_ALLOW_DEFAULT_WORKSPACE_FALLBACK=true.
        """
        candidate_files = sorted(folder.glob("*.txt"), key=lambda p: p.name)

        subject = ""
        sender = ""
        body_content = ""

        for txt_file in candidate_files:
            try:
                content = txt_file.read_text(encoding="utf-8", errors="ignore")
                metadata = self._extract_archive_metadata(content)

                workspace = self._normalize_workspace(metadata.get("workspace"))
                if workspace:
                    return workspace

                if metadata.get("subject"):
                    subject = metadata["subject"]

                if metadata.get("sender"):
                    sender = metadata["sender"]

                if subject and sender:
                    body_content = content
                    break

            except Exception as e:
                logger.debug("   ⚠️ Impossible de lire %s : %s", txt_file, e)
                continue

        if subject and sender:
            email_data = {
                "subject": subject,
                "from": sender,
                "body": body_content,
            }
            workspace = self.router.determine_workspace(email_data)
            return self._normalize_workspace(workspace)

        if self._env_bool("RESYNC_ALLOW_DEFAULT_WORKSPACE_FALLBACK", False):
            logger.warning(
                "   ⚠️ Pas de métadonnées dans %s. "
                "Fallback vers default_workspace=%s.",
                folder.name,
                self.config.default_workspace,
            )
            return self._normalize_workspace(self.config.default_workspace)

        logger.warning(
            "   ⚠️ Pas de métadonnées workspace/sujet/expéditeur dans %s.",
            folder.name,
        )
        return ""

    # ------------------------------------------------------------------ #
    # Configuration des workspaces
    # ------------------------------------------------------------------ #
    def apply_workspace_configuration(self) -> None:
        """
        Log la configuration des workspaces.

        Cette méthode n'ingère rien.
        """
        logger.info("⚙️ Configuration des Workspaces (log uniquement)...")

        ws_prompts = getattr(self.config, "workspace_prompts", {}) or {}
        ws_settings = getattr(self.config, "workspace_settings", {}) or {}
        local_slugs = set(ws_prompts.keys()) | set(ws_settings.keys())

        if not local_slugs:
            logger.info("ℹ️ Aucun workspace custom déclaré.")
            return

        for slug in sorted(local_slugs):
            prompt = ws_prompts.get(slug)
            settings = ws_settings.get(slug, {})
            temp = settings.get(
                "temperature",
                getattr(self.config, "default_llm_temperature", 0.7),
            )
            logger.info(
                "✅ Workspace '%s' : temp=%s, prompt=%s",
                slug,
                temp,
                "custom" if prompt else "default",
            )

        logger.info("✅ Configuration des Workspaces terminée.")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _extract_archive_metadata(self, text: str) -> Dict[str, str]:
        metadata: Dict[str, str] = {}

        key_map = {
            "sujet": "subject",
            "subject": "subject",
            "de": "sender",
            "from": "sender",
            "a": "to",
            "à": "to",
            "to": "to",
            "date": "date",
            "message_id": "message_id",
            "message-id": "message_id",
            "imap_uid": "imap_uid",
            "uid": "imap_uid",
            "workspace": "workspace",
        }

        for line in text.splitlines()[:100]:
            match = self.METADATA_RE.match(line)
            if not match:
                continue

            raw_key = match.group(1).strip().lower()
            raw_key_alt = raw_key.replace("-", "_").replace(" ", "_")
            value = match.group(2).strip()

            normalized_key = key_map.get(raw_key) or key_map.get(raw_key_alt)

            if normalized_key and value:
                metadata[normalized_key] = value

        return metadata

    def _build_ingestion_metadata(
        self,
        workspace: str,
        secure_id: str,
        file_path: Path,
        content_hash: str,
        document_key: str,
        archive_metadata: Dict[str, str],
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "filename": file_path.name,
            "source": "archive_resync",
            "secure_id": secure_id,
            "workspace": workspace,
            "archive_path": f"{secure_id}/{file_path.name}",
            "content_hash": content_hash,
            "document_key": document_key,
            "resync": True,
        }

        for key in (
            "subject",
            "sender",
            "to",
            "date",
            "message_id",
            "imap_uid",
        ):
            value = archive_metadata.get(key)
            if value:
                metadata[key] = value

        return metadata

    def _known_workspaces(self) -> set:
        workspaces = set()

        ws_prompts = getattr(self.config, "workspace_prompts", {}) or {}
        ws_settings = getattr(self.config, "workspace_settings", {}) or {}

        workspaces.update(str(k).strip() for k in ws_prompts.keys() if str(k).strip())
        workspaces.update(str(k).strip() for k in ws_settings.keys() if str(k).strip())

        default_workspace = self._normalize_workspace(
            getattr(self.config, "default_workspace", "")
        )

        if default_workspace:
            workspaces.add(default_workspace)

        return workspaces

    def _normalize_workspace(self, workspace: Optional[str]) -> str:
        if workspace is None:
            return ""

        workspace = str(workspace).strip()

        if not workspace:
            return ""

        workspace = workspace.replace(" ", "-").lower()
        workspace = re.sub(r"[^a-z0-9_.-]", "", workspace)

        return workspace

    def _looks_like_test_document(
        self,
        file_path: Path,
        text: str,
        metadata: Dict[str, str],
    ) -> bool:
        lowered_text = text.lower()

        for marker in self.TEST_MARKERS:
            if marker.lower() in lowered_text:
                return True

        message_id = metadata.get("message_id", "").lower().strip("<>")
        if message_id == "test-mock-id@dsiatlantic.com":
            return True

        name = file_path.name.lower()
        if name.startswith("test_") or name.startswith("demo_"):
            return True

        return False

    def _sha256(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def _document_key(self, workspace: str, secure_id: str, filename: str) -> str:
        raw = f"{workspace}:{secure_id}:{filename}"
        digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
        return f"{workspace}:{secure_id}:{digest[:16]}"

    @staticmethod
    def _env_bool(name: str, default: bool = False) -> bool:
        value = os.getenv(name)

        if value is None:
            return default

        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
