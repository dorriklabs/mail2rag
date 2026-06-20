# app/scoring.py
from typing import Dict, Optional
from .config import RAG_FILTER_WEIGHTS

def calculate_metadata_bonus(meta: Dict, filters: Optional[Dict]) -> float:
    """Calcule le bonus/malus de score pour les correspondances de filtres."""
    bonus = 0.0
    
    # 1. Malus automatique pour les documents obsolètes
    if meta and str(meta.get("status", "")).lower() == "obsolete":
        # On applique le malus SAUF SI l'utilisateur a explicitement demandé un doc obsolète
        if not (filters and str(filters.get("status", "")).lower() == "obsolete"):
            bonus -= 0.30

    # 2. Bonus pour les filtres explicites de l'utilisateur
    if filters and meta:
        for k, v in filters.items():
            doc_v = meta.get(k)
            if doc_v is not None and str(doc_v).lower() == str(v).lower():
                bonus += RAG_FILTER_WEIGHTS.get(k, RAG_FILTER_WEIGHTS["default"])
    
    return bonus
