# include/vectordb.py

import logging
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple

from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
#  INTERFACE ABSTRAITE (Le "HAL" / Contrat)
# -----------------------------------------------------------------------------
class VectorDBProvider(ABC):
    """Interface générique pour toutes les bases de données vectorielles."""
    
    @abstractmethod
    def search(self, query_vector: List[float], limit: int, collection_name: str = None) -> List[Dict]:
        """Recherche les vecteurs les plus proches."""
        pass

    @abstractmethod
    def get_all_documents(self) -> List[Dict]:
        """
        Récupère TOUS les documents (texte + métadonnées) pour construire l'index BM25.
        Doit retourner une liste de dicts avec au moins les clés 'text' et 'metadata'.
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Vérifie si la base de données est accessible."""
        pass
    
    @abstractmethod
    def count_documents(self) -> int:
        """Retourne le nombre total de documents dans la collection."""
        pass
    
    @abstractmethod
    def list_collections(self) -> List[str]:
        """Retourne la liste de toutes les collections disponibles."""
        pass


# -----------------------------------------------------------------------------
#  ADAPTATEUR QDRANT (Le "Driver")
# -----------------------------------------------------------------------------
class QdrantProvider(VectorDBProvider):
    def __init__(self, host: str, port: int, collection_name: str):
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        logger.info(f"Initialized QdrantProvider on {host}:{port} (collection: {collection_name})")

    def search(self, query_vector: List[float], limit: int, collection_name: str = None) -> List[Dict]:
        target_collection = collection_name or self.collection_name
        try:
            hits = self.client.query_points(
                collection_name=target_collection,
                query=query_vector,
                limit=limit,
            ).points
        except Exception as e:
            logger.error(f"Qdrant search failed on '{target_collection}': {e}")
            return []

        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                {
                    "text": payload.get("text", ""),
                    "metadata": payload,
                    "score": float(hit.score),
                }
            )
        return results

    def get_all_documents(self) -> List[Dict]:
        try:
            # Scroll pour récupérer tous les points (limité à 10000 pour l'instant)
            # TODO: Implémenter une pagination réelle si > 10000 docs
            points, _ = self.client.scroll(
                collection_name=self.collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )
            
            docs = []
            for point in points:
                payload = point.payload or {}
                docs.append({
                    "text": payload.get("text", ""),
                    "metadata": payload
                })
            return docs
            
        except Exception as e:
            # Gestion spécifique des erreurs Qdrant pour aider l'utilisateur
            error_msg = str(e)
            if "Not found: Collection" in error_msg or "doesn't exist" in error_msg:
                logger.warning(f"Collection {self.collection_name} not found in Qdrant.")
                # On propage l'erreur pour que l'appelant puisse afficher le bon message d'aide
                raise e 
            else:
                logger.error(f"Failed to fetch all documents from Qdrant: {e}")
                raise e

    def is_ready(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.warning(f"Qdrant readiness check failed: {e}")
            return False

    def count_documents(self) -> int:
        try:
            count_result = self.client.count(collection_name=self.collection_name)
            return count_result.count
        except Exception:
            return 0
    
    def list_collections(self) -> List[str]:
        """Retourne la liste de toutes les collections Qdrant."""
        try:
            collections = self.client.get_collections()
            return [col.name for col in collections.collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []


# -----------------------------------------------------------------------------
#  FACTORY / SERVICE (Le point d'entrée unique)
# -----------------------------------------------------------------------------
class VectorDBService:
    def __init__(self, host: str, port: int, collection_name: str):
        # Ici on pourrait lire os.getenv('VECTOR_DB_PROVIDER') pour choisir dynamiquement
        # Pour l'instant on hardcode Qdrant, mais l'architecture est prête.
        self.provider: VectorDBProvider = QdrantProvider(host, port, collection_name)
        self.collection_name = collection_name

    def search(self, query_vector: List[float], limit: int, collection_name: str = None) -> List[Dict]:
        return self.provider.search(query_vector, limit, collection_name)

    def is_ready(self) -> bool:
        return self.provider.is_ready()
    
    def get_all_documents(self) -> List[Dict]:
        return self.provider.get_all_documents()
    
    def count_documents(self) -> int:
        return self.provider.count_documents()
    
    def list_collections(self) -> List[str]:
        return self.provider.list_collections()
