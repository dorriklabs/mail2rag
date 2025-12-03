# include/bm25.py

import logging
import os
import pickle
import re
from pathlib import Path
from typing import List, Dict, Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Service:
    """
    Service BM25 mono-collection (legacy).
    Conservé pour rétrocompatibilité.
    """
    def __init__(self, index_path: str):
        self.bm25: Optional[BM25Okapi] = None
        self.docs: List[str] = []
        self.meta: List[Dict] = []

        if os.path.exists(index_path):
            try:
                with open(index_path, "rb") as f:
                    self.bm25, self.docs, self.meta = pickle.load(f)
                logger.info(f"BM25 index loaded: {len(self.docs)} docs")
            except Exception as e:
                logger.error(f"Failed to load BM25 index: {e}")
                self.bm25 = None
        else:
            logger.info(f"BM25 index not found at {index_path}")

    def is_ready(self) -> bool:
        return self.bm25 is not None and len(self.docs) == len(self.meta) > 0

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize avec lowercase et suppression ponctuation basique."""
        # Lowercase
        text = text.lower()
        # Suppression ponctuation (garde apostrophes)
        text = re.sub(r'[^\w\s\']', ' ', text)
        # Split et filtrage
        return [t for t in text.split() if t]

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        if not self.is_ready():
            return []

        tokens = self._tokenize(query)
        scores = self.bm25.get_scores(tokens)
        idx = scores.argsort()[-top_k:][::-1]

        return [
            {
                "text": self.docs[i],
                "metadata": self.meta[i],
                "score": float(scores[i]),
            }
            for i in idx
        ]


class MultiBM25Service:
    """
    Service BM25 multi-collections.
    Gère un index BM25 séparé par collection (workspace).
    """
    def __init__(self, base_index_dir: str = "/bm25"):
        self.base_index_dir = Path(base_index_dir)
        self.base_index_dir.mkdir(parents=True, exist_ok=True)
        
        # Dict[collection_name, (bm25, docs, meta)]
        self.indexes: Dict[str, tuple] = {}
        
        # Charger tous les index existants
        self._load_all_indexes()
    
    def _load_all_indexes(self):
        """Charge tous les index BM25 existants au démarrage."""
        for index_file in self.base_index_dir.glob("bm25_*.pkl"):
            collection_name = index_file.stem.replace("bm25_", "")
            try:
                with open(index_file, "rb") as f:
                    bm25, docs, meta = pickle.load(f)
                self.indexes[collection_name] = (bm25, docs, meta)
                logger.info(f"Loaded BM25 index for '{collection_name}': {len(docs)} docs")
            except Exception as e:
                logger.error(f"Failed to load BM25 index for '{collection_name}': {e}")
    
    def is_ready(self, collection: Optional[str] = None) -> bool:
        """Vérifie si un index est prêt pour une collection donnée."""
        if collection is None:
            # Au moins un index disponible
            return len(self.indexes) > 0
        return collection in self.indexes and len(self.indexes[collection][1]) > 0
    
    def get_collection_stats(self, collection: str) -> Dict:
        """Retourne les statistiques d'une collection."""
        if collection not in self.indexes:
            return {"ready": False, "docs_count": 0}
        
        _, docs, _ = self.indexes[collection]
        return {
            "ready": True,
            "docs_count": len(docs)
        }
    
    def list_collections(self) -> List[str]:
        """Retourne la liste des collections ayant un index BM25."""
        return list(self.indexes.keys())
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize avec lowercase et suppression ponctuation basique."""
        text = text.lower()
        text = re.sub(r'[^\w\s\']', ' ', text)
        return [t for t in text.split() if t]
    
    def search(self, query: str, collection: str, top_k: int = 10) -> List[Dict]:
        """Recherche BM25 dans une collection spécifique."""
        if not self.is_ready(collection):
            logger.warning(f"BM25 index not ready for collection '{collection}'")
            return []
        
        bm25, docs, meta = self.indexes[collection]
        tokens = self._tokenize(query)
        scores = bm25.get_scores(tokens)
        idx = scores.argsort()[-top_k:][::-1]
        
        return [
            {
                "text": docs[i],
                "metadata": meta[i],
                "score": float(scores[i]),
            }
            for i in idx
        ]
    
    def build_index(self, collection: str, docs: List[str], meta: List[Dict]) -> bool:
        """Construit et sauvegarde un index BM25 pour une collection."""
        try:
            if not docs:
                logger.warning(f"No documents to index for collection '{collection}'")
                return False
            
            # Tokenization
            tokenized = [self._tokenize(doc) for doc in docs]
            
            # Créer index BM25
            bm25 = BM25Okapi(tokenized)
            
            # Sauvegarder
            index_path = self.base_index_dir / f"bm25_{collection}.pkl"
            with index_path.open("wb") as f:
                pickle.dump((bm25, docs, meta), f)
            
            # Mettre en cache
            self.indexes[collection] = (bm25, docs, meta)
            
            logger.info(
                f"Built BM25 index for '{collection}': {len(docs)} docs, "
                f"size: {index_path.stat().st_size / 1024:.2f} KB"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to build BM25 index for '{collection}': {e}")
            return False
    
    def delete_index(self, collection: str) -> bool:
        """Supprime un index BM25 pour une collection."""
        try:
            index_path = self.base_index_dir / f"bm25_{collection}.pkl"
            
            if index_path.exists():
                index_path.unlink()
            
            if collection in self.indexes:
                del self.indexes[collection]
            
            logger.info(f"Deleted BM25 index for '{collection}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete BM25 index for '{collection}': {e}")
            return False
