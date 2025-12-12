import argparse
import logging
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any

import requests

from version import __version__ as APP_VERSION
from config import Config
from services.email_parser import EmailParser
from services.mail import MailService
from services.cleaner import CleanerService
from services.router import RouterService
from services.processor import DocumentProcessor
from services.email_renderer import EmailRenderer
from services.support_qa import SupportQAService
from services.ingestion_service import IngestionService
from services.chat_service import ChatService
from services.maintenance import MaintenanceService
from services.state_manager import StateManager
from services.diagnostic import DiagnosticService
from services.tika_client import TikaClient
from services.ragproxy_client import RAGProxyClient
from services.draft_service import DraftService
from services.support_draft_service import SupportDraftService
from services.usage_tracker import UsageTracker
from models import ParsedEmail


# ---------------------------------------------------------------------------
# Détection des modes (CHAT / DIAGNOSTIC)
# ---------------------------------------------------------------------------
CHAT_SUBJECT_RE = re.compile(r"(?i)^\s*(chat|question)\s*:")
DIAG_SUBJECT_RE = re.compile(r"(?i)^\s*(test\s*:\s*all|test\s*:\s*diag)")


def is_chat_email(subject: str | None) -> bool:
    """Retourne True si le sujet correspond au mode CHAT (Chat: / Question:)."""
    return bool(CHAT_SUBJECT_RE.match((subject or "").strip()))


def is_diagnostic_email(subject: str | None) -> bool:
    """Retourne True si le sujet correspond au mode DIAGNOSTIC (test : all / test:diag)."""
    return bool(DIAG_SUBJECT_RE.match((subject or "").strip()))


def is_support_draft_mode(
    email: "ParsedEmail",
    router: "RouterService",
    config: "Config",
) -> bool:
    """
    Détermine si le mode Support Draft s'applique.
    
    Conditions:
    1. Le workspace a support_draft: true dans workspaces_config.json
    2. L'email N'est PAS envoyé par la boîte support elle-même (évite boucle BCC)
    
    Args:
        email: Email parsé
        router: Service de routage
        config: Configuration
        
    Returns:
        True si le mode Support Draft doit être activé
    """
    workspace = router.determine_workspace(email.email_data)
    ws_cfg = config.workspace_settings.get(workspace, {})
    
    if not ws_cfg.get("support_draft", False):
        return False
    
    # Éviter de traiter nos propres réponses comme des demandes
    support_email = (config.imap_user or "").lower()
    sender = (email.sender or "").lower()
    
    return sender != support_email


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mail2RAG3 worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Traite les messages disponibles puis s'arrête.",
    )
    parser.add_argument(
        "--sync-archive",
        action="store_true",
        help="Ré-ingère l'archive locale via RAG Proxy puis s'arrête.",
    )
    parser.add_argument(
        "--apply-workspace-config",
        action="store_true",
        help="Applique les prompts et paramètres LLM aux workspaces distants.",
    )
    parser.add_argument(
        "--cleanup-archive",
        action="store_true",
        help="Supprime tout le contenu de l'archive locale puis s'arrête.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Construction du contexte (services + état)
# ---------------------------------------------------------------------------
def build_context(config: Config, logger: logging.Logger) -> Dict[str, Any]:
    """
    Instancie tous les services et charge l'état applicatif.

    Retourne un dict 'context' passé ensuite à la boucle principale.
    """
    mail_service = MailService(config)
    cleaner = CleanerService(config)
    router = RouterService(config)
    processor = DocumentProcessor(config)

    template_dir = Path(__file__).parent / "templates"
    email_renderer = EmailRenderer(template_dir)

    support_qa = SupportQAService(config)

    state_manager = StateManager(config.state_path, logger)
    state = state_manager.load_state()
    # Sécurise la structure minimale de l'état
    state.setdefault("last_uid", 0)
    state.setdefault("secure_ids", {})

    maintenance = MaintenanceService(config, router, mail_service)

    def get_secure_id(uid: int) -> str:
        """Retourne un ID opaque et stable pour le dossier d'archive de cet UID."""
        return state_manager.get_or_create_secure_id(state, uid)

    def trigger_bm25_rebuild(workspace: str = None) -> None:
        """
        Déclenche la reconstruction de l'index BM25 via le RAG Proxy, si activé.
        Si workspace est fourni, reconstruit uniquement pour ce workspace.
        Sinon, tente une reconstruction globale ou intelligente.
        """
        if not config.auto_rebuild_bm25:
            logger.debug("AUTO_REBUILD_BM25 désactivé, aucun rebuild BM25 lancé.")
            return

        base = config.rag_proxy_url.rstrip("/")
        
        if workspace:
            # Endpoint spécifique au workspace
            candidates = [f"/admin/build-bm25/{workspace}"]
        else:
            # Endpoints globaux
            candidates = ["/admin/auto-rebuild-bm25", "/admin/rebuild-all-bm25"]

        for path in candidates:
            url = f"{base}{path}"
            try:
                logger.info("Déclenchement rebuild BM25 via %s ...", url)
                resp = requests.post(url, timeout=config.rag_proxy_timeout)
                if resp.ok:
                    logger.info("✅ Rebuild BM25 déclenché avec succès via %s", url)
                    return
                logger.warning(
                    "Endpoint %s a répondu %s : %s",
                    url,
                    resp.status_code,
                    resp.text[:300],
                )
            except Exception as e:
                logger.warning(
                    "Erreur lors de l'appel rebuild BM25 (%s): %s", url, e
                )

        logger.error("Impossible de déclencher le rebuild BM25 sur les endpoints connus.")

    ingestion_service = IngestionService(
        config=config,
        logger=logger,
        mail_service=mail_service,
        router=router,
        processor=processor,
        cleaner=cleaner,
        support_qa_service=support_qa,
        email_renderer=email_renderer,
        get_secure_id=get_secure_id,
        trigger_bm25_rebuild=trigger_bm25_rebuild,
    )

    chat_service = ChatService(
        config=config,
        logger=logger,
        mail_service=mail_service,
        router=router,
        cleaner=cleaner,
        email_renderer=email_renderer,
        get_secure_id=get_secure_id,
    )

    email_parser = EmailParser(logger)

    # Service de diagnostic (test : all)
    tika_client = TikaClient(config.tika_server_url, timeout=config.tika_timeout)
    ragproxy_client = RAGProxyClient(config.rag_proxy_url, timeout=config.rag_proxy_timeout)
    
    diagnostic_service = DiagnosticService(
        config=config,
        logger=logger,
        mail_service=mail_service,
        ragproxy_client=ragproxy_client,
        processor=processor,
        email_renderer=email_renderer,
        tika_client=tika_client,
        get_secure_id=get_secure_id,
    )

    # Services Support Draft Mode (SaaS-ready)
    usage_tracker = UsageTracker(config, logger)
    draft_service = DraftService(config, logger, mail_service)
    support_draft_service = SupportDraftService(
        config=config,
        logger_instance=logger,
        mail_service=mail_service,
        draft_service=draft_service,
        router=router,
        cleaner=cleaner,
        email_renderer=email_renderer,
        usage_tracker=usage_tracker,
    )

    return {
        "config": config,
        "logger": logger,
        "state_manager": state_manager,
        "state": state,
        "mail_service": mail_service,
        "email_parser": email_parser,
        "ingestion_service": ingestion_service,
        "chat_service": chat_service,
        "diagnostic_service": diagnostic_service,
        "maintenance": maintenance,
        "router": router,
        "support_draft_service": support_draft_service,
        "usage_tracker": usage_tracker,
    }


# ---------------------------------------------------------------------------
# Maintenance (actions CLI)
# ---------------------------------------------------------------------------
def handle_maintenance_actions(
    context: Dict[str, Any],
    args: argparse.Namespace,
) -> bool:
    """
    Exécute les actions de maintenance demandées sur la ligne de commande.

    Retourne True si au moins une action a été exécutée (et donc que
    le programme doit s'arrêter ensuite).
    """
    maintenance: MaintenanceService = context["maintenance"]
    logger: logging.Logger = context["logger"]

    did_something = False

    if args.cleanup_archive:
        did_something = True
        maintenance.cleanup_archive()

    if args.sync_archive:
        did_something = True
        maintenance.sync_all()

    if args.apply_workspace_config:
        did_something = True
        maintenance.apply_workspace_configuration()

    if did_something:
        logger.info("Opérations de maintenance terminées, arrêt du processus.")

    return did_something


# ---------------------------------------------------------------------------
# Boucle principale de polling IMAP
# ---------------------------------------------------------------------------
def run_poller(context: Dict[str, Any], once: bool = False) -> None:
    """
    Boucle principale de polling IMAP.

    - Récupère les nouveaux messages > last_uid
    - Parse chaque email
    - Route vers ingestion normale ou mode chat
    - Met à jour l'état (last_uid, secure_ids)
    """
    config: Config = context["config"]
    logger: logging.Logger = context["logger"]
    state_manager: StateManager = context["state_manager"]
    state: Dict[str, Any] = context["state"]

    mail_service: MailService = context["mail_service"]
    email_parser: EmailParser = context["email_parser"]
    ingestion_service: IngestionService = context["ingestion_service"]
    chat_service: ChatService = context["chat_service"]
    diagnostic_service: DiagnosticService = context["diagnostic_service"]

    last_uid = int(state.get("last_uid", 0))
    logger.info("Dernier UID connu au démarrage : %s", last_uid)

    while True:
        try:
            messages = mail_service.fetch_new_messages(last_uid)
        except Exception as e:
            logger.error("Erreur lors du fetch IMAP : %s", e, exc_info=True)
            if once:
                break
            time.sleep(config.poll_interval)
            continue

        if not messages:
            logger.debug("Aucun nouveau message. Pause %ss.", config.poll_interval)
            if once:
                break
            time.sleep(config.poll_interval)
            continue

        for uid in sorted(messages.keys()):
            msg_data = messages[uid]

            try:
                parsed_email = email_parser.parse(uid, msg_data)
            except Exception as e:
                logger.error(
                    "Erreur lors du parsing de l'email UID %s : %s",
                    uid,
                    e,
                    exc_info=True,
                )
                # On avance malgré tout pour ne pas rester bloqué
                last_uid = max(last_uid, uid)
                state["last_uid"] = last_uid
                state_manager.save_state(state)
                continue

            # Services additionnels du context
            router: RouterService = context["router"]
            support_draft_service: SupportDraftService = context.get("support_draft_service")

            try:
                if is_diagnostic_email(parsed_email.subject):
                    # Mode diagnostic : test : all
                    diagnostic_service.run_diagnostic(parsed_email)
                elif is_chat_email(parsed_email.subject):
                    # Mode Chat : Chat: / Question:
                    chat_service.handle_chat(parsed_email)
                elif support_draft_service and is_support_draft_mode(parsed_email, router, config):
                    # Mode Support Draft : génère un brouillon
                    support_draft_service.handle_support_request(parsed_email)
                else:
                    # Mode Ingestion standard
                    ingestion_service.ingest_email(parsed_email)
            except Exception as e:
                # Les services internes gèrent déjà la plupart des exceptions
                logger.error(
                    "Erreur non gérée lors du traitement UID %s : %s",
                    uid,
                    e,
                    exc_info=True,
                )

            # Mise à jour de l'UID après traitement
            last_uid = max(last_uid, uid)
            state["last_uid"] = last_uid
            state_manager.save_state(state)

        if once:
            logger.info("Mode --once actif : boucle terminée après ce cycle.")
            break

        time.sleep(config.poll_interval)


# ---------------------------------------------------------------------------
# Entrée principale
# ---------------------------------------------------------------------------
def main() -> None:
    config = Config()
    logger = config.setup_logging()

    args = parse_args()

    logger.info("Mail2RAG démarré - version %s", APP_VERSION)

    context = build_context(config, logger)

    # Exécution des actions de maintenance si demandées
    if handle_maintenance_actions(context, args):
        return

    # Maintenance automatique au démarrage (optionnelle)
    maintenance: MaintenanceService = context["maintenance"]
    if config.cleanup_archive_before_sync:
        maintenance.cleanup_archive()
    if config.sync_on_start:
        maintenance.sync_all()
        maintenance.apply_workspace_configuration()

    # Boucle principale de polling
    try:
        run_poller(context, once=args.once)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé (Ctrl+C).")
    except Exception as e:
        logger.error("Erreur critique dans la boucle principale : %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
