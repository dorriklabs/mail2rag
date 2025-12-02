import json
import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

class RouterService:
    def __init__(self, config):
        self.routing_file = config.routing_path
        self.config = config
        self.rules = []
        self._load_rules()

    def _load_rules(self):
        try:
            if self.routing_file.exists():
                with open(self.routing_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                rules = data.get('rules', [])
                if not isinstance(rules, list):
                    logger.error(f"Format de routage invalide (rules n'est pas une liste) dans {self.routing_file}")
                    self.rules = []
                else:
                    self.rules = rules
                logger.info(f"Chargé {len(self.rules)} règles de routage.")
            else:
                logger.warning(f"Fichier routage {self.routing_file} absent.")
        except Exception as e:
            logger.error(f"Erreur lecture routage : {e}")
            self.rules = []

    def _slugify(self, text):
        """Transforme 'Projet : Été 2024' en 'projet-ete-2024' (ASCII strict)."""
        if not text:
            return "default-workspace"
        
        # 1. Minuscules
        text = text.lower().strip()
        
        # 2. Suppression des accents (Normalisation NFD)
        text = unicodedata.normalize('NFD', text)
        text = "".join([c for c in text if unicodedata.category(c) != 'Mn'])
        
        # 3. Ne garder que les caractères alphanumériques (a-z, 0-9) et espaces
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        
        # 4. Remplacer espaces par tirets
        text = re.sub(r'[\s_-]+', '-', text)
        
        # 5. Retirer les tirets au début/fin
        text = text.strip('-')
        
        return text if text else "default-workspace"

    def _extract_sender_domain(self, sender: str) -> str:
        """
        Extrait le domaine de l'expéditeur (partie après @).
        Exemple: 'Boss <boss@example.com>' -> 'example.com'
        """
        if not sender:
            return ""
        # Récupérer ce qui ressemble à une adresse email
        match = re.search(r'[\w\.-]+@([\w\.-]+)', sender)
        if not match:
            return ""
        return match.group(1).lower()

    def _match_rule(self, rule, sender, subject, body, sender_l, subject_l, body_l, sender_domain):
        """
        Applique une règle de routage.
        
        Types supportés (compatibles avec ton JSON actuel) :
          - sender          : valeur contenue dans le champ From (insensible à la casse)
          - subject         : valeur contenue dans le sujet (insensible à la casse)
        
        Types avancés optionnels :
          - sender_contains : idem sender
          - sender_domain   : domaine exact, ex: "client.com"
          - subject_contains: idem subject
          - subject_regex   : regex appliquée sur le sujet
          - body_contains   : valeur contenue dans le corps
          - body_regex      : regex appliquée sur le corps
        """
        rtype = rule.get('type', '')
        value = rule.get('value', '')
        if not value or not rtype:
            return False

        val_l = value.lower()

        # Compat heritage: "sender" = contains dans le champ From
        if rtype in ('sender', 'sender_contains'):
            return val_l in sender_l

        # Domaine expéditeur : "sender_domain": "client.com"
        if rtype == 'sender_domain':
            return sender_domain == val_l

        # Compat heritage: "subject" = contains dans le sujet
        if rtype in ('subject', 'subject_contains'):
            return val_l in subject_l

        # Regex sur le sujet
        if rtype == 'subject_regex':
            try:
                return re.search(value, subject, re.IGNORECASE) is not None
            except re.error as e:
                logger.warning(f"Regex invalide dans règle subject_regex '{value}': {e}")
                return False

        # Recherche dans le corps
        if rtype == 'body_contains':
            return val_l in body_l

        # Regex sur le corps
        if rtype == 'body_regex':
            try:
                return re.search(value, body, re.IGNORECASE) is not None
            except re.error as e:
                logger.warning(f"Regex invalide dans règle body_regex '{value}': {e}")
                return False

        # Type inconnu -> on ignore la règle
        logger.debug(f"Type de règle inconnu ou non géré: {rtype}")
        return False

    def determine_workspace(self, email_data):
        body = email_data.get('body', '') or ''
        subject = email_data.get('subject', '') or ''
        sender = email_data.get('from', '') or ''
        
        logger.debug(f"Routage pour Sender='{sender}', Subject='{subject}'")
        
        # Versions normalisées (minuscules) pour les comparaisons
        sender_l = sender.lower()
        subject_l = subject.lower()
        body_l = body.lower()
        sender_domain = self._extract_sender_domain(sender)

        # Workspace par défaut
        raw_ws = self.config.default_workspace

        # 1. Mention explicite (CORPS)
        # Exemple de ligne :
        #   Workspace: projet_x
        #   Dossier : Client Y
        for line in body.split('\n'):
            clean_line = line.strip()
            if not clean_line:
                continue
            
            # Regex souple (avec ou sans espace avant les deux points)
            match = re.match(r'^(?:Dossier|Workspace)\s*:\s*(.+)', clean_line, re.IGNORECASE)
            if match:
                raw_ws = match.group(1).strip()
                logger.debug(f"-> Routage explicite (CORPS) : '{raw_ws}'")
                break

        # 2. Règles automatiques (uniquement si on n'a pas déjà un workspace explicite)
        if raw_ws == self.config.default_workspace:
            for rule in self.rules:
                workspace = rule.get('workspace')
                if not workspace:
                    continue

                try:
                    if self._match_rule(rule, sender, subject, body, sender_l, subject_l, body_l, sender_domain):
                        raw_ws = workspace
                        logger.debug(f"-> Règle appliquée ({rule.get('type')}='{rule.get('value')}') -> {raw_ws}")
                        break
                except Exception as e:
                    logger.error(f"Erreur lors de l'application de la règle {rule}: {e}")
                    continue
        
        final_slug = self._slugify(raw_ws)
        if final_slug != raw_ws:
            logger.debug(f"-> Slugifié : '{raw_ws}' -> '{final_slug}'")
            
        return final_slug
