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
        "sender": "citoyen.user@dsiatlantic.com",
        "body": "Pouvez-vous me dire à quelle heure ouvre l'accueil de la mairie demain ?",
    },

    # ==========================================
    # REQUÊTES DE SUPPORT (RAG)
    # ==========================================
    {
        "id": "SUPPORT_URBA",
        "type": "Support (RAG)",
        "subject": "Demande de PLU",
        "sender": "citoyen.urba@dsiatlantic.com",
        "body": "Bonjour, je souhaite construire un abri de jardin. Quelles sont les règles d'urbanisme ?",
    },
    {
        "id": "SUPPORT_VOIRIE",
        "type": "Support (RAG)",
        "subject": "Nid de poule dangereux",
        "sender": "citoyen.voirie@dsiatlantic.com",
        "body": "Il y a un énorme trou dans la chaussée rue de la République. Pouvez-vous réparer ?",
    },
    {
        "id": "SUPPORT_EC_1",
        "type": "Support (RAG)",
        "subject": "Renouvellement passeport urgent",
        "sender": "citoyen.etatcivil@dsiatlantic.com",
        "body": "Bonjour, mon passeport expire dans 2 mois et je dois voyager. Comment prendre rendez-vous rapidement ?",
    },
    {
        "id": "SUPPORT_EC_2",
        "type": "Support (RAG)",
        "subject": "Copie acte de naissance",
        "sender": "citoyen.etatcivil2@dsiatlantic.com",
        "body": "Je me marie bientôt, il me faut une copie intégrale de mon acte de naissance. Quelle est la démarche ?",
    },
    {
        "id": "SUPPORT_ENF_1",
        "type": "Support (RAG)",
        "subject": "Inscription cantine scolaire",
        "sender": "parent.eleve@dsiatlantic.com",
        "body": "Bonjour, je viens d'emménager et je souhaite inscrire ma fille à la cantine de l'école primaire pour la rentrée.",
    },
    {
        "id": "SUPPORT_ENF_2",
        "type": "Support (RAG)",
        "subject": "Place en crèche",
        "sender": "parent.bebe@dsiatlantic.com",
        "body": "Je reprends le travail en septembre, comment faire une demande de place en crèche municipale ?",
    },
    {
        "id": "SUPPORT_VOIRIE2",
        "type": "Support (RAG)",
        "subject": "Ramassage des encombrants",
        "sender": "citoyen.proprete@dsiatlantic.com",
        "body": "J'ai un vieux canapé à jeter. Quand passez-vous pour les encombrants dans le quartier Nord ?",
    },
    {
        "id": "SUPPORT_ASSO",
        "type": "Support (RAG)",
        "subject": "Réservation salle des fêtes",
        "sender": "president.asso@dsiatlantic.com",
        "body": "Notre association souhaite réserver la salle polyvalente pour un loto le mois prochain. Est-elle disponible ?",
    },
    {
        "id": "SUPPORT_SOCIAL_1",
        "type": "Support (RAG)",
        "subject": "Demande de logement social",
        "sender": "citoyen.social@dsiatlantic.com",
        "body": "Ma famille s'agrandit et notre appartement est trop petit. Comment faire une demande de HLM ?",
    },
    {
        "id": "SUPPORT_SOCIAL_2",
        "type": "Support (RAG)",
        "subject": "Aide financière CCAS",
        "sender": "citoyen.ccas@dsiatlantic.com",
        "body": "Je suis en difficulté pour payer ma facture d'électricité ce mois-ci. Le CCAS peut-il m'aider ?",
    },
    {
        "id": "SUPPORT_SECU",
        "type": "Support (RAG)",
        "subject": "Nuisances sonores bar",
        "sender": "voisin.fatigue@dsiatlantic.com",
        "body": "Le bar en bas de chez moi met la musique à fond tous les soirs jusqu'à 2h du matin. Que peut faire la police municipale ?",
    },
    {
        "id": "SUPPORT_ELEC",
        "type": "Support (RAG)",
        "subject": "Procuration élections",
        "sender": "electeur.absent@dsiatlantic.com.com",
        "body": "Je serai en vacances lors du prochain scrutin. Comment puis-je donner procuration à mon frère ?",
    },
    {
        "id": "SUPPORT_HORS_SUJET",
        "type": "Support (RAG)",
        "subject": "Recette de cuisine",
        "sender": "citoyen.curieux@dsiatlantic.com",
        "body": "Bonjour, pouvez-vous me donner la vraie recette des crêpes bretonnes s'il vous plaît ?",
    },
    {
        "id": "SUPPORT_CONVERSATION",
        "type": "Support (RAG)",
        "subject": "Re: Demande de PLU",
        "sender": "citoyen.urba@dsiatlantic.com",
        "body": "Merci pour la réponse sur l'abri de jardin. Et pour une piscine, c'est quoi la limite de taille avant de devoir faire un permis ?",
    },
]
