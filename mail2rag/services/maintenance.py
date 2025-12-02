import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class MaintenanceService:
    def __init__(self, config, client, router, mail_service):
        self.config = config
        self.client = client
        self.router = router
        self.mail_service = mail_service

    def cleanup_archive(self):
        """
        Supprime TOUS les dossiers dans l'archive avant resync.
        ⚠️ ATTENTION : Cette opération est irréversible !
        """
        import shutil
        
        if not self.config.archive_path.exists():
            logger.info("📂 Dossier d'archive inexistant, rien à nettoyer.")
            return
        
        logger.warning("🗑️ NETTOYAGE DE L'ARCHIVE : Suppression de tous les dossiers...")
        
        try:
            folder_count = sum(1 for item in self.config.archive_path.iterdir() if item.is_dir())
            
            for item in self.config.archive_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                    logger.debug(f"   🗑️ Supprimé : {item.name}")
            
            logger.info(f"✅ Archive nettoyée : {folder_count} dossiers supprimés.")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du nettoyage de l'archive : {e}")
            raise

    def sync_all(self):
        """
        Parcourt l'archive locale et ré-ingère tous les documents dans AnythingLLM.
        Utilise le RouterService pour redéterminer le workspace cible.
        """
        logger.info("🔄 Démarrage de la synchronisation complète (Smart Resync)...")
        
        if not self.config.archive_path.exists():
            logger.warning("⚠️ Dossier d'archive introuvable. Rien à synchroniser.")
            return

        count_folders = 0
        count_files = 0
        
        for folder in self.config.archive_path.iterdir():
            if not folder.is_dir():
                continue
            
            secure_id = folder.name
            logger.info(f"📂 Traitement du dossier : {secure_id}")
            
            workspace = self._determine_workspace_from_folder(folder)
            
            if not workspace:
                logger.warning(f"⚠️ Impossible de déterminer le workspace pour {secure_id}. Ignoré.")
                continue
                
            self.client.ensure_workspace_exists(workspace)
            
            uploaded_locs = []
            files_in_folder = [f for f in folder.iterdir() if f.is_file()]
            
            for file_path in files_in_folder:
                if file_path.name.startswith('.'):
                    continue
                
                logger.debug(f"   ⬆️ Upload : {file_path.name}")
                loc = self.client.upload_file(str(file_path))
                if loc:
                    uploaded_locs.append(loc)
                    count_files += 1
            
            if uploaded_locs:
                self.client.update_embeddings(workspace, adds=uploaded_locs)
                logger.info(f"   ✅ {len(uploaded_locs)} fichiers indexés dans '{workspace}'")
            
            count_folders += 1
            
        logger.info(f"🎉 Synchronisation terminée : {count_folders} dossiers, {count_files} fichiers traités.")

    def _determine_workspace_from_folder(self, folder: Path) -> str:
        """
        Tente de reconstruire le contexte (Sujet, Expéditeur) à partir des fichiers textes
        présents dans le dossier pour relancer le routage.
        Si le champ 'Workspace :' est présent, on l'utilise directement.
        """
        candidate_files = list(folder.glob("*.txt"))
        
        subject = "Inconnu"
        sender = "Inconnu"
        body_content = ""
        found_metadata = False
        
        for txt_file in candidate_files:
            try:
                with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                lines = content.splitlines()
                for line in lines[:20]:
                    if line.startswith("Workspace : "):
                        return line.replace("Workspace : ", "").strip()
                        
                    if line.startswith("Sujet : "):
                        subject = line.replace("Sujet : ", "").strip()
                    elif line.startswith("De : "):
                        sender = line.replace("De : ", "").strip()
                
                if subject != "Inconnu" and sender != "Inconnu":
                    body_content = content
                    found_metadata = True
                    break
            except Exception:
                continue
        
        if not found_metadata:
            logger.debug(f"   ℹ️ Pas de métadonnées trouvées dans {folder.name}. Utilisation du workspace par défaut.")
            return self.config.default_workspace

        email_data = {
            'subject': subject,
            'from': sender,
            'body': body_content
        }
        
        return self.router.determine_workspace(email_data)

    def sync_from_anythingllm(self):
        """
        Synchronisation inverse : Détecte les documents dans AnythingLLM mais absents de l'archive.
        Crée des entrées d'archive pour ces documents orphelins.
        """
        logger.info("🔄 Démarrage de la synchronisation inverse (AnythingLLM -> Archive)...")
        
        workspaces = self.client.list_workspaces()
        if not workspaces:
            logger.warning("⚠️ Aucun workspace trouvé dans AnythingLLM")
            return
        
        orphan_count = 0
        
        for ws in workspaces:
            ws_slug = ws.get('slug')
            if not ws_slug:
                continue
                
            logger.info(f"📂 Vérification du workspace : {ws_slug}")
            documents = self.client.list_documents(ws_slug)
            
            logger.debug(f"   DEBUG: type(documents) = {type(documents)}")
            if documents:
                logger.debug(f"   DEBUG: type(documents[0]) = {type(documents[0])}")
                logger.debug(f"   DEBUG: documents[0] = {documents[0]}")
            
            if not documents:
                logger.debug(f"   Pas de documents dans '{ws_slug}'")
                continue
            
            for doc in documents:
                doc_name = doc.get('name', 'unknown')
                doc_location = doc.get('location', '')
                
                if self._document_exists_in_archive(doc_name, doc_location):
                    continue
                
                logger.warning(f"   ⚠️ Orphelin détecté : {doc_name}")
                
                if self._send_synthetic_email_for_orphan(ws_slug, doc):
                    orphan_count += 1
        
        logger.info(f"🎉 Synchronisation inverse terminée : {orphan_count} emails synthétiques envoyés.")
    
    def _document_exists_in_archive(self, doc_name: str, doc_location: str) -> bool:
        """Vérifie si un document existe déjà dans l'archive locale."""
        for folder in self.config.archive_path.iterdir():
            if not folder.is_dir():
                continue
            
            for file in folder.iterdir():
                if file.is_file() and (file.name == doc_name or doc_name in file.name):
                    logger.debug(f"      ✅ Trouvé dans archive : {folder.name}/{file.name}")
                    return True
        
        return False
    
    def _send_synthetic_email_for_orphan(self, workspace_slug: str, doc: dict) -> bool:
        """
        Génère et envoie un email synthétique pour un document orphelin.
        L'email sera ensuite traité normalement par Mail2RAG.
        """
        import time
        
        try:
            doc_name = doc.get('name', 'unknown')
            doc_location = doc.get('location', 'N/A')
            doc_id = doc.get('id', 'N/A')
            
            subject = f"📄 Upload manuel : {doc_name}"
            
            body = f"""Ce document a été uploadé manuellement via l'interface AnythingLLM.

Workspace : {workspace_slug}
Nom du document : {doc_name}
Location AnythingLLM : {doc_location}
Document ID : {doc_id}
Date de détection : {time.strftime('%Y-%m-%d %H:%M')}

---
Document généré automatiquement par le système de synchronisation Mail2RAG.
"""
            
            success = self.mail_service.send_synthetic_email(
                subject=subject,
                body=body,
                attachment_paths=None
            )
            
            if success:
                logger.info(f"      ✅ Email synthétique envoyé pour : {doc_name}")
            else:
                logger.error(f"      ❌ Échec envoi email pour : {doc_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"      ❌ Erreur génération email pour orphelin: {e}")
            return False

    def apply_workspace_configuration(self):
        """
        Applique la configuration des prompts et paramètres LLM aux workspaces.
        - Prompts spécifiques (workspace_prompts)
        - Température / refus spécifiques (workspace_settings)
        - Prompt par défaut sur les autres workspaces
        """
        logger.info("⚙️ Application de la configuration des Workspaces...")

        default_temp = self.config.default_llm_temperature
        default_refusal = self.config.default_refusal_response
        ws_prompts = self.config.workspace_prompts
        ws_settings = self.config.workspace_settings

        local_slugs = set(ws_prompts.keys()) | set(ws_settings.keys())

        # 1) Configs explicites locales
        for slug in sorted(local_slugs):
            prompt = ws_prompts.get(slug, None)
            settings = ws_settings.get(slug, {})

            temp = settings.get("temperature", default_temp)
            refusal = settings.get("refusal_response", default_refusal)

            if not self.client.ensure_workspace_exists(slug):
                logger.error(f"Impossible de créer ou trouver le workspace '{slug}', configuration sautée.")
                continue

            updated = self.client.update_workspace_settings(
                slug,
                system_prompt=prompt,
                temperature=temp,
                refusal_response=refusal
            )

            if updated:
                logger.info(
                    f"✅ Paramètres appliqués à '{slug}' "
                    f"(temp={temp}, refusal={'custom' if refusal else 'None'}, "
                    f"prompt={'spécifique' if prompt else 'inchangé/None'})"
                )

        # 2) Prompt par défaut sur les autres workspaces distants
        if self.config.default_system_prompt:
            logger.info("   Application du prompt par défaut aux autres workspaces distants...")
            try:
                all_workspaces = self.client.list_workspaces()
                for ws in all_workspaces:
                    slug = ws.get('slug')
                    if not slug:
                        continue

                    if slug in local_slugs:
                        continue

                    updated = self.client.update_workspace_settings(
                        slug,
                        system_prompt=self.config.default_system_prompt,
                        temperature=default_temp,
                        refusal_response=default_refusal
                    )
                    if updated:
                        logger.info(
                            f"✅ Prompt par défaut appliqué à '{slug}' "
                            f"(temp={default_temp}, refusal={'custom' if default_refusal else 'None'})"
                        )
            except Exception as e:
                logger.error(f"Erreur lors de l'application du prompt par défaut: {e}")
        
        logger.info("✅ Configuration des Workspaces terminée.")
