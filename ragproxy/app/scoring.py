# app/scoring.py
from typing import Dict, Optional

def calculate_metadata_bonus(meta: Dict, filters: Optional[Dict]) -> float:
    """Calcule le bonus de score pour les correspondances de filtres 'probables'."""
    bonus = 0.0
    if filters and meta:
        for k, v in filters.items():
            doc_v = meta.get(k)
            if doc_v is not None and str(doc_v).lower() == str(v).lower():
                bonus += 0.10
    return bonus
