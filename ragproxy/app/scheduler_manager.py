import os
import json
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import asyncio
import subprocess

logger = logging.getLogger(__name__)

CONFIG_PATH = os.environ.get("CRON_CONFIG_PATH", "/app/state/cron_config.json")
SCRIPTS_PATH = os.environ.get("SCRIPTS_PATH", "/app/scripts")

def trigger_remote_task(task_name: str, trigger_filename: str):
    """Crée un fichier déclencheur pour déléguer une tâche à Mail2Rag (ex: cron)."""
    logger.info(f"⏰ Cron : Déclenchement de la tâche '{task_name}'...")
    try:
        trigger_file = Path(os.getenv("STATE_PATH", "/app/state/state.json")).parent / trigger_filename
        trigger_file.parent.mkdir(parents=True, exist_ok=True)
        with open(trigger_file, "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "source": "cron"}, f)
        logger.info(f"Fichier déclencheur '{trigger_filename}' créé avec succès.")
    except Exception as e:
        logger.error(f"❌ Erreur lors de la création du déclencheur {task_name} : {e}")

class SchedulerManager:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.tasks_config = self._load_config()
        self._setup_jobs()

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cron config: {e}")
        
        # Default configuration
        default_config = {
            "rgpd_purge": {
                "active": False,
                "hour": "03",
                "minute": "00"
            },
            "analyze_feedback": {
                "active": False,
                "hour": "02",
                "minute": "00"
            },
            "sla_report": {
                "active": True,
                "hour": "08",
                "minute": "00",
                "day_of_week": "1"
            }
        }
        self._save_config(default_config)
        return default_config

    def _save_config(self, config):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving cron config: {e}")

    def _setup_jobs(self):
        # Clear existing jobs
        for job in self.scheduler.get_jobs():
            job.remove()
            
        # Register tasks
        for task_name, task_config in self.tasks_config.items():
            if not task_config.get("active", False):
                logger.info(f"{task_name} is disabled")
                continue

            try:
                if task_name == "rgpd_purge":
                    self.scheduler.add_job(
                        self.run_rgpd_purge,
                        trigger=CronTrigger(hour=int(task_config.get("hour", "03")), minute=int(task_config.get("minute", "00"))),
                        id='rgpd_purge',
                        name='Purge RGPD Automatique',
                        replace_existing=True
                    )
                    logger.info(f"Scheduled rgpd_purge at {task_config.get('hour')}:{task_config.get('minute')} daily")
                
                elif task_name == "analyze_feedback":
                    self.scheduler.add_job(
                        trigger_remote_task,
                        args=["analyze_feedback", "trigger_analyze.json"],
                        trigger=CronTrigger(hour=int(task_config.get("hour", "02")), minute=int(task_config.get("minute", "00"))),
                        id="analyze_feedback",
                        replace_existing=True
                    )
                    logger.info(f"Scheduled analyze_feedback at {task_config.get('hour')}:{task_config.get('minute')} daily")

                elif task_name == "sla_report":
                    day_of_week = task_config.get("day_of_week", "1")
                    hour = task_config.get("hour", "08")
                    minute = task_config.get("minute", "00")
                    self.scheduler.add_job(
                        trigger_remote_task,
                        args=["sla_report", "trigger_sla_report.json"],
                        trigger=CronTrigger(hour=int(hour), minute=int(minute), day_of_week=day_of_week),
                        id='send_weekly_sla_report',
                        name='Rapport SLA par E-mail',
                        replace_existing=True
                    )
                    logger.info(f"Scheduled sla_report at {hour}:{minute} (day {day_of_week})")

            except Exception as e:
                logger.error(f"Error scheduling {task_name}: {e}")

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shut down")

    def get_config(self):
        return self.tasks_config

    def update_config(self, task_name: str, active: bool, hour: str, minute: str, day_of_week: str = "*"):
        """Met à jour la configuration d'une tâche et la replanifie si nécessaire."""
        if task_name not in self.tasks_config:
            self.tasks_config[task_name] = {}
            
        self.tasks_config[task_name] = {
            "active": active,
            "hour": hour.zfill(2),
            "minute": minute.zfill(2),
            "day_of_week": day_of_week
        }
        self._save_config(self.tasks_config)
        self._setup_jobs()
        return self.tasks_config[task_name]

    async def run_rgpd_purge(self):
        """Run the RGPD purge script asynchronously without blocking the API."""
        logger.info("Starting RGPD Purge background task...")
        try:
            import sys
            if SCRIPTS_PATH not in sys.path:
                sys.path.append(SCRIPTS_PATH)
            
            # Setup environment for the script
            os.environ["RAG_PROXY_URL"] = "http://localhost:8000"
            qdrant_host = os.environ.get("VECTOR_DB_HOST", "qdrant")
            qdrant_port = os.environ.get("VECTOR_DB_PORT", "6333")
            os.environ["QDRANT_URL"] = f"http://{qdrant_host}:{qdrant_port}"
            
            # Use importlib to dynamically load the script as a module
            import importlib.util
            script_path = os.path.join(SCRIPTS_PATH, "rgpd_purge.py")
            if not os.path.exists(script_path):
                logger.error(f"Script not found at {script_path}")
                return
                
            spec = importlib.util.spec_from_file_location("rgpd_purge", script_path)
            if spec is None or spec.loader is None:
                logger.error(f"Could not load script spec from {script_path}")
                return
            
            rgpd_purge = importlib.util.module_from_spec(spec)
            sys.modules["rgpd_purge"] = rgpd_purge
            spec.loader.exec_module(rgpd_purge)
            
            # Run the imported function in a thread to avoid blocking the event loop
            deleted_count = await asyncio.to_thread(rgpd_purge.run_purge)
            logger.info(f"RGPD Purge completed. Total deleted: {deleted_count}")
                
        except Exception as e:
            logger.error(f"Error running RGPD Purge: {e}")



# Global instance
scheduler_manager = SchedulerManager()
