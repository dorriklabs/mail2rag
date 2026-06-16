import os
from pathlib import Path
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw
import requests
from unittest.mock import patch

from config import Config
from services.processor import DocumentProcessor
from services.cache_service import CacheService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ManualTest")

def create_native_pdf(path: Path):
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, "Ceci est un document PDF natif très propre.")
    c.drawString(100, 730, "Il contient du texte parfaitement lisible par PyMuPDF.")
    c.save()

def create_scanned_pdf(path: Path):
    # Créer une image vide avec du "bruit"
    img_path = path.with_suffix('.jpg')
    img = Image.new('RGB', (800, 1000), color=(200, 200, 200))
    d = ImageDraw.Draw(img)
    d.text((100, 100), "Texte illisible comme un scan délavé", fill=(190, 190, 190))
    img.save(str(img_path))
    
    # Créer un PDF de 2 pages avec cette image
    c = canvas.Canvas(str(path))
    c.drawImage(str(img_path), 0, 0, width=595, height=842)
    c.showPage()
    c.drawImage(str(img_path), 0, 0, width=595, height=842)
    c.save()
    img_path.unlink()

def main():
    config = Config()
    # On force la vision sélective et le timeout court au cas où LM Studio n'est pas up
    config.vision_pdf_mode = "low_quality_pages"
    config.vision_pdf_dpi = 150
    config.vision_timeout = 5
    
    processor = DocumentProcessor(config)
    cache = CacheService(Path(config.state_path).parent)
    
    native_path = Path("/tmp/native.pdf")
    scan_path = Path("/tmp/scan_multipage.pdf")
    
    create_native_pdf(native_path)
    create_scanned_pdf(scan_path)
    
    logger.info("=== 1. Test PDF Natif ===")
    res_native = processor._process_pdf(native_path)
    logger.info(f"Résultat Natif (extrait) : {res_native[:150]}")
    
    logger.info("=== 2. Test PDF Scanné Multipage (avec Mock Qwen3-VL) ===")
    
    # On mock la requête vers LM Studio pour simuler un succès Vision
    mock_response = requests.Response()
    mock_response.status_code = 200
    mock_response._content = b'{"choices": [{"message": {"content": "Texte extrait par Qwen3-VL Vision avec un score parfait."}}]}'
    
    with patch("requests.post", return_value=mock_response):
        res_scan = processor._process_pdf(scan_path)
        logger.info(f"Résultat Scan complet :\\n{res_scan}")
        
    logger.info("=== 3. Test Cache Hit ===")
    # Simulation du flux ingestion (appel direct de CacheService)
    params = {"vision_mode": config.vision_pdf_mode, "dpi": config.vision_pdf_dpi}
    key = cache.get_cache_key(native_path, params)
    
    # Premier passage : on enregistre
    cache.set_cached_extraction(key, {"extracted_text": res_native, "filename": native_path.name})
    
    # Deuxième passage : on récupère
    cached = cache.get_cached_extraction(key)
    if cached:
        logger.info(f"✅ Cache hit réussi pour {native_path.name} !")
    else:
        logger.error("❌ Echec du cache hit !")

if __name__ == "__main__":
    main()
