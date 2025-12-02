import os
import logging
import json
from pathlib import Path

class Config:
    def __init__(self):
        # --- LOGGING CONFIG ---
        self.log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.log_level = getattr(logging, self.log_level_str, logging.INFO)
        
        # --- EMAIL (IMAP/SMTP) ---
        self.imap_server = os.getenv('IMAP_SERVER')
        self.imap_port = int(os.getenv('IMAP_PORT', 993))
        self.imap_user = os.getenv('IMAP_USER')
        self.imap_password = os.getenv('IMAP_PASSWORD')

        self.smtp_server = os.getenv('SMTP_SERVER')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')

        # --- ANYTHINGLLM ---
        self.anythingllm_base_url = os.getenv('ANYTHINGLLM_BASE_URL', 'http://localhost:3001')
        if not self.anythingllm_base_url.endswith('/api/v1'):
            self.anythingllm_base_url = f"{self.anythingllm_base_url}/api/v1"
        self.anythingllm_api_key = os.getenv('ANYTHINGLLM_API_KEY')

        # --- VISION IA / LM STUDIO ---
        self.ai_api_url = os.getenv('AI_API_URL', 'http://host.docker.internal:1234/v1/chat/completions')
        self.ai_api_key = os.getenv('AI_API_KEY', 'lm-studio') 
        self.ai_model_name = os.getenv('AI_MODEL_NAME', 'qwen2-vl-7b-instruct')
        self.vision_enable = os.getenv('VISION_ENABLE', 'true').lower() == 'true'

        # --- SYSTEME ---
        self.poll_interval = int(os.getenv('POLL_INTERVAL', 60))
        self.save_chat_history = os.getenv('SAVE_CHAT_HISTORY', 'false').lower() == 'true'
        self.sync_on_start = os.getenv('SYNC_ON_START', 'false').lower() == 'true'
        self.cleanup_archive_before_sync = os.getenv('CLEANUP_ARCHIVE_BEFORE_SYNC', 'false').lower() == 'true'
        self.state_path = Path(os.getenv('STATE_PATH', '/var/lib/mail2rag/state.json'))
        self.archive_path = Path(os.getenv('ARCHIVE_PATH', '/var/lib/mail2rag/mail2rag_archive'))
        self.routing_path = Path(os.getenv('ROUTING_PATH', '/etc/mail2rag/routing.json'))
        self.log_path = Path('/var/log/mail2rag/mail2rag.log')

        # --- WORKERS ---
        self.worker_count = int(os.getenv('WORKER_COUNT', '2'))
        self.worker_queue_size = int(os.getenv('WORKER_QUEUE_SIZE', '100'))

        # --- ARCHIVES WEB ---
        self.archive_base_url = os.getenv('ARCHIVE_BASE_URL', 'http://localhost:8080')
        if self.archive_base_url.endswith('/'):
            self.archive_base_url = self.archive_base_url[:-1]

        # --- PROMPTS ---
        self.prompts_dir = Path(os.getenv('PROMPTS_DIR', '/etc/mail2rag/prompts'))
        
        # 1. Prompt système par défaut
        self.default_system_prompt = None
        default_prompt_path = self.prompts_dir / 'system_default.txt'
        if default_prompt_path.exists():
            try:
                self.default_system_prompt = default_prompt_path.read_text(encoding='utf-8').strip()
                logging.info(f"Chargé prompt système par défaut depuis {default_prompt_path}")
            except Exception as e:
                logging.error(f"Erreur lecture prompt par défaut: {e}")

        # 2. Prompts spécifiques par workspace
        self.workspace_prompts = {}
        workspaces_prompts_dir = self.prompts_dir / 'workspaces'
        if workspaces_prompts_dir.exists():
            for prompt_file in workspaces_prompts_dir.glob('*.txt'):
                try:
                    slug = prompt_file.stem  # nom du fichier sans extension
                    content = prompt_file.read_text(encoding='utf-8').strip()
                    if content:
                        self.workspace_prompts[slug] = content
                        logging.info(f"Chargé prompt spécifique pour '{slug}'")
                except Exception as e:
                    logging.error(f"Erreur lecture prompt workspace {prompt_file}: {e}")
        
        # 3. Configuration avancée par workspace (température, refus, flags...)
        self.workspace_settings = {}
        workspaces_cfg_path = self.prompts_dir / 'workspaces_config.json'
        if workspaces_cfg_path.exists():
            try:
                with open(workspaces_cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.workspace_settings = data
                    logging.info(
                        f"Chargée configuration avancée pour "
                        f"{len(self.workspace_settings)} workspace(s) depuis {workspaces_cfg_path}"
                    )
                else:
                    logging.error(
                        f"workspaces_config.json doit contenir un objet JSON (dict), trouvé: {type(data)}"
                    )
            except Exception as e:
                logging.error(f"Erreur lecture workspaces_config.json: {e}")
        else:
            logging.info(f"Aucune configuration avancée par workspace trouvée ({workspaces_cfg_path} absent).")

        self.vision_prompt_file = os.getenv('VISION_AI_PROMPT_FILE', 'vision_ai.txt')

        # --- LLM SETTINGS (AnythingLLM) ---
        self.default_llm_temperature = float(os.getenv('DEFAULT_LLM_TEMPERATURE', '0.7'))
        self.default_refusal_response = os.getenv('DEFAULT_REFUSAL_RESPONSE', None)

        # --- VISION AI PARAMETERS ---
        self.vision_temperature = float(os.getenv('VISION_TEMPERATURE', '0.0'))
        self.vision_max_tokens = int(os.getenv('VISION_MAX_TOKENS', '1500'))
        self.vision_timeout = int(os.getenv('VISION_TIMEOUT', '90'))

        # --- EMAIL SUMMARY CONFIGURATION ---
        self.enable_email_summary = os.getenv('ENABLE_EMAIL_SUMMARY', 'false').lower() == 'true'
        self.summary_max_sentences = int(os.getenv('SUMMARY_MAX_SENTENCES', '3'))
        self.summary_max_tokens = int(os.getenv('SUMMARY_MAX_TOKENS', '150'))

        # --- SUPPORT QA (réécriture Q/R mails de support) ---
        self.support_qa_prompt_file = os.getenv('SUPPORT_QA_PROMPT_FILE', 'support_qa_prompt.txt')
        self.support_qa_temperature = float(os.getenv('SUPPORT_QA_TEMPERATURE', '0.1'))
        self.support_qa_max_tokens = int(os.getenv('SUPPORT_QA_MAX_TOKENS', '1200'))

        # --- RAG PROXY ---
        self.rag_proxy_url = os.getenv('RAG_PROXY_URL', 'http://rag_proxy:8000')
        self.use_rag_proxy_for_search = os.getenv('USE_RAG_PROXY_FOR_SEARCH', 'false').lower() == 'true'
        self.auto_rebuild_bm25 = os.getenv('AUTO_REBUILD_BM25', 'true').lower() == 'true'
        
        # --- LLM DIRECT (pour RAG Proxy) ---
        self.llm_api_url = os.getenv('LLM_BASE_URL', 'http://host.docker.internal:1234/v1')
        if not self.llm_api_url.endswith('/chat/completions'):
             # Si l'URL est la base (v1), on ajoute le endpoint chat
             if self.llm_api_url.endswith('/v1'):
                 self.llm_api_url = f"{self.llm_api_url}/chat/completions"
             elif self.llm_api_url.endswith('/'):
                 self.llm_api_url = f"{self.llm_api_url}chat/completions"
             else:
                 self.llm_api_url = f"{self.llm_api_url}/chat/completions"

        # --- DEFAULTS ---
        self.default_workspace = os.getenv('DEFAULT_WORKSPACE', 'default-workspace')
        self.default_subject = os.getenv('DEFAULT_SUBJECT', 'No_Subject')
        self.max_filename_length = int(os.getenv('MAX_FILENAME_LENGTH', '100'))

        # --- LOG TRUNCATION ---
        self.log_truncate_head = int(os.getenv('LOG_TRUNCATE_HEAD', '5'))
        self.log_truncate_tail = int(os.getenv('LOG_TRUNCATE_TAIL', '3'))
        self.log_max_line_length = int(os.getenv('LOG_MAX_LINE_LENGTH', '500'))

        # --- SECURITE ---
        allowed_str = os.getenv(
            'ALLOWED_EXTENSIONS', 
            '.pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.xls,.pptx,.ppt,.html,.xml,.json,.jpg,.jpeg,.png,.bmp,.webp'
        )
        self.allowed_extensions = set(ext.strip() for ext in allowed_str.split(','))
        
        blocked_str = os.getenv(
            'BLOCKED_EXTENSIONS',
            '.exe,.bin,.bat,.sh,.zip,.rar,.7z,.tar,.gz,.iso,.dll'
        )
        self.blocked_extensions = set(ext.strip() for ext in blocked_str.split(','))

        # --- API TIMEOUTS ---
        self.anythingllm_upload_timeout = int(os.getenv('ANYTHINGLLM_UPLOAD_TIMEOUT', '120'))
        self.anythingllm_chat_timeout = int(os.getenv('ANYTHINGLLM_CHAT_TIMEOUT', '60'))

        # --- FILE SIZE LIMITS ---
        self.min_image_size_kb = float(os.getenv('MIN_IMAGE_SIZE_KB', '5'))

        # --- OCR PARAMETERS ---
        self.max_ocr_pages = int(os.getenv('MAX_OCR_PAGES', '10'))
        self.ocr_dpi = int(os.getenv('OCR_DPI', '300'))

        # --- IMAP/SMTP TIMEOUTS ---
        self.imap_timeout = int(os.getenv('IMAP_TIMEOUT', '30'))
        self.smtp_timeout = int(os.getenv('SMTP_TIMEOUT', '30'))

        self._ensure_directories()

    def _ensure_directories(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def setup_logging(self):
        from logging.handlers import RotatingFileHandler
        
        file_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,              # 5 fichiers de backup
            encoding='utf-8'
        )
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        )
        
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        )
        
        logging.basicConfig(
            level=self.log_level,
            handlers=[file_handler, stream_handler]
        )
        
        # Limiter le bruit de certaines libs
        logging.getLogger("urllib3").setLevel(logging.INFO)
        logging.getLogger("PIL").setLevel(logging.INFO)
        logging.getLogger("multipart").setLevel(logging.INFO)
        logging.getLogger("imapclient").setLevel(logging.INFO)
        logging.getLogger("imaplib").setLevel(logging.INFO)
        
        # Respecter le LOG_LEVEL pour les modules internes
        logging.getLogger("services.mail").setLevel(self.log_level)
        logging.getLogger("services.processor").setLevel(self.log_level)
        logging.getLogger("services.router").setLevel(self.log_level)
        logging.getLogger("services.cleaner").setLevel(self.log_level)
        logging.getLogger("client").setLevel(self.log_level)
            
        logger = logging.getLogger("Mail2RAG")
        logger.info(f"Système de log initialisé au niveau : {self.log_level_str}")
        return logger
    
    def load_prompt(self, prompt_file):
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
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    logging.info(f"Loaded prompt from: {prompt_path}")
                    return content
            else:
                logging.warning(f"Prompt file not found: {prompt_path}")
                return None
        except Exception as e:
            logging.error(f"Error loading prompt {prompt_file}: {e}")
            return None
