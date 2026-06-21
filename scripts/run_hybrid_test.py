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

class IndentFormatter(logging.Formatter):
    def format(self, record):
        msg = record.getMessage()
        return "\n".join(f"  ├─ {line}" for line in msg.split("\n"))

class HybridTester:
    def __init__(self):
        self.config = Config()
        # Désactiver les notifications sortantes pendant les tests
        self.config.teams_webhook_url = None
        self.config.slack_webhook_url = None
        self.config.google_chat_webhook_url = None
        
        # Mettre un log level moins bavard pour le test
        self.logger = logging.getLogger("HybridTest")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Évite la duplication des logs
        
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
            
        handler = logging.StreamHandler()
        handler.setFormatter(IndentFormatter())
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
        
        total_emails = len(TEST_EMAILS)
        for idx, email_data in enumerate(TEST_EMAILS, 1):
            if ingestion_phase and email_data["type"] != "Ingestion":
                ingestion_phase = False
                print("\n" + "="*80)
                print("⏳ Fin de l'ingestion, pause de 3s pour indexation Qdrant...")
                time.sleep(3)
                print("="*80)
                print("🔄 RECONSTRUCTION GLOBALE BM25 (Synchronisation)")
                print("="*80)
                print("✅ BM25 rebuild n'est plus nécessaire : géré nativement par Qdrant (Sparse Vectors).")
                print("="*80 + "\n")
                
            uid_counter += 1
            self.interceptor.reset()
            
            print(f"🔄 Traitement [{idx}/{total_emails}] : [{email_data['id']}] - {email_data['subject']}")
            
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
                
                if email_data["type"] == "Ingestion":
                    # Force l'ingestion sans passer par le Dispatch Sémantique
                    ingest.ingest_email(parsed)
                    ingested_uids[uid_counter] = target_ws
                elif is_diagnostic_email(parsed.subject):
                    diag.run_diagnostic(parsed)
                elif is_chat_email(parsed.subject):
                    chat.handle_chat(parsed)
                elif router.semantic_dispatch_enabled and dispatch and dispatch.handle_dispatch(parsed):
                    pass # Handled by semantic dispatch
                elif support and is_support_draft_mode(parsed, router, self.config):
                    support.handle_support_request(parsed)
                else:
                    from app import is_internal_sender
                    if is_internal_sender(parsed.sender, self.config.imap_user):
                        ingest.ingest_email(parsed)
                        ingested_uids[uid_counter] = target_ws
                    else:
                        self.logger.info(f"Email non routable d'un expéditeur externe ({parsed.sender}) ignoré pour l'ingestion.")
            
            except Exception as e:
                self.logger.error(f"Erreur lors du traitement : {e}")
                print(f"  ├─ EXCEPTION SWALLOWED: {e}")
                
            latency = time.time() - start_time
            
            # Récupérer les données de l'envoi intercepté
            target_email = "Non intercepté"
            note = "N/A"
            remarque = "Pas d'envoi SMTP détecté"
            sources = []
            
            if email_data["type"] == "Ingestion":
                note = "-"
                remarque = "Document indexé"
            
            if self.interceptor.last_sent_email_data:
                target_email = self.interceptor.last_sent_email_data['recipient']
                sources = self.interceptor.last_sent_email_data.get('sources', [])
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
                "remarque": remarque,
                "sources": sources
            })
            
            if email_data["type"] != "Ingestion":
                print(f"  ├─ 🎯 Cible : {target_email}")
                if sources:
                    print(f"  ├─ 📚 Sources RAG : {len(sources)} document(s)")
                
                try:
                    score = float(note)
                    note_str = f"{score}/10"
                    icon = "✅" if score >= 8.0 else ("⚠️" if score >= 5.0 else "❌")
                except ValueError:
                    note_str = str(note)
                    icon = "ℹ️"
                
                print(f"  ├─ {icon}  Note LLM : {note_str}")
                print(f"  ├─ 📝 Remarque : {remarque}")
                print(f"  └─ ⏱️  Terminé en {latency:.2f}s\n")
            else:
                print(f"  ├─ 📥 Action : Document indexé")
                print(f"  └─ ⏱️  Terminé en {latency:.2f}s\n")
            
        # Appel du reporter
        reporter = HtmlReporter(self.interceptor.original_send_reply)
        success_rate, avg_score = reporter.generate_and_send(self.results)
        
        # --- NETTOYAGE ---
        if ingested_uids:
            rag_proxy = self.context["ingestion_service"].ragproxy_client

            def cleanup_test_documents():
                print("\n" + "="*80)
                print(f"🧹 NETTOYAGE DE {len(ingested_uids)} DOCUMENTS DE TEST...")
                
                success_count = 0
                error_count = 0
                for uid, ws in ingested_uids.items():
                    try:
                        rag_proxy.delete_document(str(uid), ws)
                        success_count += 1
                    except Exception as e:
                        print(f"❌ Erreur suppression UID {uid} : {e}")
                        error_count += 1
                        
                print(f"✅ Nettoyage terminé : {success_count} supprimés, {error_count} erreurs.")
                print("="*80)
                
            # Enregistrement du gestionnaire de signaux pour nettoyage propre en cas de Ctrl+C
            import atexit
            atexit.register(cleanup_test_documents)
            
            # Appel manuel immédiat
            cleanup_test_documents()
            atexit.unregister(cleanup_test_documents)
            
        if success_rate < 90.0 or avg_score < 8.0:
            print(f"\n❌ CRITÈRES NON ATTEINTS (Taux: {success_rate:.1f}%, Note: {avg_score:.1f}/10) -> EXIT 1")
            sys.exit(1)
        else:
            print(f"\n✅ TOUS LES CRITÈRES SONT ATTEINTS (Taux: {success_rate:.1f}%, Note: {avg_score:.1f}/10) -> EXIT 0")
            sys.exit(0)

if __name__ == "__main__":
    tester = HybridTester()
    tester.run()
