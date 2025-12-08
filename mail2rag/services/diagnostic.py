"""
DiagnosticService - Mode de test complet avec trace du pipeline.

Déclenché par un email avec sujet "test : all" ou "TEST:DIAG".
Trace toutes les étapes du processus d'ingestion et retourne un rapport HTML.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import Config
from models import ParsedEmail
from services.mail import MailService
from services.ragproxy_client import RAGProxyClient
from services.processor import DocumentProcessor
from services.email_renderer import EmailRenderer
from services.tika_client import TikaClient

logger = logging.getLogger(__name__)


@dataclass
class TraceStep:
    """Une étape tracée du diagnostic."""
    name: str
    status: str = "pending"  # pending, running, success, error
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class DiagnosticTrace:
    """
    Collecteur de traces pour le diagnostic.
    
    Usage:
        trace = DiagnosticTrace()
        with trace.step("tika_extraction") as step:
            result = tika.extract(...)
            step.details["pages"] = result.pages
    """
    
    def __init__(self):
        self.steps: List[TraceStep] = []
        self.global_start: float = time.time()
        self.metadata: Dict[str, Any] = {
            "started_at": datetime.now().isoformat(),
        }
    
    def step(self, name: str) -> "TraceStepContext":
        """Crée un contexte pour une étape tracée."""
        trace_step = TraceStep(name=name)
        self.steps.append(trace_step)
        return TraceStepContext(trace_step)
    
    def add_metadata(self, key: str, value: Any) -> None:
        """Ajoute des métadonnées globales."""
        self.metadata[key] = value
    
    @property
    def total_duration_ms(self) -> int:
        """Durée totale en millisecondes."""
        return int((time.time() - self.global_start) * 1000)
    
    @property
    def all_success(self) -> bool:
        """True si toutes les étapes ont réussi."""
        return all(s.status == "success" for s in self.steps)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export pour le template HTML."""
        return {
            "metadata": self.metadata,
            "total_duration_ms": self.total_duration_ms,
            "all_success": self.all_success,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "details": s.details,
                    "error": s.error,
                }
                for s in self.steps
            ],
        }


class TraceStepContext:
    """Context manager pour une étape de trace."""
    
    def __init__(self, step: TraceStep):
        self.step = step
    
    def __enter__(self) -> TraceStep:
        self.step.status = "running"
        self.step.start_time = time.time()
        return self.step
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.step.end_time = time.time()
        self.step.duration_ms = int((self.step.end_time - self.step.start_time) * 1000)
        
        if exc_type is not None:
            self.step.status = "error"
            self.step.error = str(exc_val)
            return False  # Re-raise exception
        
        self.step.status = "success"
        return False


class DiagnosticService:
    """
    Service de diagnostic complet du pipeline Mail2RAG.
    
    Exécute un test end-to-end et génère un rapport détaillé.
    """
    
    def __init__(
        self,
        config: Config,
        logger,
        mail_service: MailService,
        ragproxy_client: RAGProxyClient,
        processor: DocumentProcessor,
        email_renderer: EmailRenderer,
        tika_client: TikaClient,
        get_secure_id: Callable[[int], str],
    ):
        self.config = config
        self.logger = logger
        self.mail = mail_service
        self.ragproxy = ragproxy_client
        self.processor = processor
        self.renderer = email_renderer
        self.tika = tika_client
        self.get_secure_id = get_secure_id
    
    def run_diagnostic(self, email: ParsedEmail) -> None:
        """
        Exécute le diagnostic complet et envoie le rapport par email.
        
        Args:
            email: Email contenant la PJ à tester et optionnellement une question
        """
        self.logger.info(f"🔬 Démarrage diagnostic pour UID {email.uid}")
        
        trace = DiagnosticTrace()
        trace.add_metadata("email_uid", email.uid)
        trace.add_metadata("sender", email.sender)
        trace.add_metadata("subject", email.subject)
        
        question = self._extract_question(email.body)
        has_question = bool(question)
        trace.add_metadata("has_question", has_question)
        if question:
            trace.add_metadata("question", question)
        
        # Variables pour les résultats
        chunks_created = 0
        rag_answer = None
        rag_sources = []
        
        # Extraire les pièces jointes du message brut
        attachments = self._extract_attachments(email)
        
        try:
            # 1. Réception et parsing
            with trace.step("email_reception") as step:
                step.details["attachments_count"] = len(attachments)
                step.details["body_length"] = len(email.body or "")
                if attachments:
                    step.details["attachments"] = [
                        {"name": a["name"], "size_bytes": len(a["content"])}
                        for a in attachments
                    ]
            
            # 2. Vérification présence PJ
            if not attachments:
                trace.metadata["error"] = "Aucune pièce jointe fournie"
                self._send_report(email, trace, None, None)
                return
            
            # 3. Extraction texte via Tika (première PJ)
            attachment = attachments[0]
            extracted_text = ""
            
            with trace.step("tika_extraction") as step:
                step.details["filename"] = attachment["name"]
                step.details["content_type"] = attachment.get("content_type", "unknown")
                step.details["size_bytes"] = len(attachment["content"])
                
                result = self.tika.extract_text_from_bytes(attachment["content"])
                extracted_text = result or ""
                
                step.details["extracted_chars"] = len(extracted_text)
            
            # 4. Chunking et ingestion via RAG Proxy
            if extracted_text:
                with trace.step("ragproxy_ingestion") as step:
                    # Collection de test temporaire
                    test_collection = f"diag-{email.uid}"
                    step.details["collection"] = test_collection
                    
                    # Ingestion
                    ingest_result = self.ragproxy.ingest(
                        collection=test_collection,
                        text=extracted_text,
                        metadata={
                            "source": "diagnostic",
                            "filename": attachment.name,
                            "uid": str(email.uid),
                        }
                    )
                    
                    chunks_created = ingest_result.get("chunks_created", 0)
                    step.details["chunks_created"] = chunks_created
                    step.details["status"] = ingest_result.get("status", "unknown")
                
                # 5. Test RAG si question posée
                if has_question and chunks_created > 0:
                    with trace.step("rag_search") as step:
                        step.details["query"] = question[:100]
                        
                        search_result = self.ragproxy.search(
                            query=question,
                            workspace=test_collection,
                            top_k=10,
                            final_k=3,
                        )
                        
                        chunks = search_result.get("chunks", [])
                        step.details["chunks_found"] = len(chunks)
                        if chunks:
                            step.details["top_score"] = round(chunks[0].get("score", 0), 3)
                        rag_sources = chunks
                    
                    # 6. Génération réponse LLM
                    with trace.step("llm_generation") as step:
                        chat_result = self.ragproxy.chat(
                            query=question,
                            collection=test_collection,
                        )
                        
                        rag_answer = chat_result.get("answer", "")
                        step.details["answer_length"] = len(rag_answer)
                        step.details["sources_count"] = len(chat_result.get("sources", []))
                
                # 7. Nettoyage : suppression de la collection de test
                with trace.step("cleanup") as step:
                    try:
                        # On ne supprime pas directement, on note juste
                        step.details["test_collection"] = test_collection
                        step.details["action"] = "La collection de test peut être supprimée manuellement"
                    except Exception as e:
                        step.details["warning"] = str(e)
            
            else:
                trace.metadata["warning"] = "Aucun texte extrait du document"
        
        except Exception as e:
            self.logger.error(f"Erreur diagnostic: {e}", exc_info=True)
            trace.metadata["fatal_error"] = str(e)
        
        # Envoi du rapport
        self._send_report(email, trace, rag_answer, rag_sources)
    
    def _extract_attachments(self, email: ParsedEmail) -> List[Dict[str, Any]]:
        """
        Extrait les pièces jointes d'un email.
        
        Returns:
            Liste de dicts avec name, content, content_type
        """
        attachments = []
        msg = email.msg
        
        if not msg or not msg.is_multipart():
            return []
        
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            
            filename = part.get_filename()
            if not filename:
                continue
            
            content = part.get_payload(decode=True)
            if content:
                attachments.append({
                    "name": filename,
                    "content": content,
                    "content_type": part.get_content_type(),
                })
        
        return attachments
    
    def _extract_question(self, body: str) -> Optional[str]:
        """Extrait la question du corps de l'email."""
        if not body:
            return None
        
        # Nettoyer le corps
        lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
        
        # Ignorer les lignes de signature ou trop courtes
        for line in lines:
            if len(line) > 10 and "?" in line:
                return line
            if len(line) > 20:
                return line
        
        return lines[0] if lines else None
    
    def _send_report(
        self,
        email: ParsedEmail,
        trace: DiagnosticTrace,
        rag_answer: Optional[str],
        rag_sources: Optional[List[Dict]],
    ) -> None:
        """Génère et envoie le rapport HTML."""
        try:
            html_content = self._render_report(trace, rag_answer, rag_sources)
            
            subject = f"📊 Rapport Diagnostic - {'✅ OK' if trace.all_success else '⚠️ Partiel'}"
            
            self.mail.send_reply(
                to_email=email.sender,
                subject=subject,
                body=html_content,
                is_html=True,
            )
            
            self.logger.info(f"📧 Rapport diagnostic envoyé à {email.sender}")
            
        except Exception as e:
            self.logger.error(f"Échec envoi rapport: {e}", exc_info=True)
    
    def _render_report(
        self,
        trace: DiagnosticTrace,
        rag_answer: Optional[str],
        rag_sources: Optional[List[Dict]],
    ) -> str:
        """Génère le HTML du rapport."""
        data = trace.to_dict()
        
        # Ajouter réponse RAG si présente
        if rag_answer:
            data["rag_answer"] = rag_answer
        if rag_sources:
            data["rag_sources"] = rag_sources[:3]  # Top 3 sources
        
        # Utiliser un template simple ou inline HTML
        return self._generate_html_report(data)
    
    def _generate_html_report(self, data: Dict[str, Any]) -> str:
        """Génère le HTML du rapport de diagnostic."""
        steps_html = ""
        for step in data["steps"]:
            icon = "✅" if step["status"] == "success" else "❌" if step["status"] == "error" else "⏳"
            
            details_html = ""
            if step["details"]:
                details_items = [f"<li><strong>{k}:</strong> {v}</li>" for k, v in step["details"].items()]
                details_html = f"<ul style='margin: 5px 0; padding-left: 20px;'>{''.join(details_items)}</ul>"
            
            error_html = ""
            if step["error"]:
                error_html = f"<div style='color: #dc3545; margin-top: 5px;'>❌ {step['error']}</div>"
            
            steps_html += f"""
            <div style="margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid {'#28a745' if step['status'] == 'success' else '#dc3545' if step['status'] == 'error' else '#6c757d'};">
                <div style="font-weight: bold;">{icon} {step['name'].replace('_', ' ').title()}</div>
                <div style="color: #6c757d; font-size: 0.9em;">Durée: {step['duration_ms']}ms</div>
                {details_html}
                {error_html}
            </div>
            """
        
        # Réponse RAG si présente
        rag_html = ""
        if data.get("rag_answer"):
            sources_html = ""
            if data.get("rag_sources"):
                sources_items = [
                    f"<li><em>Score: {s.get('score', 0):.2f}</em> - {s.get('text', '')[:100]}...</li>"
                    for s in data["rag_sources"]
                ]
                sources_html = f"<ul>{''.join(sources_items)}</ul>"
            
            rag_html = f"""
            <div style="margin-top: 20px; padding: 15px; background: #e7f3ff; border-radius: 5px;">
                <h3 style="margin-top: 0;">💬 Réponse RAG</h3>
                <p>{data['rag_answer']}</p>
                <h4>📚 Sources utilisées</h4>
                {sources_html}
            </div>
            """
        
        # Métadonnées
        meta = data["metadata"]
        meta_html = f"""
        <div style="margin-bottom: 20px;">
            <strong>Email UID:</strong> {meta.get('email_uid', 'N/A')}<br>
            <strong>Expéditeur:</strong> {meta.get('sender', 'N/A')}<br>
            <strong>Date:</strong> {meta.get('started_at', 'N/A')}<br>
        </div>
        """
        
        # Erreurs globales
        error_global = ""
        if meta.get("error") or meta.get("fatal_error") or meta.get("warning"):
            msg = meta.get("fatal_error") or meta.get("error") or meta.get("warning")
            color = "#dc3545" if "error" in str(meta.keys()) else "#ffc107"
            error_global = f"""
            <div style="padding: 10px; background: {color}20; border-left: 4px solid {color}; margin-bottom: 20px;">
                ⚠️ {msg}
            </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; }}
            </style>
        </head>
        <body>
            <h1>📊 Rapport de Diagnostic Mail2RAG</h1>
            
            {meta_html}
            {error_global}
            
            <h2>⏱️ Durée totale: {data['total_duration_ms']}ms</h2>
            
            <h2>📋 Étapes du Pipeline</h2>
            {steps_html}
            
            {rag_html}
            
            <hr style="margin-top: 30px;">
            <p style="color: #6c757d; font-size: 0.9em;">
                Généré automatiquement par Mail2RAG Diagnostic Mode
            </p>
        </body>
        </html>
        """
