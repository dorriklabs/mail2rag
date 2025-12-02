# include/bm25.py

import logging
import os
import pickle
import re
from typing import List, Dict, Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Service:
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
