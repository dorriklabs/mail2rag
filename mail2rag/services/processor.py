from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

from config import Config
from services.tika_client import TikaClient

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Service chargé d'analyser les documents (images/PDF) :

    - Si VISION_ENABLE = true et format supporté : envoi à un modèle Vision (LM Studio).
    - Sinon (ou en cas d'échec) : fallback OCR Tesseract classique.

    Le résultat est un texte brut prêt à être indexé via RAG Proxy.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

        # Chargement du prompt Vision depuis un fichier (si présent)
        self.vision_prompt: str = (
            config.load_prompt(config.vision_prompt_file) or self._get_default_prompt()
        )
        if not config.load_prompt(config.vision_prompt_file):
            logger.warning("Using hardcoded Vision AI prompt as fallback")
        
        # Initialisation du client Tika (si activé)
        self.tika_client: Optional[TikaClient] = None
        if config.tika_enable:
            self.tika_client = TikaClient(
                server_url=config.tika_server_url,
                timeout=config.tika_timeout,
            )
            logger.info("TikaClient initialisé (TIKA_ENABLE=true)")
        else:
            logger.info("TikaClient désactivé (TIKA_ENABLE=false)")

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def analyze_document(self, file_path: str | Path) -> Optional[str]:
        """
        Analyse un document et renvoie un texte descriptif/ocrisé.

        Pipeline d'extraction adaptatif :
        
        IMAGES (JPG/PNG) :
        1. Vision AI (si activé) - description visuelle riche
        2. Tika OCR (fallback)
        3. Tesseract OCR (fallback final)
        
        DOCUMENTS (PDF, DOCX, etc.) :
        1. Tika (extraction native optimale)
        2. Vision AI (si activé et Tika échoue)
        3. Tesseract OCR (fallback final)

        - Retourne une chaîne non vide si analyse réussie.
        - Retourne None si tout a échoué ou si le résultat est vide.
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        logger.debug("Analyse document : %s (ext=%s)", path.name, ext)

        # Déterminer le type de fichier
        is_image = ext in {".jpg", ".jpeg", ".png"}
        is_pdf = ext == ".pdf"
        
        # Vérifier si Vision AI est activé pour ce type
        vision_enabled = False
        if is_image and self.config.vision_enable_images:
            vision_enabled = True
        elif is_pdf and self.config.vision_enable_pdf:
            vision_enabled = True

        # ========== PIPELINE POUR LES IMAGES ==========
        if is_image:
            vision_result = None
            tika_metadata = None
            
            # 1. Vision AI pour description visuelle riche
            if vision_enabled:
                try:
                    vision_result = self._analyze_with_vision_llm(path)
                    if not vision_result:
                        logger.debug("Vision AI n'a pas retourné de résultat pour %s", path.name)
                except Exception as e:
                    logger.warning(
                        "⚠️ Échec Vision IA sur %s (%s).",
                        path.name,
                        e,
                    )
            
            # 2. Tika pour métadonnées EXIF (toujours essayer pour les images)
            if self.tika_client:
                try:
                    tika_metadata = self.tika_client.extract_metadata(path)
                    if not tika_metadata:
                        logger.debug("Tika n'a pas retourné de métadonnées pour %s", path.name)
                except Exception as e:
                    logger.debug("Échec extraction métadonnées Tika pour %s: %s", path.name, e)
            
            # 3. Combiner les résultats Vision AI + EXIF
            if vision_result or tika_metadata:
                return self._combine_vision_and_exif(vision_result, tika_metadata, path)
            
            # 4. Fallback Tika OCR si aucun résultat
            if self.tika_client:
                try:
                    result = self._analyze_with_tika(path)
                    if result:
                        return result
                except Exception as e:
                    logger.warning(
                        "⚠️ Échec Tika OCR sur %s (%s). Passage à Tesseract.",
                        path.name,
                        e,
                    )
            
            # 5. Fallback final Tesseract OCR
            return self._analyze_with_tesseract(path)

        # ========== PIPELINE POUR LES DOCUMENTS (PDF, DOCX, etc.) ==========
        else:
            # 1. Priorité Tika pour extraction optimale
            if self.tika_client:
                try:
                    result = self._analyze_with_tika(path)
                    if result:
                        return result
                    logger.debug("Tika n'a pas retourné de résultat pour %s", path.name)
                except Exception as e:
                    logger.warning(
                        "⚠️ Échec Tika sur %s (%s). Passage au fallback.",
                        path.name,
                        e,
                    )

            # 2. Fallback Vision AI (si activé et autorisé)
            if vision_enabled and self.config.tika_fallback_to_vision:
                try:
                    result = self._analyze_with_vision_llm(path)
                    if result:
                        return result
                except Exception as e:
                    logger.warning(
                        "⚠️ Échec Vision IA sur %s (%s). Bascule vers OCR classique.",
                        path.name,
                        e,
                    )

            # 3. Fallback final OCR Tesseract
            return self._analyze_with_tesseract(path)

    # ------------------------------------------------------------------ #
    # OCR Tesseract
    # ------------------------------------------------------------------ #
    def _analyze_with_tesseract(self, path: Path) -> Optional[str]:
        """
        Fallback d'analyse via Tesseract.

        - Pour les PDF : OCR des premières pages seulement (MAX_OCR_PAGES).
        - Pour les images : OCR direct.
        """
        logger.debug("Début OCR Tesseract sur %s...", path.name)
        text_content = ""

        try:
            if path.suffix.lower() == ".pdf":
                max_pages = self.config.max_ocr_pages
                dpi = self.config.ocr_dpi

                images = convert_from_path(
                    str(path),
                    dpi=dpi,
                    first_page=1,
                    last_page=max_pages,
                )
                logger.debug(
                    "PDF converti en %d image(s) pour OCR "
                    "(limite %d pages, dpi=%d).",
                    len(images),
                    max_pages,
                    dpi,
                )

                for i, img in enumerate(images, start=1):
                    page_text = pytesseract.image_to_string(
                        img,
                        lang="fra+eng",
                    )
                    text_content += f"\n--- Page {i} (OCR) ---\n{page_text}"

                # Note si on est potentiellement tronqué
                if len(images) == max_pages:
                    note = (
                        f"[NOTE] OCR réalisé sur les {max_pages} premières pages du PDF "
                        f"(le document peut éventuellement en contenir davantage).\n\n"
                    )
                    text_content = note + text_content

            else:
                img = Image.open(path)
                text_content = pytesseract.image_to_string(
                    img,
                    lang="fra+eng",
                )

            text_content = text_content.strip()
            if text_content:
                logger.debug("OCR Tesseract terminé avec succès sur %s.", path.name)
                return text_content

            logger.debug(
                "OCR Tesseract terminé sur %s mais résultat vide.",
                path.name,
            )
            return None

        except Exception as e:
            logger.error("❌ Erreur Tesseract sur %s : %s", path.name, e, exc_info=True)
            return None

    # ------------------------------------------------------------------ #
    # Apache Tika
    # ------------------------------------------------------------------ #
    def _analyze_with_tika(self, path: Path) -> Optional[str]:
        """
        Analyse via Apache Tika pour extraction de texte universelle.

        - Extrait le texte du document
        - Récupère les métadonnées pertinentes (auteur, date, titre)
        - Retourne le texte formaté avec métadonnées ou None si échec
        """
        if not self.tika_client:
            return None

        logger.info("📄 Extraction Tika pour %s...", path.name)

        # Extraction du texte
        text = self.tika_client.extract_text(path)
        if not text:
            return None

        # Extraction des métadonnées (optionnel, enrichit le contenu)
        metadata = self.tika_client.extract_metadata(path)

        # Construction du résultat avec métadonnées pertinentes
        result_parts = ["--- EXTRACTION TIKA ---\n"]

        # Ajout des métadonnées intéressantes si disponibles
        if metadata:
            if "dc:title" in metadata:
                result_parts.append(f"Titre: {metadata['dc:title']}\n")
            if "dc:creator" in metadata or "Author" in metadata:
                author = metadata.get("dc:creator") or metadata.get("Author")
                result_parts.append(f"Auteur: {author}\n")
            if "dcterms:created" in metadata or "Creation-Date" in metadata:
                created = metadata.get("dcterms:created") or metadata.get("Creation-Date")
                result_parts.append(f"Date de création: {created}\n")
            if "dcterms:modified" in metadata or "Last-Modified" in metadata:
                modified = metadata.get("dcterms:modified") or metadata.get("Last-Modified")
                result_parts.append(f"Dernière modification: {modified}\n")
            if "Content-Type" in metadata:
                result_parts.append(f"Type: {metadata['Content-Type']}\n")

            if len(result_parts) > 1:  # Si on a des métadonnées
                result_parts.append("\n")

        result_parts.append(text)

        return "".join(result_parts)

    def _combine_vision_and_exif(
        self,
        vision_result: Optional[str],
        metadata: Optional[Dict[str, Any]],
        path: Path,
    ) -> str:
        """
        Combine la description Vision AI avec les métadonnées EXIF pour les images.
        
        Args:
            vision_result: Résultat de l'analyse Vision AI
            metadata: Métadonnées extraites par Tika
            path: Chemin du fichier image
            
        Returns:
            Texte combiné avec description visuelle + EXIF
        """
        parts = []
        
        # Ajouter la description Vision AI
        if vision_result:
            parts.append(vision_result)
        
        # Ajouter les métadonnées EXIF pertinentes
        if metadata:
            exif_parts = []
            
            # Date de prise de vue
            date_keys = ["EXIF:DateTimeOriginal", "Date/Time Original", "Creation-Date", "dcterms:created"]
            for key in date_keys:
                if key in metadata:
                    exif_parts.append(f"📅 Date de prise de vue: {metadata[key]}")
                    break
            
            # Localisation GPS
            gps_lat = metadata.get("GPS Latitude")
            gps_lon = metadata.get("GPS Longitude")
            if gps_lat and gps_lon:
                exif_parts.append(f"📍 Coordonnées GPS: {gps_lat}, {gps_lon}")
            
            # Appareil photo
            make = metadata.get("EXIF:Make") or metadata.get("Make")
            model = metadata.get("EXIF:Model") or metadata.get("Model")
            if make or model:
                camera = f"{make} {model}".strip() if make and model else (make or model)
                exif_parts.append(f"📸 Appareil: {camera}")
            
            # Paramètres de prise de vue
            iso = metadata.get("EXIF:ISOSpeedRatings") or metadata.get("ISO Speed Ratings")
            aperture = metadata.get("EXIF:FNumber") or metadata.get("F-Number")
            exposure = metadata.get("EXIF:ExposureTime") or metadata.get("Exposure Time")
            focal = metadata.get("EXIF:FocalLength") or metadata.get("Focal Length")
            
            settings = []
            if iso:
                settings.append(f"ISO {iso}")
            if aperture:
                settings.append(f"f/{aperture}")
            if exposure:
                settings.append(f"{exposure}s")
            if focal:
                settings.append(f"{focal}mm")
            
            if settings:
                exif_parts.append(f"⚙️ Paramètres: {', '.join(settings)}")
            
            # Résolution
            width = metadata.get("Image Width") or metadata.get("tiff:ImageWidth")
            height = metadata.get("Image Height") or metadata.get("tiff:ImageLength")
            if width and height:
                exif_parts.append(f"📏 Résolution: {width}×{height} pixels")
            
            # Ajouter les métadonnées EXIF au résultat
            if exif_parts:
                parts.append("\n\n--- MÉTADONNÉES EXIF ---")
                parts.append("\n" + "\n".join(exif_parts))
        
        # Si aucun résultat, retourner une note
        if not parts:
            return f"Image analysée ({path.name}) - Aucune information extraite."
        
        return "".join(parts)

    # ------------------------------------------------------------------ #
    # Vision LLM (LM Studio)
    # ------------------------------------------------------------------ #
    def _analyze_with_vision_llm(self, path: Path) -> Optional[str]:
        """
        Analyse via un modèle Vision (LM Studio compatible OpenAI).

        - Pour les PDF, on convertit la première page en image (PNG).
        - On envoie une requête /chat/completions avec image en base64.
        """
        logger.info("👁️ Envoi de %s à LM Studio (Vision)...", path.name)

        temp_img_path = path
        is_temp = False

        # Si PDF, convertit la première page en image temporaire
        if path.suffix.lower() == ".pdf":
            dpi = self.config.ocr_dpi
            pages = convert_from_path(
                str(path),
                first_page=1,
                last_page=1,
                dpi=dpi,
            )
            if not pages:
                raise RuntimeError("PDF sans page exploitable")

            temp_img_path = path.with_suffix(".tmp.png")
            pages[0].save(temp_img_path, "PNG")
            is_temp = True

        try:
            image_bytes = temp_img_path.read_bytes()
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
        finally:
            if is_temp and temp_img_path.exists():
                temp_img_path.unlink()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.ai_api_key}",
        }

        payload = {
            "model": self.config.ai_model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.vision_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            "temperature": self.config.vision_temperature,
            "max_tokens": self.config.vision_max_tokens,
        }

        try:
            response = requests.post(
                self.config.ai_api_url,
                headers=headers,
                json=payload,
                timeout=self.config.vision_timeout,
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as e:
            logger.error(
                "❌ Erreur HTTP Vision IA sur %s : %s",
                path.name,
                e,
                exc_info=True,
            )
            raise
        except ValueError as e:
            logger.error(
                "❌ Erreur de décodage JSON Vision IA sur %s : %s",
                path.name,
                e,
                exc_info=True,
            )
            raise

        choices = result.get("choices") or []
        if not choices:
            logger.error(
                "Réponse Vision IA sans 'choices' pour %s : %s",
                path.name,
                str(result)[:500],
            )
            return None

        content = (
            choices[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            logger.error(
                "Réponse Vision IA vide pour %s : %s",
                path.name,
                str(result)[:500],
            )
            return None

        logger.info("✅ Réponse Vision IA reçue pour %s.", path.name)
        return (
            f"--- ANALYSE VISION IA ({self.config.ai_model_name}) ---\n\n"
            f"{content}"
        )

    # ------------------------------------------------------------------ #
    # Prompt par défaut
    # ------------------------------------------------------------------ #
    @staticmethod
    def _get_default_prompt() -> str:
        """Prompt de fallback si aucun fichier de prompt Vision n'est disponible."""
        return (
            "Agis comme un expert en analyse visuelle. Analyse cette image et adapte ta réponse selon son contenu.\n\n"
            "**ÉTAPE 1 : Identification**\n"
            "Détermine d'abord le type de contenu :\n"
            "- DOCUMENT : Facture, reçu, lettre, rapport, contrat, graphique, capture d'écran avec texte structuré\n"
            "- PHOTO : Paysage, événement, portrait, scène de vie, objet, architecture\n\n"
            "**ÉTAPE 2 : Analyse Adaptative**\n\n"
            "# Analyse de l'Image\n\n"
            "## 1. Classification\n"
            "- **Type** : (DOCUMENT ou PHOTO)\n"
            "- **Catégorie Précise** : (ex: Facture, Paysage urbain, Portrait de groupe, etc.)\n\n"
            "## 2. Méta-données\n"
            "**Pour un DOCUMENT :**\n"
            "- **Date** : (Format YYYY-MM-DD si visible, sinon 'Non spécifiée')\n"
            "- **Émetteur** : (Entreprise/Personne)\n"
            "- **Destinataire** : (Entreprise/Personne)\n"
            "- **Sujet/Titre** : (Objet principal)\n"
            "- **Données Financières** : (Montant HT, TVA, TTC, Devise si applicable, sinon 'N/A')\n\n"
            "**Pour une PHOTO :**\n"
            "- **Lieu** : (Localisation visible ou estimée, ou 'Non identifié')\n"
            "- **Date/Période** : (Si visible sur l'image ou déductible du contexte)\n"
            "- **Sujets Principaux** : (Personnes, objets, éléments dominants)\n"
            "- **Ambiance/Style** : (Couleurs dominantes, atmosphère, style photographique)\n\n"
            "## 3. Description Détaillée\n"
            "**Pour un DOCUMENT :** Un résumé concis du contenu et de l'objectif (2-3 phrases).\n\n"
            "**Pour une PHOTO :** Une description riche de la scène incluant :\n"
            "   - Ce qui est visible au premier plan / arrière-plan\n"
            "   - Les couleurs, la lumière, l'ambiance\n"
            "   - Les actions ou événements capturés\n"
            "   - Tout détail pertinent ou remarquable\n\n"
            "## 4. Transcription Textuelle\n"
            "**Transcris TOUT texte visible** (panneaux, enseignes, légendes, texte structuré) en respectant la mise en forme.\n"
            "Si aucun texte n'est présent, écris : 'Aucun texte visible.'"
        )
