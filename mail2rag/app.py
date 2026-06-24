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
from services.notification_service import NotificationService
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
from services.dispatch_service import DispatchService
from services.usage_tracker import UsageTracker
from services.feedback_service import FeedbackService
from services.sla_service import SlaService
from services.sla_report_service import SlaReportService
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


def is_sender_allowed(sender: str, allowed_domains: set) -> bool:
    """Retourne True si l'expéditeur appartient à l'un des domaines autorisés."""
    if not allowed_domains:
        return True
    if not sender:
        return False
    match = re.search(r"[\w\.-]+@([\w\.-]+)", sender)
    if not match:
        return False
    domain = match.group(1).lower()
    return domain in allowed_domains


def is_internal_sender(sender: str, imap_user: str) -> bool:
    """Retourne True si l'expéditeur appartient au même domaine que l'adresse de réception (interne)."""
    if not sender or not imap_user or '@' not in sender or '@' not in imap_user:
        return False
    try:
        sender_domain = sender.rsplit('@', 1)[1].lower()
        internal_domain = imap_user.rsplit('@', 1)[1].lower()
        return sender_domain == internal_domain
    except IndexError:
        return False


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
    parser.add_argument(
        "--analyze-feedback",
        action="store_true",
        help="Analyse les logs de feedback et met à jour les règles dynamiques.",
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
    notification_service = NotificationService(config)

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
        Obsolète : Le BM25 est maintenant natif dans Qdrant via les vecteurs sparses (SPLADE/BM25).
        Plus besoin de reconstruction manuelle.
        """
        logger.debug("Rebuild BM25 ignoré : Le BM25 est géré nativement par Qdrant en temps réel.")
        return

    from services.feedback_service import FeedbackService
    feedback_service = FeedbackService(
        state_dir=Path(config.state_path).parent,
        log_dir=Path(config.logs_path) if hasattr(config, 'logs_path') else Path("logs")
    )
    
    from services.feedback_analyzer import FeedbackAnalyzerService
    # SLA Service (Suivi des temps de réponse)
    sla_service = SlaService(
        state_dir=Path(config.state_path).parent
    )

    # Clean up old SLA records on startup
    sla_service.cleanup_old_records()

    # SLA Report Service
    sla_report_service = SlaReportService(
        config=config,
        logger_instance=logger,
        mail_service=mail_service,
        sla_service=sla_service
    )

    # 4. Initialisation des services métier
    # FeedbackAnalyzerService
    feedback_analyzer = FeedbackAnalyzerService(
        config=config,
        state_dir=config.state_path,
        log_dir=config.logs_path if hasattr(config, 'logs_path') else Path("logs"),
        support_qa_service=support_qa,
    )

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
        feedback_service=feedback_service,
        sla_service=sla_service,
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
        notification_service=notification_service,
    )

    # Dispatch Sémantique
    dispatch_service = DispatchService(
        config=config,
        logger_instance=logger,
        mail_service=mail_service,
        cleaner=cleaner,
        router=router,
        notification_service=notification_service,
        support_draft_service=support_draft_service,
        feedback_service=feedback_service,
        sla_service=sla_service
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
        "dispatch_service": dispatch_service,
        "usage_tracker": usage_tracker,
        "feedback_analyzer": feedback_analyzer,
        "notification_service": notification_service,
        "feedback_service": feedback_service,
        "sla_service": sla_service,
        "sla_report_service": sla_report_service
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

    if getattr(args, "analyze_feedback", False):
        did_something = True
        logger.info("Début de l'analyse des feedbacks (--analyze-feedback)")
        context["feedback_analyzer"].process_new_feedbacks()

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
        # Check for remote cron trigger
        trigger_file = Path(config.state_path).parent / "trigger_analyze.json"
        if trigger_file.exists():
            try:
                logger.info("⏳ Déclencheur cron détecté : exécution de l'analyse des feedbacks...")
                context["feedback_analyzer"].process_new_feedbacks()
                trigger_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error("❌ Erreur lors de l'analyse des feedbacks déclenchée par cron : %s", e)

        # Check for remote SLA report trigger
        sla_trigger_file = Path(config.state_path).parent / "trigger_sla_report.json"
        if sla_trigger_file.exists():
            try:
                logger.info("⏳ Déclencheur cron détecté : exécution du Rapport SLA...")
                context["sla_report_service"].send_report_to_admin(trigger_type="Cron Hebdo")
                sla_trigger_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error("❌ Erreur lors de l'envoi du Rapport SLA déclenché par cron : %s", e)

        # Reload routing config if changed
        router: RouterService = context["router"]
        router.reload_if_changed()

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

        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        state_lock = threading.Lock()

        def process_single_email(uid, msg_data):
            try:
                parsed_email = email_parser.parse(uid, msg_data)
            except Exception as e:
                logger.error("[UID %s] Erreur lors du parsing de l'email : %s", uid, e, exc_info=True)
                return uid

            router: RouterService = context["router"]
            support_draft_service: SupportDraftService = context.get("support_draft_service")
            dispatch_service: DispatchService = context.get("dispatch_service")

            if not is_sender_allowed(parsed_email.sender, config.allowed_domains):
                logger.warning("[UID %s] Bloqué: Expéditeur '%s' non autorisé par ALLOWED_DOMAINS. Email ignoré.", uid, parsed_email.sender)
                return uid

            # Flow SLA Report (Pull manuel)
            lower_subject = parsed_email.subject.lower()
            if lower_subject.startswith("sla:") or lower_subject.startswith("rapport sla"):
                if parsed_email.sender == config.admin_email:
                    logger.info("[UID %s] Demande manuelle de rapport SLA de la part de %s", uid, parsed_email.sender)
                    context["sla_report_service"].send_report_to_admin(trigger_type="Demande Manuelle")
                else:
                    logger.warning("[UID %s] Demande SLA refusée (Expéditeur non autorisé : %s)", uid, parsed_email.sender)
                mail_service.move_message(uid, config.imap_folder_archive)
                return uid

            try:
                if is_diagnostic_email(parsed_email.subject):
                    diagnostic_service.run_diagnostic(parsed_email)
                elif is_chat_email(parsed_email.subject):
                    chat_service.handle_chat(parsed_email)
                elif router.semantic_dispatch_enabled and dispatch_service.handle_dispatch(parsed_email):
                    logger.info("[UID %s] Email classé par le Dispatch IA. Fin du traitement.", uid)
                    pass
                elif support_draft_service and is_support_draft_mode(parsed_email, router, config):
                    support_draft_service.handle_support_request(parsed_email)
                else:
                    if is_internal_sender(parsed_email.sender, config.imap_user):
                        ingestion_service.ingest_email(parsed_email)
                    else:
                        logger.info("[UID %s] Email non routable d'un expéditeur externe (%s) ignoré pour l'ingestion.", uid, parsed_email.sender)
            except Exception as e:
                logger.error("[UID %s] Erreur non gérée lors du traitement : %s", uid, e, exc_info=True)

            return uid

        # Exécution concurrente avec ThreadPoolExecutor
        uids_to_process = sorted(messages.keys())
        logger.info("Traitement concurrent de %d e-mail(s) via ThreadPoolExecutor...", len(uids_to_process))
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(process_single_email, uid, messages[uid]): uid for uid in uids_to_process}
            
            for future in as_completed(futures):
                completed_uid = future.result()
                with state_lock:
                    last_uid = max(last_uid, completed_uid)
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
