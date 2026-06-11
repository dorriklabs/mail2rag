# include/vectordb.py

import logging
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional

from qdrant_client import QdrantClient
from qdrant_client import models

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
#  INTERFACE ABSTRAITE (Le "HAL" / Contrat)
# -----------------------------------------------------------------------------
class VectorDBProvider(ABC):
    """Interface générique pour toutes les bases de données vectorielles."""
    
    @abstractmethod
    def search(self, query_text: str, query_vector: List[float], limit: int, collection_name: Optional[str] = None) -> List[Dict]:
        """Recherche les vecteurs les plus proches en mode Hybride (Dense + Sparse)."""
        pass

    @abstractmethod
    def get_all_documents(self) -> List[Dict]:
        """
        Récupère TOUS les documents (texte + métadonnées).
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
    
    @abstractmethod
    def upsert_documents(
        self,
        chunks: List[Dict],
        collection_name: str,
    ) -> bool:
        """
        Indexe des chunks avec embeddings dans la collection.
        
        Args:
            chunks: Liste de dicts avec clés 'text', 'metadata', 'embedding'
            collection_name: Nom de la collection cible
            
        Returns:
            True si succès, False sinon
        """
        pass
    
    @abstractmethod
    def delete_by_metadata(
        self,
        collection_name: str,
        metadata_filter: Dict,
    ) -> int:
        """
        Supprime les documents matchant un filtre de métadonnées.
        
        Args:
            collection_name: Nom de la collection
            metadata_filter: Filtre de métadonnées (ex: {"uid": "12345"})
            
        Returns:
            Nombre de documents supprimés
        """
        pass


# -----------------------------------------------------------------------------
#  ADAPTATEUR QDRANT (Le "Driver")
# -----------------------------------------------------------------------------
class QdrantProvider(VectorDBProvider):
    def __init__(self, host: str, port: int, collection_name: str):
        from fastembed import SparseTextEmbedding
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        logger.info(f"Initialized QdrantProvider on {host}:{port} (collection: {collection_name})")

    def search(self, query_text: str, query_vector: List[float], limit: int, collection_name: Optional[str] = None) -> List[Dict]:
        target_collection = collection_name or self.collection_name
        try:
            # Générer le sparse vector
            sparse_result = list(self.sparse_model.embed([query_text]))[0]
            sparse_vector = models.SparseVector(
                indices=sparse_result.indices.tolist(),
                values=sparse_result.values.tolist(),
            )
            
            # Recherche hybride avec RRF
            hits = self.client.query_points(
                collection_name=target_collection,
                prefetch=[
                    models.Prefetch(
                        query=sparse_vector,
                        using="sparse",
                        limit=limit * 2,
                    ),
                    models.Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=limit * 2,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
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
            error_msg = str(e)
            if "Not found: Collection" in error_msg or "doesn't exist" in error_msg:
                logger.warning(f"Collection {self.collection_name} not found in Qdrant.")
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
        try:
            collections = self.client.get_collections()
            return [col.name for col in collections.collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    def collection_exists(self) -> bool:
        try:
            collections = self.client.get_collections().collections
            return any(col.name == self.collection_name for col in collections)
        except Exception as e:
            logger.error(f"Failed to check if collection exists: {e}")
            return False
    
    def delete_collection(self) -> bool:
        try:
            self.client.delete_collection(collection_name=self.collection_name)
            logger.info(f"Deleted Qdrant collection '{self.collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection '{self.collection_name}': {e}")
            return False
    
    def upsert_documents(
        self,
        chunks: List[Dict],
        collection_name: str,
    ) -> bool:
        import uuid
        
        try:
            collections = self.client.get_collections().collections
            collection_exists = any(col.name == collection_name for col in collections)
            
            if not collection_exists:
                if not chunks or "embedding" not in chunks[0]:
                    logger.error("No chunks or missing embedding in first chunk")
                    return False
                
                vector_dim = len(chunks[0]["embedding"])
                
                logger.info(f"Creating new hybrid collection '{collection_name}' with dense dimension {vector_dim}")
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": models.VectorParams(size=vector_dim, distance=models.Distance.COSINE),
                    },
                    sparse_vectors_config={
                        "sparse": models.SparseVectorParams(),
                    }
                )
            
            # Générer les sparse vectors pour tous les chunks
            texts = [chunk.get("text", "") for chunk in chunks]
            sparse_embeddings = list(self.sparse_model.embed(texts))
            
            points = []
            for i, chunk in enumerate(chunks):
                if "embedding" not in chunk or not chunk.get("text"):
                    logger.warning("Chunk missing embedding or text, skipping")
                    continue
                
                point_id = str(uuid.uuid4())
                payload = {
                    "text": chunk["text"],
                    **chunk.get("metadata", {})
                }
                
                sparse_res = sparse_embeddings[i]
                
                point = models.PointStruct(
                    id=point_id,
                    vector={
                        "dense": chunk["embedding"],
                        "sparse": models.SparseVector(
                            indices=sparse_res.indices.tolist(),
                            values=sparse_res.values.tolist(),
                        )
                    },
                    payload=payload,
                )
                points.append(point)
            
            if not points:
                logger.warning("No valid points to upsert")
                return False
            
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self.client.upsert(
                    collection_name=collection_name,
                    points=batch,
                )
            
            logger.info(f"Successfully upserted {len(points)} hybrid points to '{collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert hybrid documents to '{collection_name}': {e}")
            return False
    
    def delete_by_metadata(
        self,
        collection_name: str,
        metadata_filter: Dict,
    ) -> int:
        try:
            conditions = []
            for key, value in metadata_filter.items():
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value)
                    )
                )
            
            if not conditions:
                logger.warning("Empty metadata filter, aborting deletion")
                return 0
            
            filter_obj = models.Filter(must=conditions)
            
            scroll_result = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=filter_obj,
                limit=10000,
                with_payload=False,
                with_vectors=False,
            )
            
            points_to_delete = [point.id for point in scroll_result[0]]
            
            if not points_to_delete:
                logger.info(f"No documents matching filter in '{collection_name}'")
                return 0
            
            self.client.delete(
                collection_name=collection_name,
                points_selector=models.PointIdsList(points=points_to_delete),
            )
            
            logger.info(f"Deleted {len(points_to_delete)} documents from '{collection_name}'")
            return len(points_to_delete)
            
        except Exception as e:
            logger.error(f"Failed to delete by metadata in '{collection_name}': {e}")
            return 0


# -----------------------------------------------------------------------------
#  FACTORY / SERVICE (Le point d'entrée unique)
# -----------------------------------------------------------------------------
class VectorDBService:
    def __init__(self, host: str, port: int, collection_name: str):
        self.provider: VectorDBProvider = QdrantProvider(host, port, collection_name)
        self.collection_name = collection_name

    def search(self, query_text: str, query_vector: List[float], limit: int, collection_name: Optional[str] = None) -> List[Dict]:
        return self.provider.search(query_text, query_vector, limit, collection_name)

    def is_ready(self) -> bool:
        return self.provider.is_ready()
    
    def get_all_documents(self) -> List[Dict]:
        return self.provider.get_all_documents()
    
    def count_documents(self) -> int:
        return self.provider.count_documents()
    
    def list_collections(self) -> List[str]:
        return self.provider.list_collections()
    
    def upsert_documents(self, chunks: List[Dict], collection_name: str) -> bool:
        return self.provider.upsert_documents(chunks, collection_name)
    
    def delete_by_metadata(self, collection_name: str, metadata_filter: Dict) -> int:
        return self.provider.delete_by_metadata(collection_name, metadata_filter)
