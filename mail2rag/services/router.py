import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RouterService:
    """
    Service de routage des emails vers les collections RAG.

    Sources possibles pour déterminer le workspace :
    1. Mention explicite dans le corps : "Workspace: xxx" ou "Dossier: yyy"
    2. Règles de routage définies dans routing.json
    3. Workspace par défaut défini dans la configuration
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.routing_file = config.routing_path
        self.rules: List[Dict[str, Any]] = []
        self._load_rules()

    # ------------------------------------------------------------------ #
    #  CHARGEMENT DES RÈGLES
    # ------------------------------------------------------------------ #
    def _load_rules(self) -> None:
        """Charge les règles de routage depuis le fichier JSON."""
        self.rules = []
        try:
            if not self.routing_file.exists():
                logger.warning("Fichier de routage %s absent.", self.routing_file)
                return

            with self.routing_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            rules = data.get("rules", [])
            if not isinstance(rules, list):
                logger.error(
                    "Format de routage invalide (champ 'rules' non liste) dans %s",
                    self.routing_file,
                )
                return

            self.rules = rules
            logger.info("Chargé %d règle(s) de routage.", len(self.rules))

        except Exception as e:
            logger.error("Erreur lecture routage (%s) : %s", self.routing_file, e)
            self.rules = []

    # ------------------------------------------------------------------ #
    #  UTILITAIRES
    # ------------------------------------------------------------------ #
    def _slugify(self, text: str) -> str:
        """
        Transforme une chaîne arbitraire en slug ASCII strict.
        Exemple : 'Projet : Été 2024' -> 'projet-ete-2024'
        """
        if not text:
            return self.config.default_workspace

        # 1. Minuscules + trim
        text = text.lower().strip()

        # 2. Suppression des accents (Normalisation NFD)
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")

        # 3. Ne garder que [a-z0-9], espaces et tirets
        text = re.sub(r"[^a-z0-9\s-]", "", text)

        # 4. Remplacer espaces / séparateurs par tirets
        text = re.sub(r"[\s_-]+", "-", text)

        # 5. Retirer tirets début/fin
        text = text.strip("-")

        return text or self.config.default_workspace

    @staticmethod
    def _extract_sender_domain(sender: str) -> str:
        """
        Extrait le domaine de l'expéditeur (partie après @).
        Exemple: 'Boss <boss@example.com>' -> 'example.com'
        """
        if not sender:
            return ""
        match = re.search(r"[\w\.-]+@([\w\.-]+)", sender)
        if not match:
            return ""
        return match.group(1).lower()

    def _match_rule(
        self,
        rule: Dict[str, Any],
        sender: str,
        subject: str,
        body: str,
        sender_l: str,
        subject_l: str,
        body_l: str,
        sender_domain: str,
    ) -> bool:
        """
        Applique une règle de routage.

        Types supportés (compatibles avec le JSON actuel) :

        - sender          : valeur contenue dans le champ From (insensible à la casse)
        - subject         : valeur contenue dans le sujet (insensible à la casse)

        Types avancés optionnels :

        - sender_contains : idem 'sender'
        - sender_domain   : domaine exact, ex: "client.com"
        - subject_contains: idem 'subject'
        - subject_regex   : regex appliquée sur le sujet
        - body_contains   : valeur contenue dans le corps
        - body_regex      : regex appliquée sur le corps
        """
        rtype = (rule.get("type") or "").strip()
        value = (rule.get("value") or "").strip()
        if not value or not rtype:
            return False

        val_l = value.lower()

        # Compat héritage : "sender" = contains dans le champ From
        if rtype in ("sender", "sender_contains"):
            return val_l in sender_l

        # Domaine expéditeur exact
        if rtype == "sender_domain":
            return sender_domain == val_l

        # Compat héritage : "subject" = contains dans le sujet
        if rtype in ("subject", "subject_contains"):
            return val_l in subject_l

        # Regex sur le sujet
        if rtype == "subject_regex":
            try:
                return re.search(value, subject, re.IGNORECASE) is not None
            except re.error as e:
                logger.warning(
                    "Regex invalide dans règle subject_regex '%s' : %s", value, e
                )
                return False

        # Recherche simple dans le corps
        if rtype == "body_contains":
            return val_l in body_l

        # Regex sur le corps
        if rtype == "body_regex":
            try:
                return re.search(value, body, re.IGNORECASE) is not None
            except re.error as e:
                logger.warning(
                    "Regex invalide dans règle body_regex '%s' : %s", value, e
                )
                return False

        # Type inconnu -> on ignore la règle
        logger.debug("Type de règle inconnu ou non géré: %s", rtype)
        return False

    # ------------------------------------------------------------------ #
    #  API PUBLIQUE
    # ------------------------------------------------------------------ #
    def determine_workspace(self, email_data: Dict[str, Any]) -> str:
        """
        Détermine le workspace cible pour un email donné.

        L'algorithme est :
        1. Chercher une mention explicite dans le corps (Workspace:/Dossier:)
        2. Sinon, appliquer les règles définies dans routing.json
        3. Sinon, utiliser DEFAULT_WORKSPACE

        Le résultat est toujours renvoyé sous forme de slug.
        """
        body = (email_data.get("body") or "").strip()
        subject = (email_data.get("subject") or "").strip()
        sender = (email_data.get("from") or "").strip()

        logger.debug("Routage pour Sender='%s', Subject='%s'", sender, subject)

        # Versions normalisées (minuscules) pour les comparaisons
        sender_l = sender.lower()
        subject_l = subject.lower()
        body_l = body.lower()
        sender_domain = self._extract_sender_domain(sender)

        # Workspace de travail (raw, non slugifié)
        raw_ws: str = self.config.default_workspace

        # ------------------------------------------------------------------
        # 1. Mention explicite dans le corps
        # ------------------------------------------------------------------
        # Exemple de ligne :
        #   Workspace: projet_x
        #   Dossier : Client Y
        for line in body.splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue

            # Regex souple (avec ou sans espace avant les deux-points)
            match = re.match(
                r"^(?:Dossier|Workspace)\s*:\s*(.+)",
                clean_line,
                re.IGNORECASE,
            )
            if match:
                raw_ws_candidate = match.group(1).strip()
                if raw_ws_candidate:
                    raw_ws = raw_ws_candidate
                    logger.debug("-> Routage explicite (CORPS) : '%s'", raw_ws)
                    break

        # ------------------------------------------------------------------
        # 2. Règles automatiques (si pas de workspace explicite)
        # ------------------------------------------------------------------
        if raw_ws == self.config.default_workspace and self.rules:
            for rule in self.rules:
                workspace = (rule.get("workspace") or "").strip()
                if not workspace:
                    continue

                try:
                    if self._match_rule(
                        rule,
                        sender,
                        subject,
                        body,
                        sender_l,
                        subject_l,
                        body_l,
                        sender_domain,
                    ):
                        raw_ws = workspace
                        logger.debug(
                            "-> Règle appliquée (%s='%s') -> %s",
                            rule.get("type"),
                            rule.get("value"),
                            raw_ws,
                        )
                        break
                except Exception as e:
                    logger.error(
                        "Erreur lors de l'application de la règle %s : %s",
                        rule,
                        e,
                    )
                    continue

        # ------------------------------------------------------------------
        # 3. Slugification finale
        # ------------------------------------------------------------------
        final_slug = self._slugify(raw_ws)
        if final_slug != raw_ws:
            logger.debug("-> Slugifié : '%s' -> '%s'", raw_ws, final_slug)

        return final_slug
