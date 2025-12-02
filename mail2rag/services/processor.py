import logging
import base64
import requests
import pytesseract
from pathlib import Path
from PIL import Image
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self, config):
        self.config = config
        
        # Load Vision AI prompt from external file
        self.vision_prompt = config.load_prompt(config.vision_prompt_file)
        
        if not self.vision_prompt:
            logger.warning("Using hardcoded Vision AI prompt as fallback")
            self.vision_prompt = self._get_default_prompt()

    def analyze_document(self, file_path: str) -> str:
        path = Path(file_path)
        ext = path.suffix.lower()
        logger.debug(f"Analyse document : {path.name} (Ext: {ext})")

        # 1. Vision IA
        if self.config.vision_enable and ext in ['.jpg', '.jpeg', '.png', '.pdf']:
            try:
                return self._analyze_with_vision_llm(path)
            except Exception as e:
                logger.warning(f"⚠️ Échec Vision IA ({e}). Bascule vers OCR classique.")
        
        # 2. Fallback OCR
        return self._analyze_with_tesseract(path)

    def _analyze_with_tesseract(self, path: Path) -> str:
        logger.debug(f"Début OCR Tesseract sur {path.name}...")
        text_content = ""
        try:
            if path.suffix.lower() == '.pdf':
                max_pages = getattr(self.config, 'max_ocr_pages', 10)
                dpi = getattr(self.config, 'ocr_dpi', 300)

                # Conversion uniquement des premières pages pour limiter la charge
                images = convert_from_path(
                    str(path),
                    dpi=dpi,
                    first_page=1,
                    last_page=max_pages
                )
                logger.debug(
                    f"PDF converti en {len(images)} images pour OCR "
                    f"(limite {max_pages} pages, dpi={dpi})."
                )

                for i, img in enumerate(images):
                    text = pytesseract.image_to_string(img, lang='fra+eng')
                    text_content += f"\n--- Page {i+1} (OCR) ---\n{text}"

                # Ajouter une note si on a atteint la limite théorique
                if len(images) == max_pages:
                    note = (
                        f"[NOTE] OCR réalisé sur les {max_pages} premières pages du PDF "
                        f"(le document peut éventuellement en contenir davantage).\n\n"
                    )
                    text_content = note + text_content

            else:
                img = Image.open(path)
                text_content = pytesseract.image_to_string(img, lang='fra+eng')
            
            if text_content.strip():
                logger.debug("OCR Tesseract terminé avec succès.")
                return text_content
            else:
                logger.debug("OCR Tesseract terminé mais résultat vide.")
                return None
        except Exception as e:
            logger.error(f"❌ Erreur Tesseract : {e}")
            return None

    def _analyze_with_vision_llm(self, path: Path) -> str:
        logger.info(f"👁️ Envoi de {path.name} à LM Studio (Vision)...")
        
        temp_img_path = path
        is_temp = False
        
        if path.suffix.lower() == '.pdf':
            dpi = getattr(self.config, 'ocr_dpi', 300)
            pages = convert_from_path(str(path), first_page=1, last_page=1, dpi=dpi)
            if not pages:
                raise Exception("PDF vide")
            temp_img_path = path.with_suffix(".tmp.png")
            pages[0].save(temp_img_path, 'PNG')
            is_temp = True

        with open(temp_img_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')

        if is_temp and temp_img_path.exists():
            temp_img_path.unlink()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.ai_api_key}"
        }
        
        payload = {
            "model": self.config.ai_model_name,
            "messages": [
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": self.vision_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ],
            "temperature": self.config.vision_temperature,
            "max_tokens": self.config.vision_max_tokens
        }

        response = requests.post(
            self.config.ai_api_url,
            headers=headers,
            json=payload,
            timeout=self.config.vision_timeout
        )
        response.raise_for_status()
        
        result = response.json()
        logger.info("✅ Réponse Vision IA reçue.")
        return (
            f"--- ANALYSE VISION IA ({self.config.ai_model_name}) ---\n\n"
            f"{result['choices'][0]['message']['content']}"
        )
    
    def _get_default_prompt(self):
        """Fallback hardcoded prompt if external file not found."""
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
