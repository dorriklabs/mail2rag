#!/usr/bin/env python3
"""
Mail2Rag - Script de purge automatique RGPD
Ce script est conçu pour être exécuté via une tâche cron (ex: toutes les nuits à 3h).
Il scanne les collections Qdrant et supprime automatiquement les documents (et archives)
qui dépassent la durée de conservation configurée.
"""

import os
import time
import requests
import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        # Optionnel : logging.FileHandler("/var/log/mail2rag_purge.log")
    ]
)
logger = logging.getLogger("RGPD-Purge")

# Paramètres de connexion
RAG_PROXY_URL = os.environ.get("RAG_PROXY_URL", "http://localhost:8000")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
ARCHIVE_PATH = os.environ.get("ARCHIVE_PATH", "/archive")

# Durées de conservation (en jours) selon les collections (Workspaces)
# "default" s'applique aux collections non spécifiées explicitement.
# Utilisez -1 pour une conservation infinie (pas de purge).
RETENTION_POLICIES = {
    "default": int(os.environ.get("RETENTION_DEFAULT_DAYS", 365 * 2)),  # 2 ans par défaut
    "urbanisme": 365 * 10,  # 10 ans pour l'urbanisme
    "rh": 365 * 2,         # 2 ans pour les RH
    "plui": -1,            # Conservation infinie
}

def get_collections():
    """Récupère la liste de toutes les collections existantes."""
    try:
        response = requests.get(f"{RAG_PROXY_URL}/admin/collections", timeout=10)
        response.raise_for_status()
        data = response.json()
        return [c["name"] for c in data.get("collections", [])]
    except Exception as e:
        logger.error(f"Impossible de récupérer les collections : {e}")
        return []

def get_retention_days(collection: str) -> int:
    """Retourne la durée de conservation pour une collection donnée."""
    return RETENTION_POLICIES.get(collection.lower(), RETENTION_POLICIES["default"])

def delete_document(uid: str, collection: str, secure_id: str | None = None) -> bool:
    """Supprime un document du RAG Proxy et son dossier d'archive physique."""
    success = True
    
    # 1. Suppression dans Qdrant / BM25 via le proxy
    try:
        response = requests.delete(
            f"{RAG_PROXY_URL}/admin/document/{uid}",
            params={"collection": collection},
            timeout=30
        )
        if response.status_code == 200:
            deleted = response.json().get("deleted_count", 0)
            logger.info(f"✅ UID {uid} supprimé de '{collection}' ({deleted} chunks).")
        else:
            logger.error(f"❌ Échec suppression API pour UID {uid}: {response.text}")
            success = False
    except Exception as e:
        logger.error(f"❌ Erreur réseau lors de la suppression de UID {uid}: {e}")
        success = False

    # 2. Suppression de l'archive physique
    if secure_id:
        try:
            archive_folder = Path(ARCHIVE_PATH) / secure_id
            if archive_folder.exists() and archive_folder.is_dir():
                shutil.rmtree(archive_folder)
                logger.info(f"🗑️ Dossier d'archive physique supprimé pour {secure_id}.")
        except Exception as e:
            logger.warning(f"⚠️ Impossible de supprimer l'archive {secure_id} : {e}")
            
    return success

def run_purge():
    """Fonction principale pour exécuter la purge (importable)."""
    logger.info("=== Démarrage de la purge RGPD automatique ===")
    
    collections = get_collections()
    if not collections:
        logger.warning("Aucune collection trouvée ou API injoignable.")
        return
    
    now = datetime.now()
    total_deleted = 0
    
    for collection in collections:
        retention_days = get_retention_days(collection)
        
        if retention_days < 0:
            logger.info(f"Collection '{collection}' ignorée (conservation infinie).")
            continue
            
        cutoff_date = now - timedelta(days=retention_days)
        logger.info(f"Analyse de la collection '{collection}' (Purge avant le {cutoff_date.strftime('%Y-%m-%d')})")
        
        offset = None
        uids_to_delete = {}
        
        while True:
            payload = {
                "limit": 1000,
                "with_payload": True,
                "with_vector": False
            }
            if offset:
                payload["offset"] = offset
            
            try:
                response = requests.post(
                    f"{QDRANT_URL}/collections/{collection}/points/scroll",
                    json=payload,
                    timeout=20
                )
                response.raise_for_status()
                data = response.json().get("result", {})
                points = data.get("points", [])
                
                for point in points:
                    payload_data = point.get("payload", {})
                    date_str = payload_data.get("date")
                    uid = payload_data.get("uid")
                    secure_id = payload_data.get("secure_id")
                    
                    if not uid or not date_str:
                        continue
                    
                    try:
                        doc_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                        if doc_date < cutoff_date:
                            uids_to_delete[uid] = secure_id
                    except ValueError:
                        pass
                
                offset = data.get("next_page_offset")
                if not offset:
                    break
                    
            except Exception as e:
                logger.error(f"Erreur lors du scan de la collection '{collection}' : {e}")
                break
        
        if uids_to_delete:
            logger.info(f"⏳ {len(uids_to_delete)} document(s) expiré(s) trouvé(s) dans '{collection}'. Suppression en cours...")
            for uid, secure_id in uids_to_delete.items():
                if delete_document(uid, collection, secure_id):
                    total_deleted += 1
        else:
            logger.info(f"✅ Aucun document expiré dans '{collection}'.")
            
    logger.info(f"=== Purge terminée. Total de documents supprimés : {total_deleted} ===")
    return total_deleted

def main():
    run_purge()

if __name__ == "__main__":
    main()
