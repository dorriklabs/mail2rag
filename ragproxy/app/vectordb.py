# include/vectordb.py

import logging
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any, Any

from qdrant_client import QdrantClient
from qdrant_client import models

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
#  INTERFACE ABSTRAITE (Le "HAL" / Contrat)
# -----------------------------------------------------------------------------
class VectorDBProvider(ABC):
    """Interface générique pour toutes les bases de données vectorielles."""
    
    @abstractmethod
    def search(self, query_text: str, query_vector: List[float], limit: int, collection_name: Optional[str] = None, metadata_filter: Optional[Dict] = None, acl_groups: Optional[List[str]] = None) -> List[Dict]:
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
        """
        pass

    @abstractmethod
    def search_by_metadata(
        self,
        collection_name: str,
        metadata_filter: Dict,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Recherche des points par filtre exact de métadonnées/payload.
        """
        pass

    @abstractmethod
    def document_exists(
        self,
        collection_name: str,
        metadata_filter: Dict,
        content_hash: Optional[str] = None,
        limit: int = 10000,
    ) -> Dict:
        """
        Vérifie l'existence d'un document à partir de métadonnées exactes.
        """
        pass

    @abstractmethod
    def check_semantic_cache(self, query_vector: List[float], threshold: float = 0.95) -> Optional[Dict]:
        """Cherche une réponse mise en cache pour une requête sémantiquement similaire."""
        pass

    @abstractmethod
    def add_to_semantic_cache(self, query_text: str, query_vector: List[float], answer: str, sources: List[Dict]) -> bool:
        """Sauvegarde une réponse générée dans le cache sémantique."""
        pass

    @abstractmethod
    def clear_semantic_cache(self) -> bool:
        """Vide entièrement le cache sémantique."""
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

    def search(self, query_text: str, query_vector: List[float], limit: int, collection_name: Optional[str] = None, metadata_filter: Optional[Dict] = None, acl_groups: Optional[List[str]] = None) -> List[Dict]:
        target_collection = collection_name or self.collection_name
        try:
            # Générer le sparse vector
            sparse_result = list(self.sparse_model.embed([query_text]))[0]
            sparse_vector = models.SparseVector(
                indices=sparse_result.indices.tolist(),
                values=sparse_result.values.tolist(),
            )
            
            # Construire le filtre strict si fourni
            filter_obj = self._build_metadata_filter(metadata_filter, acl_groups=acl_groups)
            
            # Recherche hybride avec RRF
            hits = self.client.query_points(
                collection_name=target_collection,
                prefetch=[
                    models.Prefetch(
                        query=sparse_vector,
                        using="sparse",
                        limit=limit * 2,
                        filter=filter_obj,
                    ),
                    models.Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=limit * 2,
                        filter=filter_obj,
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


    def _build_metadata_filter(self, metadata_filter: Dict, acl_groups: Optional[List[str]] = None) -> Optional[models.Filter]:
        """
        Construit un filtre Qdrant exact sur payload/métadonnées et ACL.


        Exemple :
            {"document_key": "...", "content_hash": "..."}
        """
        conditions = []

        for key, value in (metadata_filter or {}).items():
            if key is None:
                continue

            key = str(key).strip()
            if not key:
                continue

            if value is None:
                continue

            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
            )

        if acl_groups:
            conditions.append(
                models.FieldCondition(
                    key="acl",
                    match=models.MatchAny(any=acl_groups),
                )
            )

        if not conditions:
            return None

        return models.Filter(must=conditions)

    def search_by_metadata(
        self,
        collection_name: str,
        metadata_filter: Dict,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Recherche directe par métadonnées/payload Qdrant.
        """
        try:
            if limit <= 0:
                limit = 100

            collections = self.client.get_collections().collections
            if not any(col.name == collection_name for col in collections):
                logger.info(f"Collection '{collection_name}' not found for metadata search")
                return []

            filter_obj = self._build_metadata_filter(metadata_filter)
            if filter_obj is None:
                logger.warning("Empty metadata filter, aborting metadata search")
                return []

            results = []
            offset = None

            while len(results) < limit:
                batch_limit = min(limit - len(results), 1000)

                points, next_offset = self.client.scroll(
                    collection_name=collection_name,
                    scroll_filter=filter_obj,
                    limit=batch_limit,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                for point in points:
                    payload = point.payload or {}
                    results.append(
                        {
                            "point_id": str(point.id),
                            "text": payload.get("text", ""),
                            "metadata": payload,
                            "payload": payload,
                        }
                    )

                if not next_offset or not points:
                    break

                offset = next_offset

            logger.debug(
                f"Metadata search in '{collection_name}' returned {len(results)} point(s)"
            )
            return results

        except Exception as e:
            logger.error(
                f"Failed metadata search in '{collection_name}': {e}",
                exc_info=True,
            )
            return []

    def document_exists(
        self,
        collection_name: str,
        metadata_filter: Dict,
        content_hash: Optional[str] = None,
        limit: int = 10000,
    ) -> Dict:
        """
        Vérifie si un document existe à partir d'un filtre exact.

        Si content_hash est fourni :
        - exists indique si des chunks existent ;
        - same_hash indique si les chunks trouvés portent le même hash.
        """
        matches = self.search_by_metadata(
            collection_name=collection_name,
            metadata_filter=metadata_filter,
            limit=limit,
        )

        exists = len(matches) > 0
        same_hash = None

        if content_hash is not None:
            if not matches:
                same_hash = False
            else:
                hashes = {
                    (m.get("metadata") or {}).get("content_hash")
                    for m in matches
                    if (m.get("metadata") or {}).get("content_hash") is not None
                }

                if not hashes:
                    same_hash = None
                else:
                    same_hash = hashes == {content_hash}

        return {
            "exists": exists,
            "same_hash": same_hash,
            "chunks_count": len(matches),
            "matches": matches,
        }

    def check_semantic_cache(self, query_vector: List[float], threshold: float = 0.95) -> Optional[Dict]:
        """Recherche dans le cache Qdrant s'il existe une question très similaire."""
        collection_name = "mail2rag_cache"
        try:
            # Vérifier si la collection cache existe
            if not any(col.name == collection_name for col in self.client.get_collections().collections):
                return None
                
            hits = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=1,
            ).points
            
            if hits and hits[0].score >= threshold:
                logger.info(f"⚡ Semantic Cache HIT! (score: {hits[0].score:.4f})")
                return hits[0].payload
                
            return None
        except Exception as e:
            logger.error(f"Semantic cache search failed: {e}")
            return None

    def add_to_semantic_cache(self, query_text: str, query_vector: List[float], answer: str, sources: List[Dict]) -> bool:
        """Ajoute une question/réponse au cache."""
        import uuid
        collection_name = "mail2rag_cache"
        
        try:
            # Vérifier/Créer la collection si elle n'existe pas
            if not any(col.name == collection_name for col in self.client.get_collections().collections):
                vector_dim = len(query_vector)
                logger.info(f"Creating semantic cache collection '{collection_name}' with dense dimension {vector_dim}")
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(size=vector_dim, distance=models.Distance.COSINE),
                )
            
            point_id = str(uuid.uuid4())
            payload = {
                "query": query_text,
                "answer": answer,
                "sources": sources,
            }
            
            point = models.PointStruct(
                id=point_id,
                vector=query_vector,
                payload=payload,
            )
            
            self.client.upsert(
                collection_name=collection_name,
                points=[point],
            )
            
            logger.info("Saved response to semantic cache.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add to semantic cache: {e}")
            return False

    def clear_semantic_cache(self) -> bool:
        collection_name = "mail2rag_cache"
        try:
            if any(col.name == collection_name for col in self.client.get_collections().collections):
                self.client.delete_collection(collection_name=collection_name)
                logger.info(f"Deleted semantic cache collection '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to clear semantic cache: {e}")
            return False


# -----------------------------------------------------------------------------
#  FACTORY / SERVICE (Le point d'entrée unique)
# -----------------------------------------------------------------------------
class VectorDBService:
    def __init__(self, host: str, port: int, collection_name: str):
        self.provider: VectorDBProvider = QdrantProvider(host, port, collection_name)
        self.collection_name = collection_name

    def search(self, query_text: str, query_vector: List[float], limit: int, collection_name: Optional[str] = None, metadata_filter: Optional[Dict] = None, acl_groups: Optional[List[str]] = None) -> List[Dict]:
        return self.provider.search(query_text, query_vector, limit, collection_name, metadata_filter, acl_groups)

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

    def search_by_metadata(
        self,
        collection_name: str,
        metadata_filter: Dict,
        limit: int = 100,
    ) -> List[Dict]:
        return self.provider.search_by_metadata(collection_name, metadata_filter, limit)

    def document_exists(
        self,
        collection_name: str,
        metadata_filter: Dict,
        content_hash: Optional[str] = None,
        limit: int = 10000,
    ) -> Dict:
        return self.provider.document_exists(collection_name, metadata_filter, content_hash, limit)

    def check_semantic_cache(self, query_vector: List[float], threshold: float = 0.95) -> Optional[Dict]:
        return self.provider.check_semantic_cache(query_vector, threshold)
        
    def add_to_semantic_cache(self, query_text: str, query_vector: List[float], answer: str, sources: List[Dict]) -> bool:
        return self.provider.add_to_semantic_cache(query_text, query_vector, answer, sources)

    def clear_semantic_cache(self) -> bool:
        return self.provider.clear_semantic_cache()
