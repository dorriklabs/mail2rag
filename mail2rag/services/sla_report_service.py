import logging
import pandas as pd
import requests
from typing import TYPE_CHECKING, Tuple, Optional
from email.message import EmailMessage
from datetime import datetime

if TYPE_CHECKING:
    from config import Config
    from services.mail import MailService
    from services.sla_service import SlaService

logger = logging.getLogger(__name__)

class SlaReportService:
    def __init__(
        self,
        config: "Config",
        logger_instance: logging.Logger,
        mail_service: "MailService",
        sla_service: "SlaService"
    ):
        self.config = config
        self.logger = logger_instance
        self.mail_service = mail_service
        self.sla_service = sla_service

    def _get_sla_data(self) -> pd.DataFrame:
        import sqlite3
        try:
            conn = sqlite3.connect(self.sla_service.db_path)
            query = "SELECT thread_id, sender, subject, target_service, dispatched_at, replied_at, response_time_hours, status FROM dispatch_sla ORDER BY dispatched_at DESC"
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            df['dispatched_at'] = pd.to_datetime(df['dispatched_at'])
            df['replied_at'] = pd.to_datetime(df['replied_at'])
            return df
        except Exception as e:
            self.logger.error("Erreur _get_sla_data : %s", e)
            return pd.DataFrame()

    def _generate_ai_summary(self, total_pending: int, avg_response: float, critical_count: int, top_critical_service: str) -> str:
        if not self.config.ai_api_url:
            return ""
            
        prompt = (
            "Tu es l'assistant de direction (IA) de la mairie/entreprise. "
            "Rédige un court paragraphe (2-3 phrases) de synthèse poli et exécutif à l'attention de la Direction pour résumer l'état des temps de réponse (SLA).\n"
            f"Faits actuels :\n"
            f"- {total_pending} e-mails citoyens sont actuellement en attente de réponse des services.\n"
            f"- Le temps moyen de réponse est de {avg_response:.1f} heures.\n"
            f"- Il y a {critical_count} e-mails en souffrance depuis plus de 48h (Urgence absolue).\n"
            f"- Le service avec le plus d'urgences est : {top_critical_service if top_critical_service else 'Aucun'}.\n\n"
            "Sois concis, professionnel et direct. Ne mets pas d'objet ni de signature."
        )
        
        try:
            payload = {
                "model": self.config.ai_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 150,
            }
            resp = requests.post(
                self.config.llm_api_url,
                json=payload,
                timeout=self.config.llm_timeout,
                headers={"Authorization": f"Bearer {self.config.ai_api_key}"}
            )
            if resp.ok:
                data = resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            self.logger.error("Erreur génération AI summary: %s", e)
        return ""

    def generate_html_report(self) -> Tuple[str, Optional[bytes]]:
        df = self._get_sla_data()
        if df.empty:
            return "<p>Aucune donnée SLA n'est disponible.</p>", None
            
        pending_df = df[df['status'] == 'PENDING'].copy()
        replied_df = df[df['status'] == 'REPLIED'].copy()

        now = datetime.utcnow()
        if not pending_df.empty:
            pending_df['delay_hours'] = (now - pending_df['dispatched_at']).dt.total_seconds() / 3600.0
        else:
            pending_df['delay_hours'] = []

        total_pending = len(pending_df)
        avg_response = replied_df['response_time_hours'].mean() if not replied_df.empty else 0.0
        critical_df = pending_df[pending_df['delay_hours'] > 48].sort_values(by='delay_hours', ascending=False)
        critical_count = len(critical_df)
        top_critical_service = critical_df['target_service'].value_counts().idxmax() if not critical_df.empty else ""

        # 1. Executive Summary IA
        ai_summary = self._generate_ai_summary(total_pending, avg_response, critical_count, top_critical_service)
        
        # 2. Construction du CSV
        csv_bytes = df.to_csv(index=False).encode('utf-8')
        
        # 3. HTML Report
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <h2 style="color: #2c3e50;">📊 Rapport SLA & Délais de Réponse</h2>
        """
        
        if ai_summary:
            html += f"""
            <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin-bottom: 20px;">
                <strong>💡 Synthèse de l'IA :</strong><br/>
                {ai_summary}
            </div>
            """
            
        html += f"""
            <h3>Indicateurs Clés</h3>
            <ul>
                <li><strong>E-mails en attente :</strong> {total_pending}</li>
                <li><strong>Temps de réponse moyen :</strong> {avg_response:.1f} h</li>
                <li><strong>Dossiers critiques (>48h) :</strong> <span style="color: {'red' if critical_count > 0 else 'green'}; font-weight: bold;">{critical_count}</span></li>
            </ul>
        """
        
        if not critical_df.empty:
            html += "<h3>🚨 Dossiers Critiques (Top 10)</h3>"
            html += "<table style='width: 100%; border-collapse: collapse;'>"
            html += "<tr><th style='border: 1px solid #ddd; padding: 8px; text-align: left; background-color: #f2f2f2;'>Service</th>"
            html += "<th style='border: 1px solid #ddd; padding: 8px; text-align: left; background-color: #f2f2f2;'>Citoyen</th>"
            html += "<th style='border: 1px solid #ddd; padding: 8px; text-align: left; background-color: #f2f2f2;'>En attente depuis</th></tr>"
            
            for _, row in critical_df.head(10).iterrows():
                html += "<tr>"
                html += f"<td style='border: 1px solid #ddd; padding: 8px;'>{row['target_service']}</td>"
                html += f"<td style='border: 1px solid #ddd; padding: 8px;'>{row['sender']}</td>"
                html += f"<td style='border: 1px solid #ddd; padding: 8px; color: red;'>{row['delay_hours']:.1f} h</td>"
                html += "</tr>"
            html += "</table>"
            
        html += """
            <p style="margin-top: 30px; font-size: 0.9em; color: #666;">
                <i>Le rapport complet est attaché en format CSV. Pour consulter tous les détails, veuillez vous rendre sur le Dashboard Streamlit.</i>
            </p>
        </body>
        </html>
        """
        return html, csv_bytes

    def send_report_to_admin(self, trigger_type: str = "Cron"):
        if not self.config.admin_email:
            self.logger.warning("SLA Report ignoré : ADMIN_EMAIL non configuré dans .env")
            return False
            
        self.logger.info("Envoi du rapport SLA (%s) à %s...", trigger_type, self.config.admin_email)
        
        html_body, csv_bytes = self.generate_html_report()
        
        eml = EmailMessage()
        eml["Subject"] = f"[Mail2Rag] Rapport SLA & Délais ({trigger_type})"
        eml["To"] = self.config.admin_email
        eml["From"] = self.config.imap_user
        
        eml.set_content("Veuillez consulter la version HTML de ce message.", subtype='html')
        eml.replace_header('Content-Type', 'text/html')
        eml.set_payload(html_body, charset='utf-8')
        
        dynamic_attachments = []
        if csv_bytes:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            dynamic_attachments.append((f"SLA_Export_{date_str}.csv", csv_bytes, "text/csv"))
            
        success = self.mail_service.send_generated_email(
            eml=eml, 
            dynamic_attachments=dynamic_attachments
        )
        
        if success:
            self.logger.info("✅ Rapport SLA envoyé avec succès.")
            return True
        else:
            self.logger.error("❌ Échec de l'envoi du rapport SLA.")
            return False
