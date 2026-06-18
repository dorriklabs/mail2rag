import os
import json
import requests

class Evaluator:
    @staticmethod
    def evaluate_with_llm(email_id: str, question: str, response_body: str) -> dict:
        """Évalue la réponse générée en l'envoyant au LLM pour agir comme juge."""
        try:
            answer_lower = response_body.lower()
            
            # 1. Détection rapide des échecs évidents (garde-fou)
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
                
            # 2. Critères attendus (déclaratif)
            expected_concepts = {
                "SUPPORT_URBA": "La réponse doit mentionner une limite de surface de 20m2 (ou équivalent) et la nécessité d'une déclaration préalable.",
                "SUPPORT_VOIRIE": "La réponse doit mentionner un délai de 48h (ou 2 jours) et l'intervention des services techniques.",
                "SUPPORT_EC_1": "La réponse doit indiquer que la démarche se fait sur le portail citoyen (ou en ligne) avec un délai de 2 semaines.",
                "SUPPORT_EC_2": "La réponse doit indiquer que la demande se fait par courrier et rediriger vers service-public.fr.",
                "SUPPORT_ENF_1": "La réponse doit mentionner l'obligation de fournir un justificatif de domicile et contacter le service enfance.",
                "SUPPORT_ENF_2": "La réponse doit mentionner la date butoir du 30 avril et la nécessité de remplir un dossier/formulaire.",
                "SUPPORT_VOIRIE2": "La réponse doit préciser que le ramassage se fait le jeudi matin pour la zone concernée (zone nord).",
                "SUPPORT_ASSO": "La réponse doit indiquer qu'il faut faire la demande un mois à l'avance.",
                "SUPPORT_SOCIAL_1": "La réponse doit mentionner de remplir un formulaire/cerfa et de s'adresser à la mairie ou au CCAS.",
                "SUPPORT_SOCIAL_2": "La réponse doit proposer une aide financière/ponctuelle du CCAS et suggérer un rendez-vous avec une assistante sociale.",
                "SUPPORT_SECU": "La réponse doit mentionner la limite de 22h, caractériser la situation de tapage nocturne/nuisances, et avertir d'une contravention/verbalisation de la police.",
                "SUPPORT_ELEC": "La réponse doit rediriger vers le commissariat/police/gendarmerie avec une pièce d'identité.",
                "SUPPORT_HORS_SUJET": "La réponse doit poliment refuser de répondre ou indiquer qu'elle n'a pas l'information dans sa base de connaissances, sans inventer de recette.",
                "SUPPORT_CONVERSATION": "La réponse doit mentionner que pour une piscine, le permis de construire est obligatoire si le bassin excède 20m2."
            }
            
            if email_id not in expected_concepts:
                return {"note": "8/10", "remarque": "Réponse pertinente générée (Pas de critères stricts)."}

            criteria = expected_concepts[email_id]
            
            # 3. Appel au LLM-as-a-judge
            lm_studio_url = os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234").rstrip("/")
            url = f"{lm_studio_url}/v1/chat/completions"
            
            system_prompt = (
                "Tu es un évaluateur qualité intransigeant spécialisé dans le contrôle de réponses de support technique. "
                "Tu dois vérifier si la réponse fournie respecte les critères exigés. "
                "Tu DOIS retourner UNIQUEMENT un objet JSON valide, sans bloc de code markdown, avec cette structure exacte : "
                '{"note": "X/10", "remarque": "Ton explication concise"}. '
                "Pour la note : Mets 10/10 si TOUS les critères sont présents (même formulés différemment). "
                "Mets 7/10 s'il manque un critère. Mets 4/10 ou moins si les critères principaux sont absents."
            )
            
            user_prompt = (
                f"Question de l'utilisateur : {question}\n\n"
                f"Réponse générée à évaluer : {response_body}\n\n"
                f"Critères obligatoires : {criteria}\n\n"
                "Rappel : Renvoie uniquement le JSON valide."
            )
            
            payload = {
                "model": "qwen2.5-7b-instruct", # Utilisé de manière générique, LM Studio l'ignore souvent
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.0,
                "max_tokens": 150
            }
            
            try:
                # Timeout de 30s pour ne pas bloquer les tests indéfiniment
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    
                    # Nettoyage d'éventuels blocs de code markdown (ex: ```json ... ```)
                    if content.startswith("```json"):
                        content = content.replace("```json", "", 1)
                    if content.startswith("```"):
                        content = content.replace("```", "", 1)
                    if content.endswith("```"):
                        content = content[:content.rfind("```")]
                    content = content.strip()
                    
                    result_dict = json.loads(content)
                    
                    # Validation du format
                    note = result_dict.get("note", "N/A")
                    remarque = result_dict.get("remarque", "Pas de remarque.")
                    
                    if "/10" not in str(note):
                        note = f"{note}/10"
                        
                    return {"note": note, "remarque": remarque}
                else:
                    return {"note": "N/A", "remarque": f"Erreur API Juge: HTTP {resp.status_code}"}
            except requests.exceptions.RequestException as e:
                return {"note": "N/A", "remarque": f"Erreur connexion Juge: {str(e)}"}
            except json.JSONDecodeError:
                return {"note": "N/A", "remarque": "Erreur Juge: Le format JSON renvoyé est invalide."}
            
        except Exception as e:
            return {"note": "N/A", "remarque": f"Erreur interne éval: {str(e)}"}
