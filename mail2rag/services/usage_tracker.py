"""
Service de suivi d'utilisation pour préparation SaaS.

Compteurs trackés :
- emails_processed: Nombre d'emails traités
- drafts_created: Nombre de brouillons générés  
- kb_ingestions: Nombre de documents ingérés dans la KB
- llm_calls: Nombre d'appels LLM

Les compteurs sont persistés dans un fichier JSON et peuvent être
récupérés via l'API pour la facturation future.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)


class UsageTracker:
    """
    Service de suivi d'utilisation pour préparation SaaS.
    
    Collecte des métriques d'utilisation par tenant et workspace
    pour faciliter une future migration vers un modèle SaaS.
    """

    def __init__(self, config: "Config", logger_instance: logging.Logger):
        """
        Initialise le tracker d'utilisation.
        
        Args:
            config: Configuration de l'application
            logger_instance: Logger pour les messages
        """
        self.config = config
        self.logger = logger_instance
        
        # Chemin du fichier de persistance
        state_path = Path(config.state_path)
        self.usage_file = state_path.parent / "usage.json"
        
        # Tenant ID (pour isolation multi-tenant future)
        self.tenant_id = getattr(config, "tenant_id", "") or "default"
        
        # Charger les données existantes
        self._load_usage()

    def _load_usage(self) -> None:
        """Charge les compteurs depuis le fichier."""
        try:
            if self.usage_file.exists():
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    self.usage = json.load(f)
                self.logger.debug(
                    "📊 Usage chargé: %d emails traités",
                    self.usage.get("counters", {}).get("emails_processed", 0),
                )
            else:
                self.usage = self._default_usage()
                self.logger.info("📊 Nouveau fichier d'usage initialisé")
        except Exception as e:
            self.logger.warning(
                "⚠️ Erreur chargement usage, réinitialisation: %s", e
            )
            self.usage = self._default_usage()

    def _default_usage(self) -> Dict[str, Any]:
        """Retourne la structure d'usage par défaut."""
        return {
            "tenant_id": self.tenant_id,
            "period_start": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "counters": {
                "emails_processed": 0,
                "drafts_created": 0,
                "kb_ingestions": 0,
                "llm_calls": 0,
                "rag_searches": 0,
            },
            "by_workspace": {},
        }

    def _save_usage(self) -> None:
        """Persiste les compteurs dans le fichier."""
        try:
            self.usage["last_updated"] = datetime.utcnow().isoformat()
            
            # Créer le répertoire parent si nécessaire
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(self.usage, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error("❌ Erreur sauvegarde usage: %s", e)

    def increment(
        self,
        counter: str,
        workspace: Optional[str] = None,
        amount: int = 1,
    ) -> None:
        """
        Incrémente un compteur global et par workspace.
        
        Args:
            counter: Nom du compteur (emails_processed, drafts_created, etc.)
            workspace: Workspace concerné (optionnel)
            amount: Valeur à ajouter (défaut: 1)
        """
        # Compteur global
        if "counters" not in self.usage:
            self.usage["counters"] = {}
        
        self.usage["counters"][counter] = (
            self.usage["counters"].get(counter, 0) + amount
        )
        
        # Compteur par workspace
        if workspace:
            if "by_workspace" not in self.usage:
                self.usage["by_workspace"] = {}
            
            ws_counters = self.usage["by_workspace"].setdefault(workspace, {})
            ws_counters[counter] = ws_counters.get(counter, 0) + amount
        
        # Sauvegarder
        self._save_usage()
        
        self.logger.debug(
            "📊 Usage: %s +%d (workspace: %s)",
            counter,
            amount,
            workspace or "global",
        )

    def track_email_processed(self, workspace: str) -> None:
        """Raccourci pour tracker un email traité."""
        self.increment("emails_processed", workspace)

    def track_draft_created(self, workspace: str) -> None:
        """Raccourci pour tracker un brouillon créé."""
        self.increment("drafts_created", workspace)

    def track_kb_ingestion(self, workspace: str, doc_count: int = 1) -> None:
        """Raccourci pour tracker une ingestion KB."""
        self.increment("kb_ingestions", workspace, doc_count)

    def track_llm_call(self, workspace: Optional[str] = None) -> None:
        """Raccourci pour tracker un appel LLM."""
        self.increment("llm_calls", workspace)

    def track_rag_search(self, workspace: str) -> None:
        """Raccourci pour tracker une recherche RAG."""
        self.increment("rag_searches", workspace)

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Retourne un rapport d'utilisation complet.
        
        Returns:
            Dict avec tenant_id, period_start, totaux et breakdown par workspace
        """
        return {
            "tenant_id": self.usage.get("tenant_id", self.tenant_id),
            "period_start": self.usage.get("period_start"),
            "last_updated": self.usage.get("last_updated"),
            "total": self.usage.get("counters", {}),
            "by_workspace": self.usage.get("by_workspace", {}),
        }

    def get_workspace_usage(self, workspace: str) -> Dict[str, int]:
        """
        Retourne l'usage pour un workspace spécifique.
        
        Args:
            workspace: Nom du workspace
            
        Returns:
            Dict des compteurs pour ce workspace
        """
        return self.usage.get("by_workspace", {}).get(workspace, {})

    def reset_period(self) -> None:
        """
        Réinitialise les compteurs (début de nouvelle période de facturation).
        
        Conserve le tenant_id mais remet tous les compteurs à zéro.
        """
        old_usage = self.usage.copy()
        self.usage = self._default_usage()
        self._save_usage()
        
        self.logger.info(
            "📊 Période d'usage réinitialisée. "
            "Anciens totaux: emails=%d, drafts=%d, ingestions=%d",
            old_usage.get("counters", {}).get("emails_processed", 0),
            old_usage.get("counters", {}).get("drafts_created", 0),
            old_usage.get("counters", {}).get("kb_ingestions", 0),
        )

    def get_summary_string(self) -> str:
        """
        Retourne un résumé textuel de l'usage.
        
        Returns:
            String formaté pour affichage/log
        """
        counters = self.usage.get("counters", {})
        return (
            f"📊 Usage (tenant: {self.tenant_id}): "
            f"emails={counters.get('emails_processed', 0)}, "
            f"drafts={counters.get('drafts_created', 0)}, "
            f"KB={counters.get('kb_ingestions', 0)}, "
            f"LLM={counters.get('llm_calls', 0)}"
        )
