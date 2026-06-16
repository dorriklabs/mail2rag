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
        self.semantic_dispatch_enabled = False
        self.semantic_dispatch_mapping = {}
        self._last_mtime = 0.0
        self.reload_if_changed()

    # ------------------------------------------------------------------ #
    #  CHARGEMENT DES RÈGLES
    # ------------------------------------------------------------------ #
    def reload_if_changed(self) -> None:
        """Vérifie si routing.json a été modifié et le recharge si nécessaire."""
        try:
            if not self.routing_file.exists():
                return
            current_mtime = self.routing_file.stat().st_mtime
            if current_mtime > self._last_mtime:
                self._load_rules()
                self._last_mtime = current_mtime
        except Exception as e:
            logger.error("Erreur lors de la vérification de routing.json : %s", e)

    def _load_rules(self) -> None:
        """Charge les règles de routage depuis le fichier JSON."""
        self.rules = []
        self.semantic_dispatch_mapping = {}
        self.semantic_dispatch_enabled = False
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
            
            # Semantic Dispatch
            sd_config = data.get("semantic_dispatch", {})
            self.semantic_dispatch_enabled = sd_config.get("enabled", False)
            self.semantic_dispatch_mapping = sd_config.get("mapping", {})

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
            
        if text == "*":
            return "*"

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
    def determine_workspace(self, email_data: Dict[str, Any], return_rejected: bool = False, is_chat: bool = False) -> str | tuple[str, List[str]]:
        """
        Détermine le workspace cible pour un email donné.

        L'algorithme avec ACL :
        1. Appliquer les règles définies dans routing.json pour trouver le workspace par défaut et les allowed_workspaces.
        2. Chercher une mention explicite dans le corps (Workspace:/Dossier:)
        3. Valider la permission si ENFORCE_STRICT_ROUTING=true.

        Le résultat est toujours renvoyé sous forme de slug (ou slugs séparés par virgules).
        """
        body = (email_data.get("body") or "").strip()
        subject = (email_data.get("subject") or "").strip()
        sender = (email_data.get("from") or "").strip()

        logger.debug("Routage pour Sender='%s', Subject='%s'", sender, subject)

        sender_l = sender.lower()
        subject_l = subject.lower()
        body_l = body.lower()
        sender_domain = self._extract_sender_domain(sender)

        # ------------------------------------------------------------------
        # 1. Règles automatiques (Détermination du contexte utilisateur)
        # ------------------------------------------------------------------
        default_ws = self.config.default_workspace
        allowed_ws = []
        matched_rule = None

        if self.rules:
            for rule in self.rules:
                workspace = (rule.get("workspace") or "").strip()
                if not workspace:
                    continue

                try:
                    if self._match_rule(
                        rule, sender, subject, body, sender_l, subject_l, body_l, sender_domain
                    ):
                        default_ws = workspace
                        # Extraire les ACLs s'ils existent
                        allowed_ws = rule.get("allowed_workspaces", [])
                        if not isinstance(allowed_ws, list):
                            allowed_ws = [str(allowed_ws)]
                        matched_rule = rule
                        logger.debug(
                            "-> Règle appliquée (%s='%s') -> par défaut: %s, allowed: %s",
                            rule.get("type"), rule.get("value"), default_ws, allowed_ws
                        )
                        break
                except Exception as e:
                    logger.error("Erreur lors de l'application de la règle %s : %s", rule, e)
                    continue

        target_ws = default_ws

        # ------------------------------------------------------------------
        # 2. Mention explicite dans le corps
        # ------------------------------------------------------------------
        requested_ws = None
        for line in body.splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue

            match = re.match(r"^(?:Dossier|Workspace|Collection)\s*:\s*(.+)", clean_line, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if candidate:
                    requested_ws = candidate
                    break

        # ------------------------------------------------------------------
        # 3. Validation ACL (Strict Routing) et Multi-Workspace
        # ------------------------------------------------------------------
        if not requested_ws and is_chat:
            requested_ws = "*"
            logger.debug("-> Mode Chat sans workspace: recherche globale autorisée par défaut.")

        rejected_workspaces = []
        target_ws_list = [default_ws]
        
        if requested_ws:
            requested_list = [w.strip() for w in requested_ws.split(",") if w.strip()]
            requested_slugs = [self._slugify(w) for w in requested_list]
            
            default_slug = self._slugify(default_ws)
            allowed_slugs = [self._slugify(w) for w in allowed_ws]

            if not getattr(self.config, "enforce_strict_routing", False):
                # Mode permissif : on accepte tout et on gère l'étoile
                target_ws_list = []
                for req_slug, req_raw in zip(requested_slugs, requested_list):
                    if req_raw == "*":
                        if "*" in allowed_ws:
                            target_ws_list.append("*")
                        else:
                            target_ws_list.append(default_slug)
                            target_ws_list.extend([w for w in allowed_slugs if w != "*"])
                    else:
                        target_ws_list.append(req_slug)
                        
                target_ws_list = list(dict.fromkeys(target_ws_list)) # deduplicate
                logger.debug("-> Routage explicite (Mode permissif) : '%s'", target_ws_list)
            else:
                # Mode strict : on vérifie chaque workspace demandé
                valid_slugs = []
                for req_slug, req_raw in zip(requested_slugs, requested_list):
                    if req_raw == "*":
                        if "*" in allowed_ws:
                            valid_slugs.append("*")
                        else:
                            # S'il demande * mais n'a pas l'ACL suprême, on lui donne tous ses accès spécifiques
                            valid_slugs.append(default_slug)
                            valid_slugs.extend([w for w in allowed_slugs if w != "*"])
                    elif (req_slug == default_slug) or (req_slug in allowed_slugs) or ("*" in allowed_ws):
                        valid_slugs.append(req_slug)
                    else:
                        rejected_workspaces.append(req_raw)
                        logger.warning(
                            "⚠️ Accès refusé au workspace '%s' pour '%s'.",
                            req_raw, sender
                        )
                
                if valid_slugs:
                    target_ws_list = list(dict.fromkeys(valid_slugs)) # deduplicate
                    logger.debug("-> Routage explicite (Mode strict) AUTORISÉ : '%s'", target_ws_list)
                else:
                    logger.warning("Aucun workspace autorisé. Redirection vers '%s'.", default_ws)
                    target_ws_list = [default_slug]
        else:
            target_ws_list = [self._slugify(default_ws)]

        # ------------------------------------------------------------------
        # 4. Slugification finale
        # ------------------------------------------------------------------
        # Les éléments dans target_ws_list sont déjà slugifiés
        final_slug = ",".join(target_ws_list)
        logger.debug("-> Résultat final du routage : '%s'", final_slug)

        if return_rejected:
            return final_slug, rejected_workspaces
        return final_slug
