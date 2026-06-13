import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

from config import Config
from services.router import RouterService
from services.mail import MailService
from services.ragproxy_client import RAGProxyClient

logger = logging.getLogger(__name__)


class MaintenanceService:
    """
    Service de maintenance / synchronisation entre l'archive locale
    et le système RAG.

    - Nettoyage complet de l'archive
    - Resynchronisation archive -> RAG Proxy
    - Application des paramètres de workspaces (prompts, température)
    """

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
        Supprime TOUS les dossiers dans l'archive avant resync.
        ⚠️ ATTENTION : Cette opération est irréversible !
        """
        if not self.config.archive_path.exists():
            logger.info("📂 Dossier d'archive inexistant, rien à nettoyer.")
            return

        logger.warning(
            "🗑️ NETTOYAGE DE L'ARCHIVE : Suppression de tous les dossiers..."
        )

        try:
            folder_count = sum(
                1 for item in self.config.archive_path.iterdir() if item.is_dir()
            )

            for item in self.config.archive_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                    logger.debug("   🗑️ Supprimé : %s", item.name)

            logger.info("✅ Archive nettoyée : %d dossiers supprimés.", folder_count)

        except Exception as e:
            logger.error("❌ Erreur lors du nettoyage de l'archive : %s", e)
            raise

    def sync_all(self) -> None:
        """
        Parcourt l'archive locale et ré-ingère tous les documents via RAG Proxy.
        Utilise le RouterService pour redéterminer le workspace cible.
        """
        logger.info("🔄 Démarrage de la synchronisation complète (Smart Resync)...")

        if not self.config.archive_path.exists():
            logger.warning(
                "⚠️ Dossier d'archive introuvable. Rien à synchroniser."
            )
            return

        count_folders = 0
        count_files = 0

        for folder in self.config.archive_path.iterdir():
            if not folder.is_dir():
                continue

            secure_id = folder.name
            logger.info("📂 Traitement du dossier : %s", secure_id)

            workspace = self._determine_workspace_from_folder(folder)
            if not workspace:
                logger.warning(
                    "⚠️ Impossible de déterminer le workspace pour %s. Ignoré.",
                    secure_id,
                )
                continue

            # Ne traiter que les fichiers .txt (texte extrait, pas les binaires)
            txt_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".txt"]
            binary_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() != ".txt"]
            
            if binary_files:
                logger.debug(
                    "   ℹ️ Fichiers binaires ignorés : %s",
                    ", ".join(f.name for f in binary_files[:3]) + ("..." if len(binary_files) > 3 else "")
                )

            for file_path in txt_files:
                # Ignorer fichiers cachés / temporaires
                if file_path.name.startswith("."):
                    continue

                try:
                    # Vérifier si ce document existe déjà (par filename)
                    # via une recherche dans la collection
                    existing = self.ragproxy_client.search(
                        query=file_path.name,
                        collection=workspace,
                        top_k=1,
                        use_bm25=False,  # Recherche simple
                    )
                    
                    # Si un chunk avec ce filename existe, ignorer
                    chunks = existing.get("chunks", [])
                    if chunks:
                        for chunk in chunks:
                            if chunk.get("metadata", {}).get("filename") == file_path.name:
                                logger.debug("   ⏭️ Déjà indexé, ignoré : %s", file_path.name)
                                break
                        else:
                            # Filename différent, on peut ingérer
                            pass
                        if any(c.get("metadata", {}).get("filename") == file_path.name for c in chunks):
                            continue
                    
                    logger.debug("   ⬆️ Ré-ingestion : %s", file_path.name)
                    text_content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if text_content.strip():
                        metadata = {
                            "filename": file_path.name,
                            "source": "archive_resync",
                            "secure_id": secure_id,
                        }
                        result = self.ragproxy_client.ingest_document(
                            collection=workspace,
                            text=text_content,
                            metadata=metadata,
                            chunk_size=self.config.chunk_size,
                            chunk_overlap=self.config.chunk_overlap,
                        )
                        if result.get("status") == "ok":
                            count_files += 1
                            logger.debug(
                                "   ✅ Indexé : %s (%d chunks)",
                                file_path.name,
                                result.get("chunks_created", 0),
                            )
                except Exception as e:
                    logger.error("Erreur ré-ingestion %s : %s", file_path.name, e)

            count_folders += 1

        logger.info(
            "🎉 Synchronisation terminée : %d dossiers, %d fichiers traités.",
            count_folders,
            count_files,
        )

    def _determine_workspace_from_folder(self, folder: Path) -> str:
        """
        Tente de reconstruire le contexte (Sujet, Expéditeur) à partir
        des fichiers textes présents dans le dossier pour relancer le routage.

        Si la ligne 'Workspace :' est présente, on l'utilise directement.
        Sinon, on reconstruit un email_data et on laisse RouterService décider.
        """
        candidate_files = list(folder.glob("*.txt"))

        subject = "Inconnu"
        sender = "Inconnu"
        body_content = ""
        found_metadata = False

        for txt_file in candidate_files:
            try:
                content = txt_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
                lines = content.splitlines()

                # Lecture des premières lignes pour trouver métadonnées
                for line in lines[:20]:
                    if line.startswith("Workspace : "):
                        return line.replace("Workspace : ", "").strip()

                    if line.startswith("Sujet : "):
                        subject = line.replace("Sujet : ", "").strip()
                    elif line.startswith("De : "):
                        sender = line.replace("De : ", "").strip()

                if subject != "Inconnu" and sender != "Inconnu":
                    body_content = content
                    found_metadata = True
                    break

            except Exception as e:
                logger.debug(
                    "   ⚠️ Impossible de lire %s : %s", txt_file, e
                )
                continue

        if not found_metadata:
            logger.debug(
                "   ℹ️ Pas de métadonnées trouvées dans %s. "
                "Utilisation du workspace par défaut.",
                folder.name,
            )
            return self.config.default_workspace

        email_data = {
            "subject": subject,
            "from": sender,
            "body": body_content,
        }

        return self.router.determine_workspace(email_data)

    # ------------------------------------------------------------------ #
    # Configuration des workspaces (logging only)
    # ------------------------------------------------------------------ #
    def apply_workspace_configuration(self) -> None:
        """
        Logs the workspace configuration.
        Note: Configuration is now managed locally via prompts files.
        """
        logger.info("⚙️ Configuration des Workspaces (log uniquement)...")

        ws_prompts = self.config.workspace_prompts
        ws_settings = self.config.workspace_settings
        local_slugs = set(ws_prompts.keys()) | set(ws_settings.keys())

        for slug in sorted(local_slugs):
            prompt = ws_prompts.get(slug)
            settings = ws_settings.get(slug, {})
            temp = settings.get("temperature", self.config.default_llm_temperature)
            logger.info(
                "✅ Workspace '%s' : temp=%s, prompt=%s",
                slug,
                temp,
                "custom" if prompt else "default",
            )

        logger.info("✅ Configuration des Workspaces terminée.")
