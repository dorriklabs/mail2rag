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
from services.state_manager import StateManager
from services.mail import MailService
from services.cleaner import CleanerService
from services.router import RouterService
from services.processor import DocumentProcessor
from services.email_renderer import EmailRenderer
from services.support_qa import SupportQAService
from services.anythingllm_client import AnythingLLMClient
from services.chat_service import ChatService
from services.ingestion_service import IngestionService
from services.maintenance import MaintenanceService


# ---------------------------------------------------------------------------
# Détection des emails "CHAT" (mode Q/R)
# ---------------------------------------------------------------------------
CHAT_SUBJECT_RE = re.compile(r"(?i)^\s*(chat|question)\s*:")


def is_chat_email(subject: str | None) -> bool:
    """Retourne True si le sujet correspond au mode CHAT (Chat: / Question:)."""
    return bool(CHAT_SUBJECT_RE.match((subject or "").strip()))


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
        help="Ré-ingère l'archive locale dans AnythingLLM puis s'arrête.",
    )
    parser.add_argument(
        "--sync-from-anythingllm",
        action="store_true",
        help="Crée des emails synthétiques pour les documents orphelins d'AnythingLLM.",
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
    client = AnythingLLMClient(config)
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

    maintenance = MaintenanceService(config, client, router, mail_service)

    def get_secure_id(uid: int) -> str:
        """Retourne un ID opaque et stable pour le dossier d'archive de cet UID."""
        return state_manager.get_or_create_secure_id(state, uid)

    def trigger_bm25_rebuild() -> None:
        """
        Déclenche la reconstruction de l'index BM25 via le RAG Proxy, si activé.
        Tente quelques endpoints possibles et logge en détail sans interrompre l'ingestion.
        """
        if not config.auto_rebuild_bm25:
            logger.debug("AUTO_REBUILD_BM25 désactivé, aucun rebuild BM25 lancé.")
            return

        base = config.rag_proxy_url.rstrip("/")
        candidates = ["/admin/auto-rebuild-bm25"]

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
        client=client,
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
        client=client,
        mail_service=mail_service,
        router=router,
        cleaner=cleaner,
        email_renderer=email_renderer,
        get_secure_id=get_secure_id,
    )

    email_parser = EmailParser(logger)

    return {
        "config": config,
        "logger": logger,
        "state_manager": state_manager,
        "state": state,
        "mail_service": mail_service,
        "email_parser": email_parser,
        "ingestion_service": ingestion_service,
        "chat_service": chat_service,
        "maintenance": maintenance,
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

    if args.sync_from_anythingllm:
        did_something = True
        maintenance.sync_from_anythingllm()

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

            try:
                if is_chat_email(parsed_email.subject):
                    chat_service.handle_chat(parsed_email)
                else:
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
