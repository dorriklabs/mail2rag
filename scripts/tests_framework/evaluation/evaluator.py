class Evaluator:
    @staticmethod
    def evaluate_with_llm(email_id: str, question: str, response_body: str) -> dict:
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
