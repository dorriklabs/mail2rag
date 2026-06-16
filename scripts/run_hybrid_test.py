#!/usr/bin/env python3
"""
Script de test hybride E2E pour Mail2RAG.
Bypasse IMAP, injecte des emails en mémoire, intercepte l'envoi SMTP pour évaluation (LLM-as-a-judge),
et effectue tout de même l'envoi SMTP réel vers les boîtes des services.
"""

import sys
import os
import time
import logging
from email.message import Message

# Ajouter le dossier parent au PATH pour pouvoir importer `mail2rag`
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
mail2rag_dir = os.path.join(parent_dir, "mail2rag")
sys.path.insert(0, mail2rag_dir if os.path.exists(mail2rag_dir) else parent_dir)

from config import Config
from app import build_context, is_diagnostic_email, is_chat_email, is_support_draft_mode
from models import ParsedEmail

# Import des nouveaux modules (tests_framework)
from tests_framework.data.test_cases import TEST_EMAILS
from tests_framework.mocks.mail_interceptor import MailInterceptor
from tests_framework.evaluation.evaluator import Evaluator
from tests_framework.reporting.html_reporter import HtmlReporter

class HybridTester:
    def __init__(self):
        self.config = Config()
        
        # Mettre un log level moins bavard pour le test
        self.logger = logging.getLogger("HybridTest")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        self.logger.addHandler(handler)
        
        # Construire le contexte interne de l'application
        self.logger.info("Démarrage du contexte Mail2RAG...")
        self.context = build_context(self.config, self.logger)
        
        self.results = []
        
        # Initialisation du mock d'interception SMTP
        self.interceptor = MailInterceptor(self.context["mail_service"])

    def run(self):
        print("\n" + "="*80)
        print("🚀 DEBUT DE LA SIMULATION HYBRIDE MAIL2RAG")
        print("="*80 + "\n")
        
        uid_counter = 1000
        ingested_uids = {}
        ingestion_phase = True
        
        for email_data in TEST_EMAILS:
            if ingestion_phase and email_data["type"] != "Ingestion":
                ingestion_phase = False
                print("\n" + "="*80)
                print("🔄 RECONSTRUCTION GLOBALE BM25 (Synchronisation)")
                print("="*80)
                try:
                    import requests
                    rag_url = self.config.rag_proxy_url.rstrip("/")
                    print(f"Appel de l'API : {rag_url}/admin/rebuild-all-bm25...")
                    resp = requests.post(f"{rag_url}/admin/rebuild-all-bm25", timeout=120)
                    if resp.status_code == 200:
                        print(f"✅ BM25 rebuild OK : {resp.json()}")
                    else:
                        print(f"⚠️ Erreur BM25 rebuild : {resp.status_code} - {resp.text}")
                except Exception as e:
                    print(f"❌ Exception lors du rebuild BM25 : {e}")
                print("="*80 + "\n")
                
            uid_counter += 1
            self.interceptor.reset()
            
            print(f"🔄 Traitement : [{email_data['id']}] - {email_data['subject']}")
            
            # Création du faux message IMAP
            msg = Message()
            msg['Subject'] = email_data['subject']
            msg['From'] = email_data['sender']
            msg['To'] = self.config.imap_user
            
            parsed = ParsedEmail(
                uid=uid_counter,
                msg=msg,
                subject=email_data['subject'],
                sender=email_data['sender'],
                body=email_data['body'],
                to=self.config.imap_user,
                cc="",
                date="",
                message_id="<test-mock-id@dsiatlantic.com>",
                is_synthetic=True
            )
            
            start_time = time.time()
            
            try:
                # Logique de routage similaire à `run_poller`
                router = self.context["router"]
                diag = self.context["diagnostic_service"]
                chat = self.context["chat_service"]
                dispatch = self.context.get("dispatch_service")
                support = self.context.get("support_draft_service")
                ingest = self.context["ingestion_service"]
                
                target_ws = router.determine_workspace(parsed.email_data) or "default-workspace"
                print(f"DEBUG: target_workspace = {target_ws}")
                print(f"DEBUG: semantic_dispatch_enabled = {router.semantic_dispatch_enabled}")
                
                if email_data["type"] == "Ingestion":
                    # Force l'ingestion sans passer par le Dispatch Sémantique
                    ingest.ingest_email(parsed)
                    ingested_uids[uid_counter] = target_ws
                    print("⏳ Pause de 2s pour laisser le temps à Qdrant d'indexer...")
                    time.sleep(2)
                elif is_diagnostic_email(parsed.subject):
                    diag.run_diagnostic(parsed)
                elif is_chat_email(parsed.subject):
                    chat.handle_chat(parsed)
                elif router.semantic_dispatch_enabled and dispatch and dispatch.handle_dispatch(parsed):
                    print("DEBUG: handled by dispatch")
                elif support and is_support_draft_mode(parsed, router, self.config):
                    print("DEBUG: handled by support_draft_mode")
                    support.handle_support_request(parsed)
                else:
                    print("DEBUG: fallback to ingest")
                    ingest.ingest_email(parsed)
                    ingested_uids[uid_counter] = target_ws
                    
            except Exception as e:
                self.logger.error(f"Erreur lors du traitement : {e}")
                print(f"EXCEPTION SWALLOWED: {e}")
                
            latency = time.time() - start_time
            
            # Récupérer les données de l'envoi intercepté
            target_email = "Non intercepté"
            note = "N/A"
            remarque = "Pas d'envoi SMTP détecté"
            
            if email_data["type"] == "Ingestion":
                note = "-"
                remarque = "Document indexé"
            
            if self.interceptor.last_sent_email_data:
                target_email = self.interceptor.last_sent_email_data['recipient']
                eval_result = Evaluator.evaluate_with_llm(email_data['id'], email_data['body'], self.interceptor.last_sent_email_data['body'])
                note = eval_result['note']
                remarque = eval_result['remarque']
                
            self.results.append({
                "id": email_data["id"],
                "type": email_data["type"],
                "subject": email_data["subject"][:20] + "..." if len(email_data["subject"]) > 20 else email_data["subject"],
                "target": target_email,
                "latency": f"{latency:.2f}s",
                "note": note,
                "remarque": remarque
            })
            
            print(f"✅ Terminé en {latency:.2f}s\n")
            
        # Appel du reporter
        reporter = HtmlReporter(self.interceptor.original_send_reply)
        reporter.generate_and_send(self.results)
        
        # --- NETTOYAGE ---
        if ingested_uids:
            rag_proxy = self.context["ingestion_service"].ragproxy_client

            def cleanup_test_documents():
                print("\n" + "="*80)
                print("🧹 NETTOYAGE DES DOCUMENTS DE TEST")
                print("="*80)
                
                for uid, ws in ingested_uids.items():
                    try:
                        print(f"🧹 Suppression du document de test UID {uid} dans {ws}...")
                        rag_proxy.delete_document(str(uid), ws)
                        print(f"✅ Document UID {uid} supprimé avec succès.")
                    except Exception as e:
                        print(f"Erreur suppression UID {uid} : {e}")
                        
                print("="*80)
                
            # Enregistrement du gestionnaire de signaux pour nettoyage propre en cas de Ctrl+C
            import atexit
            atexit.register(cleanup_test_documents)
            
            # Appel manuel immédiat
            cleanup_test_documents()
            atexit.unregister(cleanup_test_documents)

if __name__ == "__main__":
    tester = HybridTester()
    tester.run()
