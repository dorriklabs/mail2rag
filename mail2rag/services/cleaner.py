import re
import logging

logger = logging.getLogger(__name__)


class CleanerService:
    def __init__(self, config):
        self.config = config

        # Regex pré-compilées pour la performance

        # Signatures courantes (FR/EN)
        self.regex_signatures = re.compile(
            r'(?i)(\n--\s*\n|'          # séparateur "--"
            r'\n\s*cordialement[,. ]|'  # "Cordialement"
            r'\n\s*bien à vous[,. ]|'   # "Bien à vous"
            r'\n\s*best regards[,. ]|'  # "Best regards"
            r'\n\s*kind regards[,. ]|'  # "Kind regards"
            r'\n\s*regards[,. ])'
            r'.*',                      # tout ce qui suit
            re.DOTALL
        )

        # Disclaimers FR/EN fréquents
        self.regex_disclaimers = re.compile(
            r'(?i)('
            r'ce message (et toutes les pièces jointes )?est confidentiel|'
            r'ce courriel (et toutes ses pièces jointes )?est confidentiel|'
            r'this (e-?mail|email) and any (files?|attachments?) transmitted with it are confidential|'
            r'this message (and any attachment)? is intended solely for the addressee|'
            r'think before you print|'
            r'please consider the environment before printing this email'
            r')'
            r'.*',
            re.DOTALL
        )

        # Footer "envoyé depuis"
        self.regex_mobile_footers = re.compile(
            r'(?i)envoy[ée] depuis mon (iphone|android|ipad|mobile)',
            re.MULTILINE
        )

        # Réponses / historiques (on ne s'en sert plus directement pour sub(),
        # mais on garde quelques patterns réutilisés)
        # On va utiliser une approche "find earliest marker + tronquer"
        self.reply_header_patterns = [
            # FR
            r'^\s*Le .+ a écrit :\s*$',
            r'^\s*Le .+ écrivait :\s*$',
            r'^\s*De : .+\s*$',
            r'^\s*Message d\'origine\s*:?\s*$',
            r'^\s*-----Message d\'origine-----\s*$',
            # EN
            r'^\s*On .+ wrote:\s*$',
            r'^\s*From: .+\s*$',
            r'^\s*-----Original Message-----\s*$',
            # DE / autres
            r'^\s*Am .+ schrieb .+:\s*$',
            r'^\s*Von: .+\s*$',
        ]

    # -------------------------------------------------------------------------
    # Nettoyage du corps du mail
    # -------------------------------------------------------------------------
    def _strip_reply_history(self, text: str) -> str:
        """
        Coupe l'historique de réponse à partir du premier "header" de réponse.
        On cherche la première ligne correspondant à un des patterns classiques :
          - "Le ... a écrit :"
          - "On ... wrote:"
          - "-----Original Message-----"
          - "De : ..."
          - "From: ..."
        et on tronque le texte à cet endroit.
        """
        if not text:
            return ""

        # On parcourt une seule fois le texte ligne par ligne, et on détecte
        # la première ligne qui matche un des patterns.
        lines = text.splitlines(keepends=True)
        cutoff_index = None

        # Compile tous les patterns une fois
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.reply_header_patterns]

        for idx, line in enumerate(lines):
            for pattern in compiled_patterns:
                if pattern.search(line):
                    cutoff_index = idx
                    break
            if cutoff_index is not None:
                break

        if cutoff_index is not None:
            logger.debug(
                f"Historique de réponse détecté à la ligne {cutoff_index}, "
                f"tronquage du corps à cet endroit."
            )
            return "".join(lines[:cutoff_index])

        return text

    def _remove_quoted_lines(self, text: str) -> str:
        """
        Supprime les lignes citées typiques qui commencent par '>'.
        Cela permet d'éviter de réindexer tout l'historique de conversation.
        """
        if not text:
            return ""

        cleaned_lines = []
        for line in text.splitlines():
            # On ignore les lignes strictement citées ("> ..." ou " > ...")
            if re.match(r'^\s*>', line):
                continue
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def clean_body(self, text: str) -> str:
        """Nettoie le corps du mail (reply chain, signatures, disclaimers, quotes)."""
        if not text:
            return ""
        
        # Normalisation des retours à la ligne
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        original_len = len(text)

        # 1. Couper l'historique (Reply) via détection de headers
        text = self._strip_reply_history(text)

        # 2. Retirer les signatures (Cordialement, Best regards, etc.)
        text = self.regex_signatures.sub("", text)

        # 3. Retirer les disclaimers verbeux (confidentialité, environnement, etc.)
        text = self.regex_disclaimers.sub("", text)

        # 4. Nettoyage des footers mobiles (envoyé depuis mon iPhone / Android ...)
        text = self.regex_mobile_footers.sub("", text)

        # 5. Supprimer les lignes citées (commençant par ">")
        text = self._remove_quoted_lines(text)

        # 6. Trim et réduction des multiples lignes vides
        #    (on évite que le texte final soit une bouillie de blancs)
        # Supprimer les espaces en début/fin global
        text = text.strip()

        # Réduire les séquences de plus de 2 lignes vides successives en max 2
        lines = text.splitlines()
        cleaned_lines = []
        empty_run = 0
        for line in lines:
            if line.strip() == "":
                empty_run += 1
                if empty_run <= 2:
                    cleaned_lines.append("")
            else:
                empty_run = 0
                cleaned_lines.append(line)
        text = "\n".join(cleaned_lines).strip()

        logger.debug(f"Nettoyage Body: {original_len} -> {len(text)} chars conservés")
        return text

    # -------------------------------------------------------------------------
    # Validation des pièces jointes
    # -------------------------------------------------------------------------
    def is_valid_attachment(self, filename: str, content: bytes) -> bool:
        """
        Valide une pièce jointe (Taille min, Extensions autorisées / interdites).
        - Filtre les logos trop petits
        - Bloque les extensions explicitement interdites
        - N'autorise que les extensions listées dans ALLOWED_EXTENSIONS (si défini)
        """
        # Récupérer l'extension sans le point
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        size_kb = len(content) / 1024

        # Règle 1 : Ignorer les images minuscules (Logos, Icônes)
        # On considère qu'une image < MIN_IMAGE_SIZE_KB est probablement un logo de signature
        if ext in ['png', 'jpg', 'jpeg', 'gif'] and size_kb < self.config.min_image_size_kb:
            logger.debug(
                f"PJ ignorée (Trop petite/Logo): {filename} "
                f"({size_kb:.1f} Ko, seuil: {self.config.min_image_size_kb} Ko)"
            )
            return False

        # Construire la forme ".ext" pour comparer avec les sets de config
        ext_with_dot = f".{ext}" if ext else ""

        # Règle 2 : Extensions interdites (sécurité)
        if ext_with_dot in self.config.blocked_extensions:
            logger.warning(f"PJ bloquée (Extension interdite): {filename}")
            return False

        # Règle 3 : Extensions autorisées (whitelist)
        # Si ALLOWED_EXTENSIONS est défini, on n'autorise que ce qui est dedans
        if self.config.allowed_extensions:
            if ext_with_dot not in self.config.allowed_extensions:
                logger.debug(
                    f"PJ ignorée (Extension non autorisée): {filename} "
                    f"(ext: '{ext_with_dot}', allowed: {self.config.allowed_extensions})"
                )
                return False

        # Si on arrive ici, la PJ est considérée comme valide
        return True
