import os
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, Optional, Set


class Config:
    """
    Configuration centrale de l'application Mail2RAG.

    Toutes les variables d'environnement utiles sont lues ici, et
    quelques valeurs dérivées (URLs normalisées, chemins, etc.) sont
    calculées une seule fois.
    """

    def __init__(self) -> None:
        # ------------------------------------------------------------------
        # LOGGING
        # ------------------------------------------------------------------
        self.log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_level = getattr(logging, self.log_level_str, logging.INFO)

        # Taille max des logs + nombre de fichiers de backup (rotation)
        self.log_max_bytes = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
        self.log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))

        # ------------------------------------------------------------------
        # EMAIL (IMAP / SMTP)
        # ------------------------------------------------------------------
        self.imap_server = os.getenv("IMAP_SERVER")
        self.imap_port = int(os.getenv("IMAP_PORT", "993"))
        self.imap_user = os.getenv("IMAP_USER")
        self.imap_password = os.getenv("IMAP_PASSWORD")

        # Dossier + critères de recherche IMAP
        self.imap_folder = os.getenv("IMAP_FOLDER", "INBOX")
        # Utilisé surtout lors de la première synchro (last_uid <= 0)
        self.imap_search_criteria = os.getenv("IMAP_SEARCH_CRITERIA", "UNSEEN")

        # Intervalle de polling IMAP (IMAP_POLL_INTERVAL prioritaire)
        self.poll_interval = int(
            os.getenv("IMAP_POLL_INTERVAL", os.getenv("POLL_INTERVAL", "60"))
        )

        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        # Adresse d'expéditeur affichée (fallback sur SMTP_USER)
        self.smtp_from = os.getenv("SMTP_FROM", self.smtp_user or "")

        # Timeouts IMAP/SMTP
        self.imap_timeout = int(os.getenv("IMAP_TIMEOUT", "30"))
        self.smtp_timeout = int(os.getenv("SMTP_TIMEOUT", "30"))

        # ------------------------------------------------------------------
        # VISION IA / LM STUDIO (analyse documents / images)
        # ------------------------------------------------------------------
        self.ai_api_url = os.getenv(
            "AI_API_URL",
            "http://host.docker.internal:1234/v1/chat/completions",
        )
        self.ai_api_key = os.getenv("AI_API_KEY", "lm-studio")
        self.ai_model_name = os.getenv("AI_MODEL_NAME", "qwen2-vl-7b-instruct")
        
        # Activation Vision séparée pour images et PDFs
        self.vision_enable_images = self._get_bool("VISION_ENABLE_IMAGES", True)
        self.vision_enable_pdf = self._get_bool("VISION_ENABLE_PDF", True)

        self.vision_temperature = float(os.getenv("VISION_TEMPERATURE", "0.0"))
        self.vision_max_tokens = int(os.getenv("VISION_MAX_TOKENS", "1500"))
        self.vision_timeout = int(os.getenv("VISION_TIMEOUT", "90"))
        self.vision_prompt_file = os.getenv("VISION_AI_PROMPT_FILE", "vision_ai.txt")

        # ------------------------------------------------------------------
        # TIKA (Document Text Extraction)
        # ------------------------------------------------------------------
        self.tika_server_url = os.getenv("TIKA_SERVER_URL", "http://tika:9998")
        self.tika_timeout = int(os.getenv("TIKA_TIMEOUT", "60"))
        self.tika_enable = self._get_bool("TIKA_ENABLE", True)
        self.tika_fallback_to_vision = self._get_bool("TIKA_FALLBACK_TO_VISION", True)

        # ------------------------------------------------------------------
        # LLM CHAT (génération de réponses RAG via LM Studio)
        # ------------------------------------------------------------------
        # Utilise AI_MODEL_NAME par défaut si LLM_CHAT_MODEL n'est pas défini (rétrocompatibilité)
        self.llm_chat_model = os.getenv("LLM_CHAT_MODEL", self.ai_model_name)
        self.llm_chat_timeout = int(os.getenv("LLM_CHAT_TIMEOUT", "120"))

        # ------------------------------------------------------------------
        # SYSTÈME / CHEMINS
        # ------------------------------------------------------------------
        self.save_chat_history = self._get_bool("SAVE_CHAT_HISTORY", True)
        self.sync_on_start = self._get_bool("SYNC_ON_START", True)
        self.cleanup_archive_before_sync = self._get_bool(
            "CLEANUP_ARCHIVE_BEFORE_SYNC", False
        )

        self.state_path = Path(os.getenv("STATE_PATH", "/var/lib/mail2rag/state.json"))
        self.archive_path = Path(
            os.getenv("ARCHIVE_PATH", "/var/lib/mail2rag/mail2rag_archive")
        )
        self.routing_path = Path(
            os.getenv("ROUTING_PATH", "/etc/mail2rag/routing.json")
        )

        log_path_str = os.getenv("LOG_PATH", "/var/log/mail2rag/mail2rag.log")
        self.log_path = Path(log_path_str)

        # ------------------------------------------------------------------
        # WORKERS
        # ------------------------------------------------------------------
        self.worker_count = int(os.getenv("WORKER_COUNT", "2"))
        self.worker_queue_size = int(os.getenv("WORKER_QUEUE_SIZE", "100"))

        # ------------------------------------------------------------------
        # ARCHIVE WEB
        # ------------------------------------------------------------------
        archive_base = os.getenv("ARCHIVE_BASE_URL", "http://localhost:8080")
        self.archive_base_url = archive_base.rstrip("/")

        # ------------------------------------------------------------------
        # PROMPTS
        # ------------------------------------------------------------------
        self.prompts_dir = Path(os.getenv("PROMPTS_DIR", "/etc/mail2rag/prompts"))

        # 1. Prompt système par défaut
        self.default_system_prompt: Optional[str] = None
        self._load_default_system_prompt()

        # 2. Prompts spécifiques par workspace
        self.workspace_prompts: Dict[str, str] = {}
        self._load_workspace_prompts()

        # 3. Configuration avancée par workspace
        self.workspace_settings: Dict[str, Any] = {}
        self._load_workspace_settings()

        # ------------------------------------------------------------------
        # LLM SETTINGS (général)
        # ------------------------------------------------------------------
        self.default_llm_temperature = float(
            os.getenv("DEFAULT_LLM_TEMPERATURE", "0.7")
        )
        self.default_refusal_response = os.getenv("DEFAULT_REFUSAL_RESPONSE")

        # ------------------------------------------------------------------
        # EMAIL SUMMARY
        # ------------------------------------------------------------------
        self.enable_email_summary = self._get_bool("ENABLE_EMAIL_SUMMARY", False)
        self.summary_max_sentences = int(os.getenv("SUMMARY_MAX_SENTENCES", "3"))
        self.summary_max_tokens = int(os.getenv("SUMMARY_MAX_TOKENS", "150"))

        # ------------------------------------------------------------------
        # SUPPORT QA (réécriture Q/R mails de support)
        # ------------------------------------------------------------------
        self.support_qa_prompt_file = os.getenv(
            "SUPPORT_QA_PROMPT_FILE", "support_qa_prompt.txt"
        )
        self.support_qa_temperature = float(
            os.getenv("SUPPORT_QA_TEMPERATURE", "0.1")
        )
        self.support_qa_max_tokens = int(os.getenv("SUPPORT_QA_MAX_TOKENS", "1200"))

        # ------------------------------------------------------------------
        # RAG PROXY
        # ------------------------------------------------------------------
        self.rag_proxy_url = os.getenv("RAG_PROXY_URL", "http://rag_proxy:8000")
        self.use_rag_proxy_for_search = self._get_bool(
            "USE_RAG_PROXY_FOR_SEARCH", False
        )
        self.auto_rebuild_bm25 = self._get_bool("AUTO_REBUILD_BM25", True)

        # Timeouts RAG Proxy / LLM (utilisés par les appels HTTP dans les services)
        self.rag_proxy_timeout = int(os.getenv("RAG_PROXY_TIMEOUT", "30"))
        self.llm_timeout = int(os.getenv("LLM_TIMEOUT", "60"))
        
        # ------------------------------------------------------------------
        # CHUNKING (pour RAG Proxy ingestion)
        # ------------------------------------------------------------------
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "800"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "100"))
        self.chunking_strategy = os.getenv("CHUNKING_STRATEGY", "recursive")

        # ------------------------------------------------------------------
        # LLM DIRECT (pour RAG Proxy : génération finale)
        # ------------------------------------------------------------------
        # Si LLM_BASE_URL est défini, on construit le endpoint /chat/completions.
        # Sinon, on fallback sur AI_API_URL (déjà complet).
        llm_base_url = os.getenv("LLM_BASE_URL")
        if llm_base_url:
            llm_base_url = llm_base_url.rstrip("/")
            if llm_base_url.endswith("/chat/completions"):
                self.llm_api_url = llm_base_url
            else:
                self.llm_api_url = f"{llm_base_url}/chat/completions"
        else:
            # Fallback : on réutilise AI_API_URL (déjà complet)
            self.llm_api_url = self.ai_api_url

        # ------------------------------------------------------------------
        # DEFAULTS / LIMITES
        # ------------------------------------------------------------------
        self.default_workspace = os.getenv(
            "DEFAULT_WORKSPACE", "default-workspace"
        )
        self.default_subject = os.getenv("DEFAULT_SUBJECT", "No_Subject")
        self.max_filename_length = int(os.getenv("MAX_FILENAME_LENGTH", "100"))

        # ------------------------------------------------------------------
        # LOG TRUNCATION
        # ------------------------------------------------------------------
        self.log_truncate_head = int(os.getenv("LOG_TRUNCATE_HEAD", "5"))
        self.log_truncate_tail = int(os.getenv("LOG_TRUNCATE_TAIL", "3"))
        self.log_max_line_length = int(os.getenv("LOG_MAX_LINE_LENGTH", "500"))

        # ------------------------------------------------------------------
        # SÉCURITÉ / FILTRAGE FICHIERS
        # ------------------------------------------------------------------
        allowed_str = os.getenv(
            "ALLOWED_EXTENSIONS",
            ".pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.xls,.pptx,.ppt,"
            ".html,.xml,.json,.jpg,.jpeg,.png,.bmp,.webp",
        )
        self.allowed_extensions: Set[str] = {
            ext.strip() for ext in allowed_str.split(",") if ext.strip()
        }

        blocked_str = os.getenv(
            "BLOCKED_EXTENSIONS",
            ".exe,.bin,.bat,.sh,.zip,.rar,.7z,.tar,.gz,.iso,.dll",
        )
        self.blocked_extensions: Set[str] = {
            ext.strip() for ext in blocked_str.split(",") if ext.strip()
        }

        # ------------------------------------------------------------------
        # FILE SIZE / OCR
        # ------------------------------------------------------------------
        self.min_image_size_kb = float(os.getenv("MIN_IMAGE_SIZE_KB", "5"))
        self.max_ocr_pages = int(os.getenv("MAX_OCR_PAGES", "10"))
        self.ocr_dpi = int(os.getenv("OCR_DPI", "300"))

        # ------------------------------------------------------------------
        # CRÉATION DES RÉPERTOIRES
        # ------------------------------------------------------------------
        self._ensure_directories()

    # ======================================================================
    #  HELPERS INTERNES
    # ======================================================================
    @staticmethod
    def _get_bool(env_name: str, default: bool = False) -> bool:
        return os.getenv(env_name, str(default)).strip().lower() == "true"

    def _ensure_directories(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_default_system_prompt(self) -> None:
        default_prompt_path = self.prompts_dir / "system_default.txt"
        if default_prompt_path.exists():
            try:
                self.default_system_prompt = (
                    default_prompt_path.read_text(encoding="utf-8").strip()
                )
                logging.info(
                    "Chargé prompt système par défaut depuis %s",
                    default_prompt_path,
                )
            except Exception as e:
                logging.error("Erreur lecture prompt par défaut: %s", e)

    def _load_workspace_prompts(self) -> None:
        workspaces_prompts_dir = self.prompts_dir / "workspaces"
        if not workspaces_prompts_dir.exists():
            return

        for prompt_file in workspaces_prompts_dir.glob("*.txt"):
            try:
                slug = prompt_file.stem
                content = prompt_file.read_text(encoding="utf-8").strip()
                if content:
                    self.workspace_prompts[slug] = content
                    logging.info(
                        "Chargé prompt spécifique pour workspace '%s'", slug
                    )
            except Exception as e:
                logging.error(
                    "Erreur lecture prompt workspace %s: %s", prompt_file, e
                )

    def _load_workspace_settings(self) -> None:
        workspaces_cfg_path = self.prompts_dir / "workspaces_config.json"
        if not workspaces_cfg_path.exists():
            logging.info(
                "Aucune configuration avancée par workspace trouvée (%s absent).",
                workspaces_cfg_path,
            )
            return

        try:
            with open(workspaces_cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.workspace_settings = data
                logging.info(
                    "Chargée configuration avancée pour %d workspace(s) "
                    "depuis %s",
                    len(self.workspace_settings),
                    workspaces_cfg_path,
                )
            else:
                logging.error(
                    "workspaces_config.json doit contenir un objet JSON (dict), trouvé: %s",
                    type(data),
                )
        except Exception as e:
            logging.error("Erreur lecture workspaces_config.json: %s", e)

    # ======================================================================
    #  LOGGING
    # ======================================================================
    def setup_logging(self) -> logging.Logger:
        file_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=self.log_max_bytes,
            backupCount=self.log_backup_count,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        logging.basicConfig(
            level=self.log_level,
            handlers=[file_handler, stream_handler],
        )

        # Limiter le bruit de certaines libs
        logging.getLogger("urllib3").setLevel(logging.INFO)
        logging.getLogger("PIL").setLevel(logging.INFO)
        logging.getLogger("multipart").setLevel(logging.INFO)
        logging.getLogger("imapclient").setLevel(logging.INFO)
        logging.getLogger("imaplib").setLevel(logging.INFO)

        # Respecter le LOG_LEVEL pour les modules internes principaux
        logging.getLogger("services.mail").setLevel(self.log_level)
        logging.getLogger("services.processor").setLevel(self.log_level)
        logging.getLogger("services.router").setLevel(self.log_level)
        logging.getLogger("services.cleaner").setLevel(self.log_level)
        logging.getLogger("services.ingestion_service").setLevel(self.log_level)
        logging.getLogger("services.chat_service").setLevel(self.log_level)
        logging.getLogger("services.support_qa").setLevel(self.log_level)
        logging.getLogger("services.email_parser").setLevel(self.log_level)

        logger = logging.getLogger("Mail2RAG")
        logger.info("Système de log initialisé au niveau : %s", self.log_level_str)
        return logger

    # ======================================================================
    #  PROMPTS HELPERS
    # ======================================================================
    def load_prompt(self, prompt_file: str) -> Optional[str]:
        """
        Charge un prompt depuis un fichier relatif à PROMPTS_DIR.

        Args:
            prompt_file: Nom du fichier de prompt

        Returns:
            str ou None
        """
        try:
            prompt_path = self.prompts_dir / prompt_file
            if prompt_path.exists():
                content = prompt_path.read_text(encoding="utf-8").strip()
                logging.info("Loaded prompt from: %s", prompt_path)
                return content
            logging.warning("Prompt file not found: %s", prompt_path)
            return None
        except Exception as e:
            logging.error("Error loading prompt %s: %s", prompt_file, e)
            return None
