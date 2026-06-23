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
            
        # Register RGPD Purge
        purge_config = self.tasks_config.get("rgpd_purge", {})
        if purge_config.get("active", False):
            hour = purge_config.get("hour", "03")
            minute = purge_config.get("minute", "00")
            
            # Add job
            self.scheduler.add_job(
                self.run_rgpd_purge,
                trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                id="rgpd_purge",
                replace_existing=True
            )
            logger.info(f"Scheduled rgpd_purge at {hour}:{minute} daily")
            logger.info("rgpd_purge is disabled")

        # Register Analyze Feedback
        analyze_config = self.tasks_config.get("analyze_feedback", {})
        if analyze_config.get("active", False):
            hour = analyze_config.get("hour", "02")
            minute = analyze_config.get("minute", "00")
            
            # Add job
            self.scheduler.add_job(
                self.run_analyze_feedback,
                trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                id="analyze_feedback",
                replace_existing=True
            )
            logger.info(f"Scheduled analyze_feedback at {hour}:{minute} daily")
        else:
            logger.info("analyze_feedback is disabled")

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

    def update_config(self, task_name: str, active: bool, hour: str, minute: str):
        if task_name not in self.tasks_config:
            self.tasks_config[task_name] = {}
            
        self.tasks_config[task_name] = {
            "active": active,
            "hour": hour.zfill(2),
            "minute": minute.zfill(2)
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

    async def run_analyze_feedback(self):
        """Run the analyze feedback task by creating a trigger file for mail2rag."""
        logger.info("Starting Analyze Feedback trigger task...")
        try:
            trigger_file = "/app/state/trigger_analyze.json"
            os.makedirs(os.path.dirname(trigger_file), exist_ok=True)
            with open(trigger_file, "w") as f:
                json.dump({"trigger": "analyze_feedback", "timestamp": datetime.now().isoformat()}, f)
            logger.info("Trigger file for analyze_feedback created successfully.")
        except Exception as e:
            logger.error(f"Error creating trigger file for analyze_feedback: {e}")

# Global instance
scheduler_manager = SchedulerManager()
