import logging
import os
import textwrap
import requests

logger = logging.getLogger(__name__)

# Check if we should use LiteLLM Gateway
_USE_LLM_GATEWAY = os.getenv("LLM_PROVIDER", "lmstudio").lower() not in ("lmstudio", "")


class SupportQAService:
    """
    Service de réécriture des emails de support en fiches Q/R structurées.
    Utilise LM Studio ou LiteLLM Gateway selon la configuration.
    """

    def __init__(self, config):
        self.config = config
        self.prompt = self.config.load_prompt(self.config.support_qa_prompt_file)
        if not self.prompt:
            logger.warning(
                "Aucun prompt support QA trouvé, utilisation du prompt par défaut embarqué."
            )
            self.prompt = self._default_prompt()
        
        # Initialize LLM Client for gateway providers
        self.llm_client = None
        if _USE_LLM_GATEWAY:
            from services.llm_client import get_llm_client
            self.llm_client = get_llm_client(config)
            logger.info(f"LLMClient initialisé pour SupportQA (provider: {os.getenv('LLM_PROVIDER')})")

    def rewrite_to_qa(self, subject: str, sender: str, raw_body: str) -> str:
        """
        Transforme un email brut de support en contenu Q/R structuré.

        Args:
            subject: Sujet de l'email
            sender: Adresse de l'expéditeur (ex: support@...)
            raw_body: Corps complet de l'email (y compris historique)

        Returns:
            Texte Q/R structuré (string)
        """
        subject = subject or ""
        sender = sender or ""
        raw_body = raw_body or ""

        logger.debug("SupportQAService.rewrite_to_qa appelé.")

        user_content = textwrap.dedent(
            f"""
        Tu reçois ci-dessous un email de support complet, avec éventuellement un historique
        de messages entre un client et un agent.

        Métadonnées :
        - Sujet original : {subject}
        - Expéditeur (dernier agent ou relai) : {sender}

        Contenu complet de l'email :

        \"\"\"EMAIL_BRUT_DE_SUPPORT
        {raw_body}
        \"\"\"EMAIL_BRUT_DE_SUPPORT_FIN

        Ta tâche est de produire une fiche Q/R structurée.
        Suis strictement les instructions fournies dans ton prompt système (structure Q/R).
        N'invente aucune information absente de l'email.
        """
        ).strip()

        messages = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            logger.info("🧠 Envoi de l'email de support au LLM pour réécriture Q/R...")
            
            content = self._call_llm(
                messages=messages,
                temperature=self.config.support_qa_temperature,
                max_tokens=self.config.support_qa_max_tokens,
            )
            
            logger.info("✅ Réécriture Q/R support reçue.")
            return content

        except Exception as e:
            logger.error(
                f"❌ Erreur lors de la réécriture Q/R support : {e}", exc_info=True
            )
            raise

    def _default_prompt(self) -> str:
        """
        Prompt système par défaut pour la réécriture Q/R,
        utilisé si SUPPORT_QA_PROMPT_FILE est absent.
        """
        return textwrap.dedent(
            """
        Tu es un assistant qui transforme des emails de support client en fiches Q/R exploitables
        par un système RAG.

        RÈGLES GÉNÉRALES :
        - Réponds toujours en français.
        - N'invente aucune information.
        - Tu dois t'appuyer uniquement sur le contenu de l'email fourni.
        - Si un élément est manquant ou ambigu, écris : "Je ne sais pas".
        - Anonymise les données personnelles (noms, emails, numéros) en les remplaçant par :
          [CLIENT], [AGENT], [EMAIL], [ID_CLIENT], etc.

        FORMAT DE SORTIE EXACT (en texte brut) :

        Type : QA_SUPPORT
        Sujet : <sujet synthétique de la question client>
        Date : <date si identifiable dans l'email, sinon "Je ne sais pas">

        QUESTION_CLIENT :
        <reformulation claire et fidèle de la dernière question du client>

        RÉPONSE_FOURNIE :
        <réponse fournie par l'agent, clarifiée si besoin, sans ajouter de nouveaux engagements>

        CONTEXTE_SUPPLÉMENTAIRE :
        <liste des conditions, restrictions, cas particuliers s'ils existent, sinon "Aucun contexte supplémentaire.">

        IMPORTANT :
        - Si l'email ne contient pas de question claire, explique-le dans QUESTION_CLIENT.
        - Si aucune réponse de l'agent n'est présente, indique-le dans RÉPONSE_FOURNIE.
        - Ne change pas la structure des sections.
        """
        ).strip()

    def generate_email_summary(
        self, subject: str, cleaned_body: str, max_sentences: int = 3
    ) -> str:
        """
        Génère un résumé court et concis d'un email (2-3 phrases maximum).

        Args:
            subject: Sujet de l'email
            cleaned_body: Corps de l'email nettoyé
            max_sentences: Nombre maximum de phrases (défaut: 3)

        Returns:
            str: Résumé de l'email (2-3 phrases)
        """
        logger.debug("SupportQAService.generate_email_summary appelé.")

        system_prompt = textwrap.dedent(
            f"""
        Tu es un assistant qui génère des résumés concis d'emails.

        RÈGLES :
        - Maximum {max_sentences} phrases courtes
        - Français uniquement
        - Identifier : sujet principal, action requise (si applicable), informations clés
        - Ton neutre et professionnel
        - Pas de fioriture, aller droit au but
        - Ne pas commencer par "Cet email..." ou "Le message..."

        FORMAT DE SORTIE (texte brut uniquement) :
        [Résumé en {max_sentences} phrases maximum]
        """
        ).strip()

        user_content = textwrap.dedent(
            f"""
        Résume cet email en maximum {max_sentences} phrases.

        Sujet : {subject or "Sans sujet"}

        Corps :
        {cleaned_body or "Aucun contenu"}
        """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            logger.info("📝 Génération résumé court de l'email...")
            
            summary = self._call_llm(
                messages=messages,
                temperature=0.1,
                max_tokens=self.config.summary_max_tokens,
            ).strip()
            
            logger.info(f"✅ Résumé généré : {summary[:50]}...")
            return summary

        except Exception as e:
            logger.error(
                f"❌ Erreur lors de la génération du résumé : {e}", exc_info=True
            )
            raise

    def analyze_document_intelligence(
        self, subject: str, cleaned_body: str
    ) -> dict:
        """
        Extrait l'intelligence documentaire d'un email (Résumé, Score, Type).

        Returns:
            dict: {
                "summary": str,
                "business_value_score": int (1-5),
                "document_type": str
            }
        """
        import json
        logger.debug("SupportQAService.analyze_document_intelligence appelé.")

        system_prompt = textwrap.dedent(
            """
        Tu es un expert en gestion documentaire. Ton rôle est d'analyser cet email et de l'indexer.
        
        RÈGLES :
        - 'summary': Résume cet email en 2 phrases courtes et précises.
        - 'business_value_score': Un entier entre 1 et 5.
            5 = Document de référence officiel, procédure métier, arrêté
            4 = Information importante, décision, note interne majeure
            3 = Résolution de problème technique, discussion informative
            2 = Échange courant, conversation métier sans grande valeur de référence
            1 = Bruit, spam, remerciement, e-mail éphémère (ex: "Ok on se voit à 14h")
        - 'document_type': Choisis exactement UNE catégorie parmi : PROCEDURE, DECISION, DISCUSSION, INFORMATIF, BRUIT, AUTRE.

        FORMAT DE SORTIE :
        Tu dois répondre UNIQUEMENT avec un objet JSON valide, sans markdown, avec la structure stricte suivante :
        {
          "summary": "...",
          "business_value_score": 3,
          "document_type": "DISCUSSION"
        }
        """
        ).strip()

        user_content = textwrap.dedent(
            f"""
        Analyse ce document :

        Sujet : {subject or "Sans sujet"}

        Corps :
        {cleaned_body or "Aucun contenu"}
        """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            logger.info("🧠 Extraction de l'intelligence documentaire (Qualité Métier)...")
            
            response = self._call_llm(
                messages=messages,
                temperature=0.1,
                max_tokens=self.config.summary_max_tokens,
                response_format={"type": "json_object"}
            ).strip()
            
            # Clean possible markdown formatting
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
                
            result = json.loads(response.strip())
            
            # Validation minimale
            score = int(result.get("business_value_score", 3))
            doc_type = str(result.get("document_type", "AUTRE")).upper()
            summary = str(result.get("summary", ""))
            
            logger.info(f"✅ Intelligence documentaire extraite : Score={score}/5, Type={doc_type}")
            return {
                "summary": summary,
                "business_value_score": score,
                "document_type": doc_type
            }

        except Exception as e:
            logger.error(
                f"❌ Erreur lors de l'extraction de l'intelligence documentaire : {e}", exc_info=True
            )
            # Fallback sûr vers le résumé simple
            return {
                "summary": self.generate_email_summary(subject, cleaned_body),
                "business_value_score": 3,
                "document_type": "AUTRE"
            }

    def _call_llm(self, messages: list, temperature: float, max_tokens: int, response_format: dict = None) -> str:
        """
        Méthode centralisée pour appeler le LLM (Gateway ou LM Studio).
        Respecte le principe DRY.
        """
        if self.llm_client:
            kwargs = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": self.config.llm_timeout,
            }
            # Add response_format if provided and supported by LLMClient wrapper
            if response_format:
                # Assuming the LLMClient handles **kwargs passing for OpenAI compatibility
                kwargs["response_format"] = response_format
                
            return self.llm_client.chat(**kwargs)
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.ai_api_key}",
            }
            payload = {
                "model": self.config.ai_model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                payload["response_format"] = response_format
                
            resp = requests.post(
                self.config.ai_api_url,
                headers=headers,
                json=payload,
                timeout=self.config.llm_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
