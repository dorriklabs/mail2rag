import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FeedbackService:
    """
    Service pour stocker temporairement les suggestions IA et les lier aux réponses 
    finales des agents pour construire un dataset de Feedback Loop.
    """
    
    def __init__(self, state_dir: Path, log_dir: Path):
        self.db_path = state_dir / "feedback_pending.db"
        self.log_file = log_dir / "feedback_loop.jsonl"
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pending_feedback (
                        thread_id TEXT PRIMARY KEY,
                        question TEXT NOT NULL,
                        ai_suggestion TEXT NOT NULL,
                        metadata TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur initialisation FeedbackService SQLite : {e}")

    def save_pending_suggestion(self, thread_id: str, question: str, ai_suggestion: str, metadata: Dict[str, Any]):
        if not thread_id:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO pending_feedback (thread_id, question, ai_suggestion, metadata)
                    VALUES (?, ?, ?, ?)
                """, (thread_id, question, ai_suggestion, json.dumps(metadata, ensure_ascii=False)))
                conn.commit()
            logger.info(f"Feedback pending saved for thread_id: {thread_id}")
        except Exception as e:
            logger.error(f"Erreur save_pending_suggestion : {e}")

    def log_final_feedback(self, thread_id: str, agent_reply: str, final_metadata: Dict[str, Any] = None):
        if not thread_id:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT question, ai_suggestion, metadata FROM pending_feedback WHERE thread_id = ?", (thread_id,))
                row = cursor.fetchone()
                
                if row:
                    question, ai_suggestion, meta_str = row
                    original_meta = json.loads(meta_str)
                    
                    if final_metadata:
                        original_meta.update(final_metadata)
                        
                    log_entry = {
                        "thread_id": thread_id,
                        "question": question,
                        "ai_suggestion": ai_suggestion,
                        "agent_reply": agent_reply,
                        "metadata": original_meta
                    }
                    
                    with open(self.log_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                    
                    cursor.execute("DELETE FROM pending_feedback WHERE thread_id = ?", (thread_id,))
                    conn.commit()
                    logger.info(f"Feedback loop logged successfully for thread: {thread_id}")
                else:
                    logger.debug(f"No pending feedback found for thread: {thread_id}")
        except Exception as e:
            logger.error(f"Erreur log_final_feedback : {e}")
