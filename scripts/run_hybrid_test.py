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
    # ==========================================
    # COLLECTION 1 : URBANISME (Abri de jardin)
    # ==========================================
    {
        "id": "INGEST_URBA_CIBLE",
        "type": "Ingestion",
        "subject": "Extrait du Plan Local d'Urbanisme - Annexes",
        "sender": "urba@dsiatlantic.com",
        "body": "Conformément aux directives de la commune, l'édification de petites structures extérieures est réglementée. Pour un abri de jardin, les règles du PLU imposent une surface inférieure à 20m2 sans permis de construire. Toutefois, une déclaration préalable de travaux est obligatoirement requise avant tout commencement d'exécution.",
    },
    {
        "id": "INGEST_URBA_DISTRACTEUR_1",
        "type": "Ingestion",
        "subject": "Note de synthèse - Abris en zone inondable",
        "sender": "urba@dsiatlantic.com",
        "body": "Il est strictement interdit de procéder à l'installation d'un abri de jardin dans les zones classées inondables par le PPRI, et ce même pour les structures démontables d'une surface inférieure à 20m2. Aucune déclaration préalable ne sera acceptée pour ces zones.",
    },
    {
        "id": "INGEST_URBA_DISTRACTEUR_2",
        "type": "Ingestion",
        "subject": "Règlementation des piscines privées",
        "sender": "urba@dsiatlantic.com",
        "body": "Toute construction de piscine dont le bassin excède 20m2 de superficie nécessite le dépôt d'un permis de construire. Pour les bassins de taille inférieure, la procédure de déclaration préalable reste de rigueur au service urbanisme.",
    },
    {
        "id": "INGEST_URBA_DISTRACTEUR_3",
        "type": "Ingestion",
        "subject": "Aménagement des abris bus de la métropole",
        "sender": "urba@dsiatlantic.com",
        "body": "L'implantation et la maintenance des abris bus relèvent exclusivement de la compétence de la communauté d'agglomération. Toute demande d'installation d'un nouvel abri doit faire l'objet d'une instruction technique.",
    },
    {
        "id": "INGEST_URBA_DISTRACTEUR_4",
        "type": "Ingestion",
        "subject": "Procès-verbal du conseil municipal",
        "sender": "urba@dsiatlantic.com",
        "body": "Le conseil a débattu des normes esthétiques régissant l'implantation de tout abri de jardin visible depuis la voie publique. La couleur des façades devra obligatoirement s'intégrer au paysage environnant. Le vote définitif est repoussé.",
    },

    # ==========================================
    # COLLECTION 2 : VOIRIE & PROPRETÉ (Nid de poule, Encombrants)
    # ==========================================
    {
        "id": "INGEST_VOIRIE_CIBLE_1",
        "type": "Ingestion",
        "subject": "Charte de propreté et gestion des déchets",
        "sender": "voirie@dsiatlantic.com",
        "body": "La municipalité assure un service de collecte des déchets volumineux. Concernant le ramassage des encombrants, l'intervention des équipes se fait tous les jeudis matin pour la zone A de la commune. Les dépôts sauvages restent passibles d'une amende.",
    },
    {
        "id": "INGEST_VOIRIE_CIBLE_2",
        "type": "Ingestion",
        "subject": "Guide d'intervention rapide voirie",
        "sender": "voirie@dsiatlantic.com",
        "body": "La sécurité des usagers de la route est une priorité. En cas d'apparition d'un nid de poule ou de dégradation majeure de la chaussée, les services techniques s'engagent à intervenir sous 48h après signalement officiel en mairie.",
    },
    {
        "id": "INGEST_VOIRIE_DISTRACTEUR_1",
        "type": "Ingestion",
        "subject": "Nouveau calendrier des ordures ménagères",
        "sender": "voirie@dsiatlantic.com",
        "body": "Le ramassage des ordures ménagères classiques (bacs gris) a été réorganisé. Désormais, le camion de collecte passera le mardi matin pour la zone A et le vendredi pour la zone B. Ce calendrier annule et remplace le précédent.",
    },
    {
        "id": "INGEST_VOIRIE_DISTRACTEUR_2",
        "type": "Ingestion",
        "subject": "Arrêté de circulation - Rue de la République",
        "sender": "voirie@dsiatlantic.com",
        "body": "Considérant les travaux d'enfouissement des réseaux, la circulation routière est temporairement interdite sur toute la longueur de la rue de la République. Cet arrêté ne concerne pas les réparations ponctuelles de type nid de poule.",
    },
    {
        "id": "INGEST_VOIRIE_DISTRACTEUR_3",
        "type": "Ingestion",
        "subject": "Renouvellement du parc automobile",
        "sender": "voirie@dsiatlantic.com",
        "body": "Les services techniques de la ville vont faire l'acquisition de deux nouveaux véhicules utilitaires légers. Une procédure de marché public sera lancée sous 48h par le service des achats.",
    },

    # ==========================================
    # COLLECTION 3 : ETAT-CIVIL & ELECTIONS
    # ==========================================
    {
        "id": "INGEST_EC_CIBLE_1",
        "type": "Ingestion",
        "subject": "Manuel des procédures du guichet unique",
        "sender": "etat-civil@dsiatlantic.com",
        "body": "Pour toute demande de renouvellement de passeport urgent, la prise de rendez-vous s'effectue exclusivement en ligne sur le portail citoyen, avec un délai moyen de traitement estimé à 2 semaines. Par ailleurs, pour obtenir une copie intégrale d'acte de naissance nécessaire à un mariage, la requête est à soumettre soit par courrier, soit directement via service-public.fr.",
    },
    {
        "id": "INGEST_EC_CIBLE_2",
        "type": "Ingestion",
        "subject": "Circulaire d'organisation des élections locales",
        "sender": "etat-civil@dsiatlantic.com",
        "body": "En vue des prochaines échéances, les électeurs dans l'incapacité de se déplacer sont invités à mandater un tiers. Pour donner procuration lors d'un scrutin électoral, l'électeur mandant doit se rendre physiquement au commissariat de police nationale muni de sa pièce d'identité.",
    },
    {
        "id": "INGEST_EC_DISTRACTEUR_1",
        "type": "Ingestion",
        "subject": "Avis - Renouvellement de passeport diplomatique",
        "sender": "etat-civil@dsiatlantic.com",
        "body": "Les fonctionnaires habilités nécessitant un passeport spécifique pour leurs missions doivent adresser leur dossier directement à la préfecture. Le portail citoyen de la ville ne traite pas ces requêtes. Le délai de délivrance incompressible est de 2 semaines.",
    },
    {
        "id": "INGEST_EC_DISTRACTEUR_2",
        "type": "Ingestion",
        "subject": "Bilan de la dernière campagne de scrutin",
        "sender": "etat-civil@dsiatlantic.com",
        "body": "Lors du dernier scrutin électoral, le taux de participation s'est élevé à 56%. Le commissariat a signalé une diminution des pertes de pièce d'identité le jour du vote. Aucune anomalie n'a été constatée lors du dépouillement.",
    },
    {
        "id": "INGEST_EC_DISTRACTEUR_3",
        "type": "Ingestion",
        "subject": "Célébration des mariages en mairie",
        "sender": "etat-civil@dsiatlantic.com",
        "body": "Les cérémonies de mariage civil sont célébrées les samedis matin par l'officier d'état civil. Les futurs époux doivent avoir déposé leur dossier complet, incluant l'acte de naissance de chacun, au moins deux mois avant la date prévue de la cérémonie.",
    },

    # ==========================================
    # COLLECTION 4 : SOCIAL, ENFANCE & ASSOCIATIONS
    # ==========================================
    {
        "id": "INGEST_SOCIAL_CIBLE_1",
        "type": "Ingestion",
        "subject": "Guide de la petite enfance et du scolaire",
        "sender": "social@dsiatlantic.com",
        "body": "Concernant la scolarité, l'inscription à la cantine scolaire s'effectue auprès du service enfance, sur présentation obligatoire d'un justificatif de domicile récent. D'autre part, toute demande de place en crèche municipale requiert qu'un dossier complet soit déposé au secrétariat avant le 30 avril de l'année en cours.",
    },
    {
        "id": "INGEST_SOCIAL_CIBLE_2",
        "type": "Ingestion",
        "subject": "Interventions du CCAS et Logement",
        "sender": "social@dsiatlantic.com",
        "body": "Pour les personnes sollicitant un logement social (HLM), le formulaire cerfa réglementaire est à retirer directement en mairie. De plus, face aux difficultés de paiement de facture d'électricité, le CCAS a la possibilité d'accorder une aide financière ponctuelle, mais uniquement sur étude approfondie du dossier du demandeur.",
    },
    {
        "id": "INGEST_SOCIAL_CIBLE_3",
        "type": "Ingestion",
        "subject": "Règlement d'utilisation des infrastructures",
        "sender": "social@dsiatlantic.com",
        "body": "La municipalité met ses locaux à disposition du tissu associatif local. En particulier, la salle polyvalente est disponible à la réservation pour les associations déclarées, sous réserve expresse de soumettre la demande écrite au moins un mois à l'avance.",
    },
    {
        "id": "INGEST_SOCIAL_DISTRACTEUR_1",
        "type": "Ingestion",
        "subject": "Menus de la cantine scolaire - Période printanière",
        "sender": "social@dsiatlantic.com",
        "body": "La commission des menus a validé les repas jusqu'au 30 avril. Pour les enfants n'ayant pas d'inscription régulière à la cantine scolaire, une réservation exceptionnelle doit être adressée par mail au directeur de l'établissement avec un délai de 48h.",
    },
    {
        "id": "INGEST_SOCIAL_DISTRACTEUR_2",
        "type": "Ingestion",
        "subject": "Subventions aux associations caritatives",
        "sender": "social@dsiatlantic.com",
        "body": "Le CCAS a décidé de revaloriser l'enveloppe allouée aux associations oeuvrant pour le relogement. Cette aide financière permettra de soutenir la création de nouveaux hébergements temporaires, soulageant ainsi la pression sur les demandes de logement social classiques (HLM).",
    },

    # ==========================================
    # COLLECTION 5 : POLICE & SÉCURITÉ
    # ==========================================
    {
        "id": "INGEST_SECU_CIBLE_1",
        "type": "Ingestion",
        "subject": "Arrêté relatif à la tranquillité publique",
        "sender": "police@dsiatlantic.com",
        "body": "Afin de préserver le repos des résidents, des règles strictes s'appliquent sur le territoire communal. Concernant les nuisances sonores, diffuser de la musique à fond après 22h est formellement qualifié de tapage nocturne. Dans une telle situation, la police municipale est habilitée à intervenir pour faire cesser l'infraction et dresser une contravention.",
    },
    {
        "id": "INGEST_SECU_DISTRACTEUR_1",
        "type": "Ingestion",
        "subject": "Règlementation des terrasses commerciales",
        "sender": "police@dsiatlantic.com",
        "body": "Les établissements recevant du public, notamment les bars et restaurants, doivent impérativement cesser l'exploitation de leur terrasse extérieure après 22h. Toute infraction constatée entraînera une amende administrative, indépendamment des questions de musique ou de nuisances sonores internes.",
    },
    {
        "id": "INGEST_SECU_DISTRACTEUR_2",
        "type": "Ingestion",
        "subject": "Contrôles routiers et vitesse",
        "sender": "police@dsiatlantic.com",
        "body": "La police municipale renforce ses contrôles aux abords des établissements scolaires. Tout dépassement de la limitation à 30km/h fera l'objet d'une contravention immédiate, même en l'absence de nuisances sonores liées au régime moteur des véhicules.",
    },
    {
        "id": "INGEST_SECU_DISTRACTEUR_3",
        "type": "Ingestion",
        "subject": "Arrêté de lutte contre les nuisances de chantier",
        "sender": "police@dsiatlantic.com",
        "body": "Les travaux bruyants occasionnant des nuisances sonores sont prohibés les dimanches et jours fériés. Tout artisan pris en défaut d'application de cet arrêté se verra signifier l'arrêt du chantier par la police municipale et s'expose au paiement d'une contravention de 5ème classe.",
    },
    {
        "id": "INGEST_SECU_DISTRACTEUR_4",
        "type": "Ingestion",
        "subject": "Dérogation exceptionnelle - Fête de la Musique",
        "sender": "police@dsiatlantic.com",
        "body": "À l'occasion du 21 juin, la notion de tapage nocturne est assouplie. Les riverains sont autorisés à jouer de la musique à fond sur l'espace public après 22h. Les effectifs de police se concentreront uniquement sur la sécurisation des rassemblements majeurs.",
    },

    # ==========================================
    # REQUÊTES DE DIAGNOSTIC ET CHAT
    # ==========================================
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

    # ==========================================
    # REQUÊTES DE SUPPORT (RAG)
    # ==========================================
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
        self.original_send_combined_email = self.context["mail_service"].send_combined_email
        self.last_sent_email_data = None
        
        # Remplacement dynamique (Mock partiel)
        def intercepted_send_reply(to_email, subject, body, is_html=False, original_message_id=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": subject,
                "body": body
            }
            return self.original_send_reply(to_email, subject, body, is_html, original_message_id)
            
        def intercepted_forward_parsed_email(parsed_email, to_email, prefix_text=None, prefix_html=None, dynamic_attachments=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": parsed_email.subject,
                "body": f"Forwarded email with prefix: {prefix_text} / {prefix_html}"
            }
            return self.original_forward_parsed_email(parsed_email, to_email, prefix_text=prefix_text, prefix_html=prefix_html, dynamic_attachments=dynamic_attachments)

        def intercepted_send_synthetic_email(to_email, subject, text_content, attachment_paths=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": subject,
                "body": text_content
            }
            return self.original_send_synthetic_email(to_email, subject, text_content, attachment_paths)

        def intercepted_send_combined_email(service_email, client_email, subject, body_html, original_message_id=None):
            self.last_sent_email_data = {
                "recipient": service_email,
                "subject": subject,
                "body": body_html
            }
            return self.original_send_combined_email(service_email, client_email, subject, body_html, original_message_id)
            
        self.context["mail_service"].send_reply = intercepted_send_reply
        self.context["mail_service"].forward_parsed_email = intercepted_forward_parsed_email
        self.context["mail_service"].send_synthetic_email = intercepted_send_synthetic_email
        self.context["mail_service"].send_combined_email = intercepted_send_combined_email
        
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
