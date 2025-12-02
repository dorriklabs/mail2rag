"""
Service de rendu des emails pour l'application Mail2RAG.
Gère le rendu des notifications HTML via des templates Jinja2.
"""

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class EmailRenderer:
    """Génère les emails HTML à partir des templates Jinja2."""

    def __init__(self, template_dir: Path):
        """
        Initialise le moteur de templates.

        Args:
            template_dir: Répertoire contenant les fichiers de templates Jinja2.
        """
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #
    def render_ingestion_success(
        self,
        workspace: str,
        files: list,
        archive_url: str,
        email_summary: str | None = None,
    ) -> str:
        """Notification d'ingestion réussie avec résumé/aperçu de l'email."""
        template = self.env.get_template("ingestion_success.html")
        return template.render(
            workspace=workspace,
            files=files,
            archive_url=archive_url,
            email_summary=email_summary,
        )

    def render_ingestion_error(self) -> str:
        """
        Génère l'email de notification en cas d'échec d'indexation.

        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template("ingestion_error.html")
        return template.render()

    def render_ingestion_info(self, subject: str) -> str:
        """
        Génère un email informatif lorsqu'aucun document n'a été indexé.

        Args:
            subject: Sujet de l'email initial.

        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template("ingestion_info.html")
        return template.render(subject=subject)

    # ------------------------------------------------------------------ #
    # Erreurs
    # ------------------------------------------------------------------ #
    def render_crash_report(self, error_message: str) -> str:
        """
        Génère un rapport d'erreur critique.

        Args:
            error_message: Description de l'erreur à afficher.

        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template("crash_report.html")
        return template.render(error_message=error_message)

    # ------------------------------------------------------------------ #
    # Chat / Q&A
    # ------------------------------------------------------------------ #
    def render_chat_response(
        self,
        response_text: str,
        sources: list,
        archive_base_url: str,
        workspace: str | None = None,
    ) -> str:
        """
        Génère la réponse de chat avec la liste des sources utilisées.

        Args:
            response_text: Texte de la réponse de l'IA.
            sources: Liste brute des sources (AnythingLLM ou RAG Proxy).
            archive_base_url: URL de base utilisée pour construire les liens d'archive.
            workspace: (optionnel) slug du workspace utilisé pour ce chat.

        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template("chat_response.html")

        formatted_sources = self.format_chat_sources(
            sources=sources,
            archive_base_url=archive_base_url,
        )

        return template.render(
            response_text=response_text,
            sources=formatted_sources,
            archive_url=archive_base_url,
            workspace=workspace,
        )

    def format_chat_sources(
        self,
        sources: list,
        archive_base_url: str | None,
    ) -> list[dict]:
        """
        Formate les sources de chat pour un affichage propre dans l'email.

        Compatibilité :
        - AnythingLLM (sources venant directement de l'API /chat)
        - RAG Proxy (sources enrichies par ChatService avec scores détaillés)

        Args:
            sources: Liste brute des sources.
            archive_base_url: URL de base des archives.

        Returns:
            list: Liste de dicts avec au minimum les clés 'name' et 'link'.
                  Des champs supplémentaires sont fournis pour les templates avancés :
                  - score        : score final
                  - scores       : dict avec vector / bm25 / rerank (si dispo)
                  - snippet      : court extrait de texte
                  - raw_title    : titre brut initial
        """
        if not sources:
            return []

        base_url = (archive_base_url or "").rstrip("/")
        formatted_sources: list[dict] = []
        seen_keys: set[tuple[str, str | None]] = set()

        for src in sources:
            if not isinstance(src, dict):
                continue

            # Métadonnées & scores potentiels (RAG Proxy)
            meta = src.get("metadata") or src.get("meta") or {}
            scores_dict = src.get("scores") or {}

            # Titre brut : on essaie plusieurs champs pour rester robuste
            raw_title = (
                src.get("title")
                or src.get("name")
                or meta.get("title")
                or meta.get("file_name")
                or "Inconnu"
            )

            text = src.get("text") or meta.get("text") or ""
            score = src.get("score")

            # Scores détaillés (si fournis par le RAG Proxy / ChatService)
            vector_score = scores_dict.get("vector", meta.get("vector_score"))
            bm25_score = scores_dict.get("bm25", meta.get("bm25_score"))
            rerank_score = scores_dict.get("rerank", meta.get("rerank_score"))

            # Construction du lien (si possible)
            display_name = raw_title
            link: str | None = None

            if base_url:
                # Cas AnythingLLM classique :
                # title = "secure_id/nom_fichier.ext"
                if isinstance(raw_title, str) and "/" in raw_title:
                    rel = raw_title.lstrip("/")
                    link = f"{base_url}/{rel}"
                    display_name = Path(rel).name
                else:
                    # Cas RAG Proxy (ou données plus riches) :
                    # on essaie de reconstituer secure_id + filename si présents
                    secure_id = (
                        meta.get("secure_id")
                        or meta.get("folder_id")
                        or meta.get("archive_id")
                    )
                    filename = (
                        meta.get("filename")
                        or meta.get("file_name")
                        or meta.get("title")
                        or (raw_title if isinstance(raw_title, str) else None)
                    )

                    if secure_id and filename:
                        link = f"{base_url}/{secure_id}/{filename}"
                        display_name = str(filename)

            # Déduplication (sur combination nom + lien)
            key = (str(display_name), link)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Petit extrait de texte (optionnel)
            snippet = None
            if text:
                snippet = text.strip()
                if len(snippet) > 180:
                    snippet = snippet[:180].rstrip() + "..."

            formatted_sources.append(
                {
                    "name": str(display_name),
                    "link": link,
                    "score": score,
                    "scores": {
                        "vector": vector_score,
                        "bm25": bm25_score,
                        "rerank": rerank_score,
                    },
                    "snippet": snippet,
                    "raw_title": raw_title,
                }
            )

        logger.debug("Format_chat_sources: %d sources formatées", len(formatted_sources))
        return formatted_sources
