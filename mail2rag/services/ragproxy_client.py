"""
Client HTTP pour communiquer avec RAG Proxy.

Fournit une interface de haut niveau pour l'ingestion, la suppression
et la recherche de documents via l'API RAG Proxy.
"""

import logging
from typing import Dict, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


logger = logging.getLogger(__name__)


class RAGProxyClient:
    """
    Client pour l'API RAG Proxy.
    
    Gère la communication HTTP avec stratégie de retry automatique.
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 60,
    ):
        """
        Initialise le client RAG Proxy.
        
        Args:
            base_url: URL de base du RAG Proxy (ex: http://rag_proxy:8000)
            timeout: Timeout par défaut pour les requêtes (secondes)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        
        # Session HTTP avec stratégie de retry
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        logger.debug(f"RAGProxyClient initialized for {self.base_url}")
    
    def ingest_document(
        self,
        collection: str,
        text: str,
        metadata: Dict[str, Any],
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> Dict[str, Any]:
        """
        Ingère un document dans RAG Proxy avec chunking et indexation.
        
        Args:
            collection: Nom de la collection (workspace)
            text: Contenu textuel du document
            metadata: Métadonnées (subject, sender, date, filename, uid, etc.)
            chunk_size: Taille des chunks (défaut: 800)
            chunk_overlap: Chevauchement entre chunks (défaut: 100)
            
        Returns:
            Dict avec clés: status, collection, chunks_created, message
            
        Raises:
            Exception: Si l'ingestion échoue
        """
        url = f"{self.base_url}/admin/ingest"
        
        payload = {
            "collection": collection,
            "text": text,
            "metadata": metadata,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        
        logger.info(
            f"Ingesting document to '{collection}' "
            f"(text_length={len(text)}, chunk_size={chunk_size})"
        )
        
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            
            if response.status_code != 200:
                logger.error(
                    f"Ingestion failed with status {response.status_code}: {response.text}"
                )
                return {
                    "status": "error",
                    "collection": collection,
                    "chunks_created": 0,
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
            
            result = response.json()
            
            if result.get("status") == "ok":
                logger.info(
                    f"Successfully ingested document: "
                    f"{result.get('chunks_created', 0)} chunks created"
                )
            else:
                logger.warning(
                    f"Ingestion returned non-ok status: {result.get('message')}"
                )
            
            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"Ingestion timeout after {self.timeout}s")
            return {
                "status": "error",
                "collection": collection,
                "chunks_created": 0,
                "message": f"Request timeout after {self.timeout}s",
            }
        except Exception as e:
            logger.error(f"Ingestion exception: {e}", exc_info=True)
            return {
                "status": "error",
                "collection": collection,
                "chunks_created": 0,
                "message": str(e),
            }
    
    def delete_document(
        self,
        doc_id: str,
        collection: Optional[str] = None,
    ) -> bool:
        """
        Supprime un document (tous ses chunks) par identifiant.
        
        Args:
            doc_id: Identifiant du document (uid, message_id, etc.)
            collection: Collection cible (optionnel)
            
        Returns:
            True si suppression réussie, False sinon
        """
        url = f"{self.base_url}/admin/document/{doc_id}"
        
        params = {}
        if collection:
            params["collection"] = collection
        
        logger.info(f"Deleting document '{doc_id}'" + (f" from '{collection}'" if collection else ""))
        
        try:
            response = self.session.delete(
                url,
                params=params,
                timeout=self.timeout,
            )
            
            if response.status_code != 200:
                logger.error(
                    f"Deletion failed with status {response.status_code}: {response.text}"
                )
                return False
            
            result = response.json()
            
            if result.get("status") == "ok":
                logger.info(
                    f"Successfully deleted document: "
                    f"{result.get('deleted_count', 0)} chunks removed"
                )
                return True
            else:
                logger.warning(f"Deletion returned error: {result.get('message')}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"Deletion timeout after {self.timeout}s")
            return False
        except Exception as e:
            logger.error(f"Deletion exception: {e}", exc_info=True)
            return False
    
    def search(
        self,
        query: str,
        collection: Optional[str] = None,
        top_k: int = 5,
        use_bm25: bool = True,
    ) -> Dict[str, Any]:
        """
        Recherche hybride (Vector + BM25) dans RAG Proxy.
        
        Args:
            query: Question ou recherche
            collection: Collection cible (optionnel)
            top_k: Nombre de résultats à retourner
            use_bm25: Utiliser recherche BM25 en plus de vectorielle
            
        Returns:
            Dict avec clés: query, chunks (liste), debug_info
        """
        url = f"{self.base_url}/rag"
        
        payload = {
            "query": query,
            "top_k": top_k * 2,  # Récupérer plus pour le reranking
            "final_k": top_k,
            "use_bm25": use_bm25,
        }
        
        if collection:
            payload["workspace"] = collection
        
        logger.debug(f"Search query: '{query[:50]}...' in collection '{collection}'")
        
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            
            if response.status_code != 200:
                logger.error(f"Search failed with status {response.status_code}")
                return {
                    "query": query,
                    "chunks": [],
                    "debug_info": {"error": f"HTTP {response.status_code}"},
                }
            
            result = response.json()
            logger.debug(f"Search returned {len(result.get('chunks', []))} chunks")
            
            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"Search timeout after {self.timeout}s")
            return {
                "query": query,
                "chunks": [],
                "debug_info": {"error": "Timeout"},
            }
        except Exception as e:
            logger.error(f"Search exception: {e}", exc_info=True)
            return {
                "query": query,
                "chunks": [],
                "debug_info": {"error": str(e)},
            }
    
    def rebuild_bm25(self, collection: str) -> bool:
        """
        Déclenche un rebuild de l'index BM25 pour une collection.
        
        Args:
            collection: Nom de la collection
            
        Returns:
            True si rebuild réussi, False sinon
        """
        url = f"{self.base_url}/admin/build-bm25/{collection}"
        
        logger.info(f"Rebuilding BM25 index for '{collection}'")
        
        try:
            response = self.session.post(url, timeout=self.timeout)
            
            if response.status_code != 200:
                logger.error(f"BM25 rebuild failed: {response.status_code}")
                return False
            
            result = response.json()
            
            if result.get("status") == "ok":
                logger.info(
                    f"BM25 rebuild successful: "
                    f"{result.get('docs_count', 0)} documents indexed"
                )
                return True
            else:
                logger.warning(f"BM25 rebuild error: {result.get('message')}")
                return False
                
        except Exception as e:
            logger.error(f"BM25 rebuild exception: {e}", exc_info=True)
            return False
    
    def chat(
        self,
        query: str,
        collection: Optional[str] = None,
        top_k: int = 20,
        final_k: int = 5,
        use_bm25: bool = True,
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> Dict[str, Any]:
        """
        RAG Chat avec génération LLM.
        
        Effectue une recherche hybride puis génère une réponse via LLM.
        
        Args:
            query: Question de l'utilisateur
            collection: Collection cible (optionnel)
            top_k: Nombre de chunks à récupérer initialement
            final_k: Nombre de chunks à utiliser après reranking
            use_bm25: Utiliser BM25 en plus de la recherche vectorielle
            temperature: Température pour le LLM
            max_tokens: Nombre max de tokens pour la réponse
            
        Returns:
            Dict avec: query, answer, sources, debug_info
        """
        url = f"{self.base_url}/chat"
        
        payload = {
            "query": query,
            "collection": collection,
            "top_k": top_k,
            "final_k": final_k,
            "use_bm25": use_bm25,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        logger.info(f"RAG Chat: '{query[:50]}...' (collection={collection})")
        
        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Chat response: {len(result.get('answer', ''))} chars")
                return result
            
            logger.error(f"Chat error: HTTP {response.status_code}")
            return {
                "query": query,
                "answer": f"Erreur HTTP {response.status_code}",
                "sources": [],
                "debug_info": {"error": response.text[:500]},
            }
            
        except requests.exceptions.Timeout:
            logger.error(f"Chat timeout after {self.timeout}s")
            return {
                "query": query,
                "answer": "Délai d'attente dépassé pour la génération de la réponse.",
                "sources": [],
                "debug_info": {"error": "Timeout"},
            }
        except Exception as e:
            logger.error(f"Chat exception: {e}", exc_info=True)
            return {
                "query": query,
                "answer": f"Erreur: {str(e)}",
                "sources": [],
                "debug_info": {"error": str(e)},
            }
    
    def get_collections(self) -> list:
        """
        Récupère la liste de toutes les collections disponibles.
        
        Returns:
            Liste des collections (noms)
        """
        url = f"{self.base_url}/admin/collections"
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code != 200:
                logger.error(f"Failed to list collections: {response.status_code}")
                return []
            
            result = response.json()
            
            if result.get("status") == "ok":
                collections_info = result.get("collections", [])
                return [c["name"] for c in collections_info]
            
            return []
            
        except Exception as e:
            logger.error(f"Get collections exception: {e}", exc_info=True)
            return []
