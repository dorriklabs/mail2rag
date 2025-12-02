"""
Service de rendu des emails pour l'application Mail2RAG.
Gère le rendu des notifications HTML via des templates Jinja2.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


class EmailRenderer:
    """Génère les emails HTML à partir des templates Jinja2."""
    
    def __init__(self, template_dir: Path):
        """
        Initialise le moteur de templates.
        
        Args:
            template_dir: Répertoire contenant les fichiers de templates Jinja2.
        """
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))
    
    def render_ingestion_success(self, workspace: str, files: list, archive_url: str, email_summary: str = None) -> str:
        """Notification d'ingestion réussie avec résumé/aperçu de l'email."""
        template = self.env.get_template('ingestion_success.html')
        return template.render(
            workspace=workspace,
            files=files,
            archive_url=archive_url,
            email_summary=email_summary
        )
    
    def render_ingestion_error(self):
        """
        Génère l'email de notification en cas d'échec d'indexation.
        
        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template('ingestion_error.html')
        return template.render()
    
    def render_ingestion_info(self, subject):
        """
        Génère un email informatif lorsqu'aucun document n'a été indexé.
        
        Args:
            subject: Sujet de l'email initial.
            
        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template('ingestion_info.html')
        return template.render(subject=subject)
    
    def render_crash_report(self, error_message):
        """
        Génère un rapport d'erreur critique.
        
        Args:
            error_message: Description de l'erreur à afficher.
            
        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template('crash_report.html')
        return template.render(error_message=error_message)
    
    def render_chat_response(self, response_text, sources, archive_base_url, workspace=None):
        """
        Génère la réponse de chat avec la liste des sources utilisées.
        
        Args:
            response_text: Texte de la réponse de l'IA.
            sources: Liste brute des sources renvoyées par AnythingLLM.
            archive_base_url: URL de base utilisée pour construire les liens d'archive.
            workspace: (optionnel) slug du workspace utilisé pour ce chat.
            
        Returns:
            str: Contenu HTML de l'email.
        """
        template = self.env.get_template('chat_response.html')
        
        formatted_sources = self.format_chat_sources(sources, archive_base_url)
        
        return template.render(
            response_text=response_text,
            sources=formatted_sources,
            archive_url=archive_base_url,
            workspace=workspace
        )
    
    def format_chat_sources(self, sources, archive_base_url):
        """
        Formate les sources de chat pour un affichage propre dans l'email.
        
        Args:
            sources: Liste brute des sources (format AnythingLLM).
            archive_base_url: URL de base des archives.
            
        Returns:
            list: Liste de dicts avec les clés 'name' et 'link'.
        """
        if not sources:
            return []
        
        formatted_sources = []
        seen = set()
        
        for source in sources:
            title = source.get('title', 'Inconnu')
            if title in seen:
                continue
            seen.add(title)
            
            # On conserve le chemin complet retourné par AnythingLLM (incluant le secure_id)
            # Exemple: "66a7f2/photo_analysis.txt" ou "66a7f2/No_Subject.txt"
            full_path = title.replace("_analysis.txt", "")
            link = f"{archive_base_url}/{full_path}"
            
            # On n'affiche que le nom de fichier dans la liste, pas le chemin complet
            display_name = Path(full_path).name
            
            formatted_sources.append({
                'name': display_name,
                'link': link
            })
        
        return formatted_sources
