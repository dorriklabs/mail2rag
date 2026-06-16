import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, Union
from models import ExtractedDocument

logger = logging.getLogger(__name__)

class CacheService:
    """
    Service gérant le cache d'extraction documentaire.
    Utilise SQLite comme index (hash -> filepath) et stocke les données détaillées en JSON.
    """
    
    def __init__(self, state_dir: Path, enabled: bool = True):
        self.enabled = enabled
        self.cache_dir = state_dir / "ingestion_cache"
        self.db_path = self.cache_dir / "cache_index.db"
        
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cache_index (
                        file_hash TEXT PRIMARY KEY,
                        json_path TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur initialisation cache SQLite : {e}")
            self.enabled = False

    def get_cache_key(self, filepath: str | Path, params: Dict[str, Any] = None) -> str:
        """Calcule un hash composite (SHA256 du fichier + hash des paramètres)."""
        # Hash du fichier
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()
        
        # Hash des paramètres
        if params:
            import json
            # Trier les clés pour une empreinte stable
            params_str = json.dumps(params, sort_keys=True)
            params_hash = hashlib.md5(params_str.encode('utf-8')).hexdigest()
            return f"{file_hash}_{params_hash}"
            
        return file_hash

    def get_cached_extraction(self, file_hash: str, return_structured: bool = False) -> Optional[Union[Dict[str, Any], ExtractedDocument]]:
        """Récupère l'extraction depuis le cache si elle existe."""
        if not self.enabled:
            return None
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT json_path FROM cache_index WHERE file_hash = ?", (file_hash,))
                row = cursor.fetchone()
                
                if row:
                    json_path = Path(row[0])
                    if json_path.exists():
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if return_structured and "schema_version" in data:
                                return ExtractedDocument(**data)
                            return data
                    else:
                        # Index invalide (fichier supprimé)
                        cursor.execute("DELETE FROM cache_index WHERE file_hash = ?", (file_hash,))
                        conn.commit()
                        logger.warning(f"Entrée cache orpheline supprimée pour {file_hash}")
        except Exception as e:
            logger.error(f"Erreur lecture cache pour {file_hash} : {e}")
            
        return None

    def set_cached_extraction(self, file_hash: str, data: Union[Dict[str, Any], ExtractedDocument]) -> None:
        """Enregistre le résultat de l'extraction dans le cache."""
        if not self.enabled:
            return
            
        try:
            json_filename = f"{file_hash}.json"
            json_path = self.cache_dir / json_filename
            
            # Sauvegarde JSON
            with open(json_path, "w", encoding="utf-8") as f:
                if isinstance(data, ExtractedDocument):
                    json.dump(data.model_dump(), f, ensure_ascii=False, indent=2)
                else:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
            # Mise à jour index SQLite
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO cache_index (file_hash, json_path)
                    VALUES (?, ?)
                """, (file_hash, str(json_path)))
                conn.commit()
                
            logger.info(f"Extraction mise en cache pour {file_hash[:8]}...")
        except Exception as e:
            logger.error(f"Erreur écriture cache pour {file_hash} : {e}")
