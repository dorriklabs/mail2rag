import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

class QualityScorer:
    """
    Évalue la qualité d'une extraction de texte (particulièrement depuis un PDF ou OCR).
    Sert à déterminer si un passage à la Vision AI est nécessaire.
    """

    @staticmethod
    def score_extraction_quality(text: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Calcule un score de qualité pour un texte extrait.
        
        Retourne un dictionnaire contenant :
        - score: float entre 0 et 1
        - is_usable: bool (score >= 0.75 ou texte significatif)
        - suspected_scan: bool
        - suspected_table: bool
        - reasons: liste de raisons ayant influencé le score
        """
        if not metadata:
            metadata = {}
            
        result = {
            "score": 0.0,
            "is_usable": False,
            "suspected_scan": False,
            "suspected_table": False,
            "reasons": []
        }
        
        if not text or not text.strip():
            result["reasons"].append("Texte vide")
            result["suspected_scan"] = True
            return result
            
        text_len = len(text)
        
        # 1. Calcul du ratio de caractères imprimables (lettres, chiffres, ponctuation courante)
        printable_chars = sum(
            1 for c in text 
            if c.isalnum() or c.isspace() or c in '.,;:!?\'"-()[]{}@#$%&*+=/<>€£¥°\n'
        )
        printable_ratio = printable_chars / text_len
        
        base_score = printable_ratio
        
        if printable_ratio < 0.85:
            result["reasons"].append(f"Ratio de caractères valides faible ({printable_ratio:.1%})")
            
        # 2. Détection de scan (texte très court mais pas vide)
        if text_len < 50:
            result["suspected_scan"] = True
            result["reasons"].append(f"Texte très court ({text_len} chars)")
            base_score *= 0.5  # Pénalité
        
        # 3. Détection de tableaux potentiels
        # Beaucoup d'espaces consécutifs, de tabulations, ou de sauts de ligne avec mots courts
        lines = text.split('\n')
        short_lines = sum(1 for line in lines if len(line.strip()) > 0 and len(line.strip()) < 15)
        if len(lines) > 5 and (short_lines / len(lines) > 0.4):
            result["suspected_table"] = True
            result["reasons"].append("Forte proportion de lignes courtes (suspicion tableau/formulaire)")
            
        # 4. Ajustement du score
        result["score"] = round(max(0.0, min(1.0, base_score)), 2)
        
        # 5. Décision
        # On considère utilisable si le score est correct, OU si c'est court mais propre (pas un tableau cassé)
        if result["score"] >= 0.80 and not result["suspected_table"]:
            result["is_usable"] = True
        elif result["score"] >= 0.90:  # Même si c'est un tableau, s'il est très propre on le garde
            result["is_usable"] = True
            
        if result["is_usable"]:
            result["reasons"].append("Qualité d'extraction jugée suffisante")
        else:
            result["reasons"].append("Qualité d'extraction insuffisante")
            
        return result
