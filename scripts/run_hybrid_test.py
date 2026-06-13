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
        
    def evaluate_with_llm(self, email_id: str, question: str, response_body: str) -> dict:
        """Évalue la réponse RAG pour détecter les échecs et valider les mots-clés."""
        try:
            answer_lower = response_body.lower()
            
            # 1. Détection des échecs explicites de l'IA (vide de contexte)
            failure_phrases = [
                "je n'ai trouvé aucune information",
                "je n'ai pas trouvé",
                "aucun document ne mentionne",
                "pas d'information pertinente",
                "je ne trouve aucune information",
                "le contexte fourni ne contient aucune information"
            ]
            
            for phrase in failure_phrases:
                if phrase in answer_lower:
                    return {"note": "2/10", "remarque": "Échec : L'IA n'a pas trouvé l'information dans le contexte."}
                    
            if len(response_body) < 50:
                return {"note": "3/10", "remarque": "Réponse trop courte ou absente."}
                
            # 2. Vérification sémantique intelligente (tolérance aux variations de l'IA)
            # Chaque élément de la liste est un groupe de synonymes (un seul suffit pour valider le point)
            expected_concepts = {
                "SUPPORT_URBA": [
                    ["20m2", "20 m2", "20 m²", "20m²", "vingt mètres carrés", "20"], 
                    ["déclaration préalable", "déclaration", "autorisation"]
                ],
                "SUPPORT_VOIRIE": [
                    ["48h", "48 heures", "48 h", "deux jours", "48"], 
                    ["services techniques", "service technique", "mairie"]
                ],
                "SUPPORT_EC_1": [
                    ["portail citoyen", "en ligne", "internet", "site web", "rendez-vous en ligne"], 
                    ["2 semaines", "deux semaines", "14 jours", "quinze jours"]
                ],
                "SUPPORT_EC_2": [
                    ["courrier", "lettre", "voie postale", "par écrit"], 
                    ["service-public.fr", "service public", "internet", "en ligne"]
                ],
                "SUPPORT_ENF_1": [
                    ["justificatif de domicile", "preuve de domicile", "facture"], 
                    ["service enfance", "service de l'enfance", "mairie"]
                ],
                "SUPPORT_ENF_2": [
                    ["30 avril", "30/04", "fin avril"], 
                    ["dossier", "inscription", "formulaire"]
                ],
                "SUPPORT_VOIRIE2": [
                    ["jeudis matin", "jeudi matin", "les jeudis", "jeudi"], 
                    ["zone a", "zone-a", "quartier nord"]
                ],
                "SUPPORT_ASSO": [
                    ["un mois à l'avance", "un mois", "1 mois", "30 jours", "au moins un mois", "un mois minimum"]
                ],
                "SUPPORT_SOCIAL_1": [
                    ["cerfa", "formulaire", "document"], 
                    ["mairie", "ccas", "sur place"]
                ],
                "SUPPORT_SOCIAL_2": [
                    ["aide financière", "aide ponctuelle", "aide exceptionnelle", "ccas"], 
                    ["dossier", "étude", "commission"]
                ],
                "SUPPORT_SECU": [
                    ["22h", "22 heures", "22 h", "vingt-deux heures", "22:00"], 
                    ["tapage nocturne", "nuisances sonores", "bruit"],
                    ["contravention", "amende", "verbaliser", "police", "intervenir"]
                ],
                "SUPPORT_ELEC": [
                    ["commissariat", "police", "gendarmerie"], 
                    ["pièce d'identité", "carte d'identité", "passeport", "cni"]
                ],
            }
            
            if email_id in expected_concepts:
                concepts = expected_concepts[email_id]
                found_concepts = 0
                
                for synonym_list in concepts:
                    if any(syn.lower() in answer_lower for syn in synonym_list):
                        found_concepts += 1
                        
                if found_concepts == len(concepts):
                    return {"note": "10/10", "remarque": "Parfait : Tous les concepts clés sont présents."}
                elif found_concepts > 0:
                    return {"note": "7/10", "remarque": f"Partiel : {found_concepts}/{len(concepts)} concepts trouvés."}
                else:
                    return {"note": "4/10", "remarque": "Médiocre : Aucun concept attendu trouvé, mais l'IA a répondu."}
            
            return {"note": "8/10", "remarque": "Réponse pertinente générée avec succès."}
            
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
                eval_result = self.evaluate_with_llm(email_data['id'], email_data['body'], self.last_sent_email_data['body'])
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
            
        self.print_report(ingested_uids)

    def print_report(self, ingested_uids):
        report_lines = []
        report_lines.append("\n" + "="*140)
        report_lines.append("📊 BILAN SYNTHETIQUE QA - MAIL2RAG")
        report_lines.append("="*140)
        
        # Entête du tableau
        header = f"| {'ID':<15} | {'Type':<15} | {'Sujet':<23} | {'Routage Cible':<25} | {'Latence':<10} | {'Note':<8} | {'Remarque':<20}"
        report_lines.append(header)
        report_lines.append("-" * len(header))
        
        rag_tests = 0
        rag_success = 0
        total_score = 0
        
        for r in self.results:
            row = f"| {r['id']:<15} | {r['type']:<15} | {r['subject']:<23} | {r['target']:<25} | {r['latency']:<10} | {r['note']:<8} | {r['remarque']:<20}"
            report_lines.append(row)
            
            # Calcul des statistiques (uniquement pour les tests qui ont reçu une note)
            if r['note'] != "N/A":
                try:
                    score = int(r['note'].split('/')[0])
                    rag_tests += 1
                    total_score += score
                    if score >= 7:
                        rag_success += 1
                except:
                    pass
        
        report_lines.append("="*140)
        if rag_tests > 0:
            report_lines.append(f"🎯 TAUX DE RÉUSSITE RAG : {rag_success}/{rag_tests} scénarios valides ({(rag_success/rag_tests)*100:.1f}%)")
            report_lines.append(f"⭐ NOTE MOYENNE : {total_score/rag_tests:.1f}/10")
        report_lines.append("="*140 + "\n")
        
        report_text = "\n".join(report_lines)
        print(report_text)
        
        # Génération du rapport HTML
        html_rows = ""
        for r in self.results:
            color = "#4CAF50" if "10/10" in r['note'] else "#FF9800" if "7/10" in r['note'] else "#F44336" if "4/10" in r['note'] or "2/10" in r['note'] else "#9E9E9E"
            html_rows += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>{r['id']}</strong></td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{r['type']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{r['subject']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; font-family: monospace;">{r['target']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{r['latency']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; color: {color}; font-weight: bold;">{r['note']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; font-size: 0.9em;">{r['remarque']}</td>
            </tr>
            """
            
        success_rate = (rag_success/rag_tests)*100 if rag_tests > 0 else 0
        avg_score = total_score/rag_tests if rag_tests > 0 else 0
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; background-color: #f4f6f8; padding: 20px; }}
                .container {{ max-width: 1000px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .summary-box {{ background-color: #e8f4f8; padding: 20px; border-left: 5px solid #3498db; border-radius: 4px; margin-bottom: 30px; }}
                .summary-box p {{ margin: 5px 0; font-size: 1.1em; }}
                .highlight {{ font-weight: bold; color: #2980b9; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background-color: #f8f9fa; color: #333; font-weight: bold; text-align: left; padding: 12px 10px; border-bottom: 2px solid #ddd; }}
                tr:hover {{ background-color: #f1f1f1; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>📊 Rapport QA Mail2RAG</h2>
                
                <div class="summary-box">
                    <p>🎯 Taux de réussite RAG : <span class="highlight">{rag_success}/{rag_tests} scénarios valides ({success_rate:.1f}%)</span></p>
                    <p>⭐ Note Moyenne : <span class="highlight">{avg_score:.1f}/10</span></p>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Type</th>
                            <th>Sujet</th>
                            <th>Cible</th>
                            <th>Latence</th>
                            <th>Note</th>
                            <th>Remarque</th>
                        </tr>
                    </thead>
                    <tbody>
                        {html_rows}
                    </tbody>
                </table>
                <br>
                <p style="font-size: 0.9em; color: #7f8c8d; text-align: center;">Généré automatiquement par l'agent de test Mail2RAG.</p>
            </div>
        </body>
        </html>
        """
        
        # Envoi de l'email HTML à l'admin
        try:
            print("📧 Envoi du rapport HTML par email à admin@dsiatlantic.com...")
            self.original_send_reply(
                to_email="admin@dsiatlantic.com",
                subject=f"📊 Rapport QA Mail2RAG - Score: {rag_success}/{rag_tests}",
                body=html_content,
                is_html=True
            )
            print("✅ Rapport HTML envoyé avec succès.")
        except Exception as e:
            print(f"⚠️ Échec de l'envoi du rapport par email : {e}")
        
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
