from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

import requests
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

from config import Config

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Service chargé d'analyser les documents (images/PDF) :

    - Si VISION_ENABLE = true et format supporté : envoi à un modèle Vision (LM Studio).
    - Sinon (ou en cas d'échec) : fallback OCR Tesseract classique.

    Le résultat est un texte brut prêt à être indexé dans AnythingLLM.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

        # Chargement du prompt Vision depuis un fichier (si présent)
        self.vision_prompt: str = (
            config.load_prompt(config.vision_prompt_file) or self._get_default_prompt()
        )
        if not config.load_prompt(config.vision_prompt_file):
            logger.warning("Using hardcoded Vision AI prompt as fallback")

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def analyze_document(self, file_path: str | Path) -> Optional[str]:
        """
        Analyse un document et renvoie un texte descriptif/ocrisé.

        - Retourne une chaîne non vide si analyse réussie.
        - Retourne None si tout a échoué ou si le résultat est vide.
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        logger.debug("Analyse document : %s (ext=%s)", path.name, ext)

        # 1. Tentative Vision IA (si activée + extension supportée)
        if self.config.vision_enable and ext in {".jpg", ".jpeg", ".png", ".pdf"}:
            try:
                return self._analyze_with_vision_llm(path)
            except Exception as e:  # on log mais on laisse le fallback OCR prendre le relais
                logger.warning(
                    "⚠️ Échec Vision IA sur %s (%s). Bascule vers OCR classique.",
                    path.name,
                    e,
                )

        # 2. Fallback OCR Tesseract
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
