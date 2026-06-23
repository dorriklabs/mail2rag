import json
import logging
import textwrap
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class FeedbackAnalyzerService:
    """
    Service analysant les écarts entre les suggestions de l'IA et les corrections des agents.
    Il génère et maintient à jour une liste dynamique de règles métiers pour chaque workspace.
    """
    
    def __init__(self, config, state_dir: Path, log_dir: Path, support_qa_service):
        self.config = config
        self.log_file = log_dir / "feedback_loop.jsonl"
        self.rules_file = log_dir / "dynamic_rules.json"
        self.state_file = state_dir / "analyzer_state.json"
        self.support_qa_service = support_qa_service

    def _load_state(self) -> int:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f).get("last_processed_line", 0)
            except Exception:
                return 0
        return 0

    def _save_state(self, line_index: int):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump({"last_processed_line": line_index}, f)

    def _load_rules(self) -> Dict[str, List[str]]:
        if self.rules_file.exists():
            try:
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_rules(self, rules: Dict[str, List[str]]):
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rules_file, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)

    def process_new_feedbacks(self):
        if not self.log_file.exists():
            logger.info("Aucun log de feedback trouvé.")
            return

        last_line = self._load_state()
        rules_by_workspace = self._load_rules()
        current_line = 0
        has_changes = False

        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                current_line += 1
                if current_line <= last_line:
                    continue
                
                try:
                    entry = json.loads(line.strip())
                    workspace = entry.get("metadata", {}).get("workspace", "default")
                    question = entry.get("question", "")
                    ai_suggestion = entry.get("ai_suggestion", "")
                    agent_reply = entry.get("agent_reply", "")
                    
                    if not agent_reply or not ai_suggestion:
                        continue
                        
                    current_rules = rules_by_workspace.get(workspace, [])
                    logger.info(f"🔍 Analyse d'un feedback pour le workspace '{workspace}' (Ligne {current_line})")
                    
                    new_rules = self._analyze_feedback(workspace, question, ai_suggestion, agent_reply, current_rules)
                    
                    if new_rules is not None and new_rules != current_rules:
                        rules_by_workspace[workspace] = new_rules
                        has_changes = True
                        logger.info(f"✅ Règles mises à jour pour '{workspace}' ({len(new_rules)} règles actives)")
                    else:
                        logger.info(f"ℹ️ Aucune nouvelle règle métier pertinente détectée pour '{workspace}'")
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'analyse du feedback ligne {current_line}: {e}")

        if has_changes:
            self._save_rules(rules_by_workspace)
            
        self._save_state(current_line)
        logger.info(f"Analyse des feedbacks terminée (Lignes traitées: {current_line - last_line}).")

    def _analyze_feedback(self, workspace: str, question: str, ai_suggestion: str, agent_reply: str, current_rules: List[str]) -> Optional[List[str]]:
        system_prompt = textwrap.dedent(
            """
            Tu es un superviseur expert de la qualité du support client. Ton rôle est d'analyser l'écart entre la suggestion d'une IA et la réponse finale corrigée par un agent humain.
            
            L'agent humain a-t-il corrigé une erreur de procédure, une hallucination, ou une information manquante cruciale ? 
            Si la différence est UNIQUEMENT liée au style, à la reformulation, ou à la politesse, retourne EXACTEMENT la liste des règles actuelles sans modification.
            
            Si l'agent a apporté une vraie correction métier :
            1. Déduis une règle stricte, concise et impérative (ex: "Ne jamais faire X", "Toujours vérifier Y").
            2. Intègre cette nouvelle règle à la liste existante.
            3. Fusionne les règles si elles se ressemblent ou s'annulent.
            4. La liste finale ne doit JAMAIS dépasser 10 règles. Conserve uniquement les plus critiques.
            
            FORMAT DE SORTIE (JSON STRICT) :
            {
                "rules": [
                    "Règle 1...",
                    "Règle 2..."
                ]
            }
            """
        ).strip()
        
        rules_text = "\n".join([f"- {r}" for r in current_rules]) if current_rules else "Aucune règle existante."

        user_content = textwrap.dedent(
            f"""
            Workspace : {workspace}
            
            QUESTION CLIENT :
            {question}
            
            SUGGESTION IA ORIGINALE :
            {ai_suggestion}
            
            REPONSE FINALE AGENT HUMAIN :
            {agent_reply}
            
            REGLES EXISTANTES POUR CE WORKSPACE :
            {rules_text}
            
            Mets à jour la liste des règles au format JSON strict.
            """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = self.support_qa_service._call_llm(
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"}
            ).strip()

            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]

            result = json.loads(response.strip())
            rules = result.get("rules", current_rules)
            
            if isinstance(rules, list):
                # Ensure max 10 rules
                rules = [str(r).strip() for r in rules if str(r).strip()]
                return rules[:10]
                
            return current_rules

        except Exception as e:
            logger.error(f"Erreur LLM lors de l'analyse du feedback: {e}")
            return None
