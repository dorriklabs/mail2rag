# app/local_reranker.py

import logging
from typing import List, Dict

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class LocalReranker:
    """
    Service de reranking local utilisant un modèle Cross-Encoder.
    Alternative au RerankerService (LM Studio) qui ne supporte pas /v1/rerank.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialise le cross-encoder pour le reranking.
        
        Args:
            model_name: Nom du modèle HuggingFace à utiliser.
                        Par défaut: cross-encoder/ms-marco-MiniLM-L-6-v2 (rapide et efficace)
                        Alternative: cross-encoder/ms-marco-MiniLM-L-12-v2 (plus précis mais plus lent)
        """
        self.model_name = model_name
        logger.info(f"Chargement du modèle de reranking local: {model_name}...")
        
        try:
            self.model = CrossEncoder(model_name, max_length=512)
            logger.info(f"✅ Modèle de reranking local chargé: {model_name}")
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement du modèle de reranking: {e}")
            raise

    def rerank(self, query: str, passages: List[Dict]) -> List[Dict]:
        """
        Reranke une liste de passages en fonction de leur pertinence par rapport à la query.
        
        Args:
            query: La requête utilisateur
            passages: Liste de dictionnaires contenant les passages (avec clé 'text')
        
        Returns:
            Liste des passages triés par pertinence décroissante avec scores mis à jour
        """
        if not passages:
            logger.warning("Aucun passage à reranker")
            return []

        try:
            # Préparer les paires (query, passage)
            pairs = [(query, p.get("text", "")) for p in passages]
            
            # Calculer les scores de pertinence
            scores = self.model.predict(pairs)
            
            # Enrichir les passages avec les nouveaux scores
            enriched = []
            for passage, score in zip(passages, scores):
                new_p = dict(passage)
                meta = dict(new_p.get("metadata") or {})
                
                # Stocker le score de rerank dans les métadonnées
                meta["rerank_score"] = float(score)
                new_p["metadata"] = meta
                
                # Mettre à jour le score principal
                new_p["score"] = float(score)
                enriched.append(new_p)
            
            # Trier par score décroissant
            ranked = sorted(
                enriched,
                key=lambda x: float(x.get("score", 0.0)),
                reverse=True,
            )
            
            logger.debug(
                f"Reranking terminé: {len(ranked)} passages, "
                f"scores: [{ranked[0]['score']:.3f} ... {ranked[-1]['score']:.3f}]"
            )
            
            return ranked
            
        except Exception as e:
            logger.error(f"Erreur lors du reranking local: {e}", exc_info=True)
            # En cas d'erreur, retourner les passages dans leur ordre original
            return passages
