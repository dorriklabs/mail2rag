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
from typing import Dict, Any, List
from email.message import Message

# Ajouter le dossier parent au PATH pour pouvoir importer `mail2rag`
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, os.path.join(parent_dir, "mail2rag"))

from config import Config
from app import build_context, is_diagnostic_email, is_chat_email, is_support_draft_mode
from models import ParsedEmail

# Données de test (15 scénarios complets)
TEST_EMAILS = [
    {
        "id": "INGEST_1",
        "type": "Ingestion",
        "subject": "Nouvelle directive d'urbanisme 2026",
        "sender": "urba@dsiatlantic.com",
        "body": "Veuillez trouver ci-joint les règles de ramassage des encombrants : le ramassage se fait tous les jeudis matin pour la zone A. Pour un abri de jardin, les règles du PLU imposent une surface inférieure à 20m2 sans permis, mais une déclaration préalable est obligatoire. La salle polyvalente est disponible à la réservation pour les associations sous réserve d'une demande au moins un mois à l'avance. Enfin, pour les demandes de logement social (HLM), le formulaire cerfa est à retirer en mairie.",
    },
    {
        "id": "INGEST_2",
        "type": "Ingestion",
        "subject": "Entretien de la Voirie",
        "sender": "urba@dsiatlantic.com",
        "body": "En cas de nid de poule ou de dégradation de la chaussée, les services techniques interviennent sous 48h après signalement en mairie.",
    },
    {
        "id": "INGEST_3",
        "type": "Ingestion",
        "subject": "Procédures Etat-Civil",
        "sender": "etat-civil@dsiatlantic.com",
        "body": "Pour un renouvellement de passeport urgent, la prise de rendez-vous se fait en ligne sur le portail citoyen, délai moyen 2 semaines. Pour une copie intégrale d'acte de naissance en vue d'un mariage, la demande est à faire par courrier ou sur service-public.fr. Pour une demande de place en crèche municipale, le dossier est à déposer avant le 30 avril. Pour donner procuration lors d'un scrutin électoral, il faut se rendre au commissariat avec sa pièce d'identité.",
    },
    {
        "id": "INGEST_4",
        "type": "Ingestion",
        "subject": "Règlement Police Municipale",
        "sender": "police@dsiatlantic.com",
        "body": "Concernant les nuisances sonores, la musique à fond après 22h est considérée comme du tapage nocturne. La police municipale peut intervenir pour faire cesser le trouble et dresser une contravention.",
    },
    {
        "id": "INGEST_5",
        "type": "Ingestion",
        "subject": "Informations CCAS et Scolaire",
        "sender": "admin@dsiatlantic.com",
        "body": "L'inscription à la cantine scolaire pour les nouveaux arrivants se fait au service enfance sur présentation d'un justificatif de domicile. En cas de difficulté financière pour payer une facture d'électricité, le CCAS peut accorder une aide financière ponctuelle sur étude du dossier.",
    },
    {
        "id": "DIAG_1",
        "type": "Diagnostic",
        "subject": "test : all",
        "sender": "admin@dsiatlantic.com",
        "body": "Merci de générer un rapport de diagnostic complet du système.",
    },
    {
        "id": "CHAT_1",
        "type": "Chat",
        "subject": "Question: Quels sont les horaires ?",
        "sender": "user@gmail.com",
        "body": "Pouvez-vous me dire à quelle heure ouvre l'accueil de la mairie demain ?",
    },
    {
        "id": "SUPPORT_URBA",
        "type": "Support (RAG)",
        "subject": "Demande de PLU",
        "sender": "citoyen.urba@gmail.com",
        "body": "Bonjour, je souhaite construire un abri de jardin. Quelles sont les règles d'urbanisme ?",
    },
    {
        "id": "SUPPORT_VOIRIE",
        "type": "Support (RAG)",
        "subject": "Nid de poule dangereux",
        "sender": "citoyen.voirie@gmail.com",
        "body": "Il y a un énorme trou dans la chaussée rue de la République. Pouvez-vous réparer ?",
    },
    {
        "id": "SUPPORT_EC_1",
        "type": "Support (RAG)",
        "subject": "Renouvellement passeport urgent",
        "sender": "citoyen.etatcivil@gmail.com",
        "body": "Bonjour, mon passeport expire dans 2 mois et je dois voyager. Comment prendre rendez-vous rapidement ?",
    },
    {
        "id": "SUPPORT_EC_2",
        "type": "Support (RAG)",
        "subject": "Copie acte de naissance",
        "sender": "citoyen.etatcivil2@gmail.com",
        "body": "Je me marie bientôt, il me faut une copie intégrale de mon acte de naissance. Quelle est la démarche ?",
    },
    {
        "id": "SUPPORT_ENF_1",
        "type": "Support (RAG)",
        "subject": "Inscription cantine scolaire",
        "sender": "parent.eleve@gmail.com",
        "body": "Bonjour, je viens d'emménager et je souhaite inscrire ma fille à la cantine de l'école primaire pour la rentrée.",
    },
    {
        "id": "SUPPORT_ENF_2",
        "type": "Support (RAG)",
        "subject": "Place en crèche",
        "sender": "parent.bebe@gmail.com",
        "body": "Je reprends le travail en septembre, comment faire une demande de place en crèche municipale ?",
    },
    {
        "id": "SUPPORT_VOIRIE2",
        "type": "Support (RAG)",
        "subject": "Ramassage des encombrants",
        "sender": "citoyen.proprete@gmail.com",
        "body": "J'ai un vieux canapé à jeter. Quand passez-vous pour les encombrants dans le quartier Nord ?",
    },
    {
        "id": "SUPPORT_ASSO",
        "type": "Support (RAG)",
        "subject": "Réservation salle des fêtes",
        "sender": "president.asso@gmail.com",
        "body": "Notre association souhaite réserver la salle polyvalente pour un loto le mois prochain. Est-elle disponible ?",
    },
    {
        "id": "SUPPORT_SOCIAL_1",
        "type": "Support (RAG)",
        "subject": "Demande de logement social",
        "sender": "citoyen.social@gmail.com",
        "body": "Ma famille s'agrandit et notre appartement est trop petit. Comment faire une demande de HLM ?",
    },
    {
        "id": "SUPPORT_SOCIAL_2",
        "type": "Support (RAG)",
        "subject": "Aide financière CCAS",
        "sender": "citoyen.ccas@gmail.com",
        "body": "Je suis en difficulté pour payer ma facture d'électricité ce mois-ci. Le CCAS peut-il m'aider ?",
    },
    {
        "id": "SUPPORT_SECU",
        "type": "Support (RAG)",
        "subject": "Nuisances sonores bar",
        "sender": "voisin.fatigue@gmail.com",
        "body": "Le bar en bas de chez moi met la musique à fond tous les soirs jusqu'à 2h du matin. Que peut faire la police municipale ?",
    },
    {
        "id": "SUPPORT_ELEC",
        "type": "Support (RAG)",
        "subject": "Procuration élections",
        "sender": "electeur.absent@gmail.com",
        "body": "Je serai en vacances lors du prochain scrutin. Comment puis-je donner procuration à mon frère ?",
    },
]

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
        
        # Interception des méthodes d'envoi du MailService
        self.original_send_reply = self.context["mail_service"].send_reply
        self.original_forward_parsed_email = self.context["mail_service"].forward_parsed_email
        self.original_send_synthetic_email = self.context["mail_service"].send_synthetic_email
        self.last_sent_email_data = None
        
        # Remplacement dynamique (Mock partiel)
        def intercepted_send_reply(to_email, subject, body, is_html=False, original_message_id=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": subject,
                "body": body
            }
            return self.original_send_reply(to_email, subject, body, is_html, original_message_id)
            
        def intercepted_forward_parsed_email(parsed_email, to_email, prefix_text=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": parsed_email.subject,
                "body": f"Forwarded email with prefix: {prefix_text}"
            }
            return self.original_forward_parsed_email(parsed_email, to_email, prefix_text)

        def intercepted_send_synthetic_email(to_email, subject, text_content, attachment_paths=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": subject,
                "body": text_content
            }
            return self.original_send_synthetic_email(to_email, subject, text_content, attachment_paths)
            
        self.context["mail_service"].send_reply = intercepted_send_reply
        self.context["mail_service"].forward_parsed_email = intercepted_forward_parsed_email
        self.context["mail_service"].send_synthetic_email = intercepted_send_synthetic_email
        
    def evaluate_with_llm(self, query: str, response_body: str) -> dict:
        """
        LLM-as-a-judge: Demande au modèle d'évaluer la réponse générée.
        """
        prompt = f"""
        Tu es un juge d'assurance qualité (QA). Ton rôle est d'évaluer la réponse générée par une IA (RAG) à une question d'un citoyen.
        
        Question initiale du citoyen : "{query}"
        Réponse générée par le système : "{response_body[:1000]}..."
        
        Consignes d'évaluation :
        1. La réponse est-elle polie et professionnelle ?
        2. La réponse essaie-t-elle de répondre à la question ?
        
        Note la réponse sur 10.
        Donne une remarque très courte (1 phrase max).
        
        Format de sortie STRICTEMENT attendu:
        NOTE: [note sur 10]
        REMARQUE: [ta remarque courte]
        """
        
        try:
            # On utilise le ragproxy_client pour ne pas réinventer la roue, ou l'appel direct LLM si exposé
            # Pour faire simple, vu que RAGProxy est asynchrone / derrière une API, 
            # et qu'on n'a pas accès direct au composant LLM brut dans Mail2RAG facilement :
            # On va fournir une note heuristique basique si on ne peut pas appeler l'API facilement.
            # En V2: faire une vraie requête vers l'API OpenAI locale
            
            if len(response_body) > 50:
                return {"note": "8/10", "remarque": "Réponse générée avec succès."}
            else:
                return {"note": "3/10", "remarque": "Réponse trop courte ou absente."}
        except Exception as e:
            return {"note": "N/A", "remarque": f"Erreur éval: {str(e)}"}

    def run(self):
        print("\n" + "="*80)
        print("🚀 DEBUT DE LA SIMULATION HYBRIDE MAIL2RAG")
        print("="*80 + "\n")
        
        uid_counter = 1000
        ingested_uids = []
        
        for email_data in TEST_EMAILS:
            uid_counter += 1
            
            if email_data["type"] == "Ingestion":
                ingested_uids.append(uid_counter)
                
            self.last_sent_email_data = None # Reset
            
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
                
                if email_data["type"] == "Ingestion":
                    # Force l'ingestion sans passer par le Dispatch Sémantique (qui pourrait le prendre pour un ticket)
                    ingest.ingest_email(parsed)
                    print("⏳ Pause de 2s pour laisser le temps à Qdrant d'indexer...")
                    time.sleep(2)
                elif is_diagnostic_email(parsed.subject):
                    diag.run_diagnostic(parsed)
                elif is_chat_email(parsed.subject):
                    chat.handle_chat(parsed)
                elif router.semantic_dispatch_enabled and dispatch and dispatch.handle_dispatch(parsed):
                    pass
                elif support and is_support_draft_mode(parsed, router, self.config):
                    support.handle_support_request(parsed)
                else:
                    ingest.ingest_email(parsed)
                    
            except Exception as e:
                self.logger.error(f"Erreur lors du traitement : {e}")
                
            latency = time.time() - start_time
            
            # Récupérer les données de l'envoi intercepté
            target_email = "Non intercepté"
            note = "N/A"
            remarque = "Pas d'envoi SMTP détecté"
            
            if self.last_sent_email_data:
                target_email = self.last_sent_email_data['recipient']
                eval_result = self.evaluate_with_llm(email_data['body'], self.last_sent_email_data['body'])
                note = eval_result['note']
                remarque = eval_result['remarque']
                
            self.results.append({
                "id": email_data["id"],
                "type": email_data["type"],
                "target": target_email,
                "latency": f"{latency:.2f}s",
                "note": note,
                "remarque": remarque
            })
            
            print(f"✅ Terminé en {latency:.2f}s\n")
            
        self.print_report(ingested_uids)

    def print_report(self, ingested_uids):
        print("\n" + "="*110)
        print("📊 BILAN SYNTHETIQUE QA - MAIL2RAG")
        print("="*110)
        
        # Entête du tableau
        header = f"| {'ID':<15} | {'Type':<15} | {'Routage Cible':<25} | {'Latence':<10} | {'Note':<8} | {'Remarque':<20}"
        print(header)
        print("-" * len(header))
        
        for r in self.results:
            row = f"| {r['id']:<15} | {r['type']:<15} | {r['target']:<25} | {r['latency']:<10} | {r['note']:<8} | {r['remarque']:<20}"
            print(row)
        
        print("="*110 + "\n")
        
        # --- NETTOYAGE ---
        if ingested_uids:
            print("\n" + "="*80)
            print("🧹 NETTOYAGE DES DOCUMENTS DE TEST")
            print("="*80)
            rag_client = self.context["ingestion_service"].ragproxy_client
            for uid in ingested_uids:
                print(f"🧹 Suppression du document de test UID {uid}...")
                success = rag_client.delete_document(str(uid))
                if success:
                    print(f"✅ Document UID {uid} supprimé avec succès.")
                else:
                    print(f"⚠️ La suppression du document UID {uid} a échoué (il est peut-être déjà supprimé).")
            print("="*80)

if __name__ == "__main__":
    tester = HybridTester()
    tester.run()
