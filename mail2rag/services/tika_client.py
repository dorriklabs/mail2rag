"""
Apache Tika Client for document text extraction.

This module provides a client for interacting with Apache Tika Server
to extract text, metadata, and content types from various document formats.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class TikaClient:
    """
    Client pour Apache Tika Server.
    
    Fournit des méthodes pour extraire du texte, détecter le type MIME,
    et récupérer les métadonnées de documents.
    """

    def __init__(self, server_url: str, timeout: int = 60) -> None:
        """
        Initialise le client Tika.
        
        Args:
            server_url: URL du serveur Tika (ex: http://tika:9998)
            timeout: Timeout pour les requêtes HTTP en secondes
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        logger.debug("TikaClient initialisé vers %s", self.server_url)

    def extract_text(self, file_path: Path) -> Optional[str]:
        """
        Extrait le texte d'un document via Tika.
        
        Args:
            file_path: Chemin du fichier à analyser
            
        Returns:
            Texte extrait ou None en cas d'échec
        """
        if not file_path.exists():
            logger.error("Fichier introuvable pour extraction Tika: %s", file_path)
            return None

        url = f"{self.server_url}/tika"
        
        logger.debug("Début extraction Tika sur %s...", file_path.name)
        
        try:
            with file_path.open("rb") as f:
                # L'endpoint /tika retourne le texte brut en text/plain
                headers = {
                    "Accept": "text/plain; charset=UTF-8",
                    "Accept-Charset": "UTF-8",
                }
                
                response = requests.put(
                    url,
                    data=f,
                    headers=headers,
                    timeout=self.timeout,
                )
                
                if response.status_code != 200:
                    logger.error(
                        "Échec extraction Tika pour %s. Code: %s, Réponse: %s",
                        file_path.name,
                        response.status_code,
                        response.text[:500],
                    )
                    return None
                
                # Forcer l'encodage UTF-8 pour éviter les problèmes de mojibake
                response.encoding = 'utf-8'
                text = response.text.strip()
                
                # Tentative de réparation si le texte semble mal encodé
                if text and 'Ã' in text:
                    try:
                        # Essayer de réparer l'encodage latin-1 -> utf-8
                        text = text.encode('latin-1').decode('utf-8')
                        logger.debug("Encodage réparé pour %s (latin-1 -> utf-8)", file_path.name)
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        pass  # Garder le texte original si la réparation échoue
                
                if not text:
                    logger.warning(
                        "Extraction Tika terminée mais résultat vide pour %s",
                        file_path.name,
                    )
                    return None
                
                logger.info("✅ Extraction Tika réussie pour %s", file_path.name)
                return text
                
        except requests.RequestException as e:
            logger.error(
                "Erreur HTTP lors de l'extraction Tika pour %s: %s",
                file_path.name,
                e,
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                "Erreur inattendue lors de l'extraction Tika pour %s: %s",
                file_path.name,
                e,
                exc_info=True,
            )
            return None

    def extract_text_from_bytes(self, content: bytes) -> Optional[str]:
        """
        Extrait le texte de bytes de document via Tika.
        
        Args:
            content: Contenu binaire du fichier
            
        Returns:
            Texte extrait ou None en cas d'échec
        """
        if not content:
            logger.warning("Contenu vide fourni à extract_text_from_bytes")
            return None

        url = f"{self.server_url}/tika"
        
        logger.debug("Début extraction Tika depuis bytes (%d octets)...", len(content))
        
        try:
            headers = {
                "Accept": "text/plain; charset=UTF-8",
                "Accept-Charset": "UTF-8",
            }
            
            response = requests.put(
                url,
                data=content,
                headers=headers,
                timeout=self.timeout,
            )
            
            if response.status_code != 200:
                logger.error(
                    "Échec extraction Tika depuis bytes. Code: %s, Réponse: %s",
                    response.status_code,
                    response.text[:500],
                )
                return None
            
            # Forcer l'encodage UTF-8 pour éviter les problèmes de mojibake
            response.encoding = 'utf-8'
            text = response.text.strip()
            
            # Tentative de réparation si le texte semble mal encodé
            if text and 'Ã' in text:
                try:
                    # Essayer de réparer l'encodage latin-1 -> utf-8
                    text = text.encode('latin-1').decode('utf-8')
                    logger.debug("Encodage réparé (latin-1 -> utf-8)")
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass  # Garder le texte original si la réparation échoue
            
            if not text:
                logger.warning("Extraction Tika terminée mais résultat vide")
                return None
            
            logger.info("✅ Extraction Tika depuis bytes réussie (%d caractères)", len(text))
            return text
                
        except requests.RequestException as e:
            logger.error("Erreur HTTP lors de l'extraction Tika depuis bytes: %s", e)
            return None
        except Exception as e:
            logger.error("Erreur inattendue lors de l'extraction Tika depuis bytes: %s", e)
            return None

    def detect_content_type(self, file_path: Path) -> Optional[str]:
        """
        Détecte le type MIME d'un fichier via Tika.
        
        Args:
            file_path: Chemin du fichier à analyser
            
        Returns:
            Type MIME (ex: "application/pdf") ou None en cas d'échec
        """
        if not file_path.exists():
            logger.error("Fichier introuvable pour détection MIME: %s", file_path)
            return None

        url = f"{self.server_url}/detect/stream"
        
        try:
            with file_path.open("rb") as f:
                response = requests.put(
                    url,
                    data=f,
                    timeout=self.timeout,
                )
                
                if response.status_code == 200:
                    mime_type = response.text.strip()
                    logger.debug("Type MIME détecté pour %s: %s", file_path.name, mime_type)
                    return mime_type
                
                logger.error(
                    "Échec détection MIME pour %s. Code: %s",
                    file_path.name,
                    response.status_code,
                )
                return None
                
        except Exception as e:
            logger.error(
                "Erreur détection MIME pour %s: %s",
                file_path.name,
                e,
                exc_info=True,
            )
            return None

    def extract_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extrait les métadonnées d'un document via Tika.
        
        Args:
            file_path: Chemin du fichier à analyser
            
        Returns:
            Dictionnaire de métadonnées (vide si échec)
        """
        if not file_path.exists():
            logger.error("Fichier introuvable pour extraction métadonnées: %s", file_path)
            return {}

        url = f"{self.server_url}/meta"
        
        try:
            with file_path.open("rb") as f:
                headers = {
                    "Accept": "application/json",
                }
                
                response = requests.put(
                    url,
                    data=f,
                    headers=headers,
                    timeout=self.timeout,
                )
                
                if response.status_code == 200:
                    metadata = response.json()
                    logger.debug(
                        "Métadonnées extraites pour %s: %d champs",
                        file_path.name,
                        len(metadata) if isinstance(metadata, dict) else 0,
                    )
                    return metadata if isinstance(metadata, dict) else {}
                
                logger.error(
                    "Échec extraction métadonnées pour %s. Code: %s",
                    file_path.name,
                    response.status_code,
                )
                return {}
                
        except Exception as e:
            logger.error(
                "Erreur extraction métadonnées pour %s: %s",
                file_path.name,
                e,
                exc_info=True,
            )
            return {}

    def health_check(self) -> bool:
        """
        Vérifie que le serveur Tika est accessible.
        
        Returns:
            True si le serveur répond, False sinon
        """
        url = f"{self.server_url}/tika"
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                logger.debug("Tika server health check: OK")
                return True
            
            logger.warning(
                "Tika server health check failed. Code: %s",
                response.status_code,
            )
            return False
            
        except Exception as e:
            logger.warning("Tika server unreachable: %s", e)
            return False
