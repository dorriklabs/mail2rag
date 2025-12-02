"""
State management for Mail2RAG application.
Handles persistence of application state including secure folder IDs.
"""

import json
import secrets
import threading
from pathlib import Path


class StateManager:
    """Manages application state persistence and secure ID generation."""

    def __init__(self, state_path, logger):
        """
        Initialize state manager.

        Args:
            state_path: Path to state.json file
            logger: Logger instance for error reporting
        """
        self.state_path = Path(state_path)
        self.logger = logger
        # Verrou simple pour sérialiser les accès concurrentiels
        self._lock = threading.Lock()

    def load_state(self):
        """
        Load state from disk.

        Returns:
            dict: State dictionary with 'last_uid' and 'secure_ids'
        """
        try:
            if self.state_path.exists():
                with self.state_path.open("r", encoding="utf-8") as f:
                    state = json.load(f)
                # Ensure structure
                if "secure_ids" not in state or not isinstance(
                    state["secure_ids"], dict
                ):
                    state["secure_ids"] = {}
                if "last_uid" not in state:
                    state["last_uid"] = 0
                return state
        except Exception as e:
            self.logger.error(f"Échec chargement état : {e}")

        return {"last_uid": 0, "secure_ids": {}}

    def _save_state_unlocked(self, state):
        """Sauvegarde le state sans gérer le verrou (à utiliser sous lock)."""
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

    def save_state(self, state):
        """
        Save state to disk.

        Args:
            state: State dictionary to persist
        """
        try:
            with self._lock:
                self._save_state_unlocked(state)
        except Exception as e:
            self.logger.error(f"Échec sauvegarde état : {e}")

    def _generate_unique_secure_id(self, state):
        """
        Generate a unique, opaque secure ID not directly lié à l'UID.

        Format typique : chaîne URL-safe, ex: 'pQ2xJ3kAbCw'
        """
        existing_ids = set(state.get("secure_ids", {}).values())

        # Boucle de sécurité : en pratique, la probabilité de collision est déjà très faible
        for _ in range(100):
            secure_id = secrets.token_urlsafe(8)  # ~11 chars, suffisamment opaque
            if secure_id not in existing_ids:
                return secure_id

        # En cas de collision improbable persistante, on log et génère un ID plus long
        self.logger.warning(
            "Collisions répétées sur secure_id, génération d'un ID plus long."
        )
        return secrets.token_urlsafe(16)

    def get_or_create_secure_id(self, state, uid):
        """
        Get existing secure ID or generate a new one for the given UID.

        Args:
            state: Current state dictionary
            uid: Email UID

        Returns:
            str: Secure folder ID (opaque, stocké dans state['secure_ids'])
        """
        uid_str = str(uid)

        # S'assurer de la structure externe (sans lock fort, c'est fait une fois au début)
        if "secure_ids" not in state or not isinstance(state["secure_ids"], dict):
            state["secure_ids"] = {}

        with self._lock:
            # Si déjà présent, on le réutilise
            if uid_str in state["secure_ids"]:
                return state["secure_ids"][uid_str]

            # Nouveau secure_id totalement opaque (ne contient pas l'UID)
            secure_id = self._generate_unique_secure_id(state)
            state["secure_ids"][uid_str] = secure_id

            try:
                self._save_state_unlocked(state)
            except Exception as e:
                self.logger.error(f"Échec sauvegarde état (get_or_create) : {e}")

            self.logger.info(f"Nouveau secure_id généré pour UID {uid} -> {secure_id}")
            return secure_id
