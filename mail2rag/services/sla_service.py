import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SlaService:
    """
    Service pour traquer les temps de réponse (SLA) entre le Dispatch IA et 
    la réponse de l'agent détectée via BCC.
    """
    
    def __init__(self, state_dir: Path):
        self.db_path = state_dir / "sla_tracker.db"
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dispatch_sla (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id TEXT UNIQUE,
                        sender TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        target_service TEXT NOT NULL,
                        dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        replied_at TIMESTAMP NULL,
                        response_time_hours REAL NULL,
                        status TEXT DEFAULT 'PENDING'
                    )
                """)
                # Indexes pour performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_id ON dispatch_sla(thread_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON dispatch_sla(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_service ON dispatch_sla(target_service)")
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur initialisation SlaService SQLite : {e}")

    def get_status(self, thread_id: str) -> str:
        """Récupère le statut actuel d'un ticket (Test/Helper)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM dispatch_sla WHERE thread_id = ?", (thread_id,))
                result = cursor.fetchone()
                if result:
                    return result[0]
                return "UNKNOWN"
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du statut SLA pour {thread_id} : {e}")
            return "ERROR"

    def log_dispatch(self, thread_id: str, sender: str, subject: str, target_service: str):
        if not thread_id:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO dispatch_sla (thread_id, sender, subject, target_service)
                    VALUES (?, ?, ?, ?)
                """, (thread_id, sender, subject, target_service))
                conn.commit()
            logger.debug(f"SLA logué (Dispatched) pour thread: {thread_id}")
        except Exception as e:
            logger.error(f"Erreur log_dispatch SLA : {e}")

    def mark_replied(self, thread_id: str):
        if not thread_id:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Récupérer l'heure de dispatch pour calculer le chrono
                cursor.execute("SELECT dispatched_at FROM dispatch_sla WHERE thread_id = ? AND status = 'PENDING'", (thread_id,))
                row = cursor.fetchone()
                
                if row:
                    dispatched_at_str = row[0]
                    # Parse le timestamp SQLite (format: YYYY-MM-DD HH:MM:SS)
                    dispatched_at = datetime.strptime(dispatched_at_str, "%Y-%m-%d %H:%M:%S")
                    now = datetime.utcnow()
                    
                    # Calculer la différence en heures
                    diff = now - dispatched_at
                    hours = diff.total_seconds() / 3600.0
                    
                    cursor.execute("""
                        UPDATE dispatch_sla 
                        SET status = 'REPLIED', 
                            replied_at = CURRENT_TIMESTAMP,
                            response_time_hours = ?
                        WHERE thread_id = ? AND status = 'PENDING'
                    """, (round(hours, 2), thread_id))
                    conn.commit()
                    logger.info(f"⏱️ SLA calculé pour {thread_id} : Répondu en {round(hours, 1)} heures.")
        except Exception as e:
            logger.error(f"Erreur mark_replied SLA : {e}")

    def cleanup_old_records(self, days: int = 90):
        """Purge les records traités vieux de plus de N jours."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM dispatch_sla 
                    WHERE status = 'REPLIED' 
                    AND replied_at < datetime('now', ?)
                """, (f'-{days} days',))
                deleted = cursor.rowcount
                conn.commit()
                if deleted > 0:
                    logger.info(f"SLA Cleanup : {deleted} anciens enregistrements purgés.")
        except Exception as e:
            logger.error(f"Erreur cleanup_old_records SLA : {e}")
