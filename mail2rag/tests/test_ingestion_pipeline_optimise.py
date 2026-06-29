import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from services.ingestion_service import IngestionService
from services.processor import DocumentProcessor
from config import Config

# Fixtures pour mocker l'environnement
@pytest.fixture
def mock_config():
    config = MagicMock(spec=Config)
    config.vision_pdf_mode = "low_quality_pages"
    config.vision_pdf_max_pages = 5
    config.vision_pdf_dpi = 150
    config.vision_force_on_tables = True
    config.vision_max_concurrent_calls = 1
    config.vision_prompt_file = "prompts/vision.txt"
    config.vision_max_tokens = 4000
    config.vision_timeout = 60
    config.structured_ingestion_enabled = False
    config.tika_enable = False
    config.ocr_dpi = 150
    config.ai_model_name = "qwen2-vl"
    config.chunk_size = 800
    config.chunk_overlap = 100
    config.state_path = Path("/tmp/state")
    config.rag_proxy_url = "http://localhost:8000"
    config.rag_proxy_timeout = 30
    config.ingestion_cache = True
    config.max_filename_length = 200
    config.archive_base_url = "http://archive.local"
    return config

@pytest.fixture
def processor(mock_config):
    # Mock LLM Client & Tika pour isolation
    proc = DocumentProcessor(mock_config)
    proc.llm_client = MagicMock()
    return proc

@pytest.fixture
def ingestion_service(mock_config, processor):
    service = IngestionService(
        config=mock_config,
        logger=MagicMock(),
        mail_service=MagicMock(),
        router=MagicMock(),
        processor=processor,
        cleaner=MagicMock(),
        support_qa_service=MagicMock(),
        email_renderer=MagicMock(),
        get_secure_id=MagicMock(),
        trigger_bm25_rebuild=MagicMock()
    )
    service.ragproxy_client = MagicMock()
    return service

@pytest.mark.parametrize("filename, text_content, expected_tag", [
    ("dummy.pdf", "Texte natif très propre avec des vraies phrases.", "Texte natif très propre"),
    ("plui_reglement.pdf", "Article 1: Dispositions Générales du PLUI. Les zones urbaines...", "PLUI")
])
def test_pdf_natif_sans_vision(processor, filename, text_content, expected_tag):
    """Vérifie qu'un PDF propre natif (standard ou PLUI) ne déclenche pas Qwen3-VL."""
    with patch("fitz.open") as mock_fitz_open, \
         patch("services.quality_scorer.QualityScorer.score_extraction_quality") as mock_scorer:
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 2
        mock_page = MagicMock()
        mock_page.get_text.return_value = text_content
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        # Simuler un score de qualité parfait
        mock_scorer.return_value = {
            "score": 0.95, "is_usable": True, 
            "suspected_scan": False, "suspected_table": False, 
            "reasons": []
        }
        
        result = processor._process_pdf(Path(filename))
        
        # Vérification
        assert expected_tag in result
        assert "Méthode : pymupdf" in result
        assert "Méthode : mixed" not in result
        processor.llm_client.vision.assert_not_called()

def test_pdf_scanne_avec_vision(processor):
    """Vérifie qu'un scan illisible déclenche Qwen3-VL (Vision IA)."""
    with patch("fitz.open") as mock_fitz_open, \
         patch("services.quality_scorer.QualityScorer.score_extraction_quality") as mock_scorer:
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = "" # Aucun texte
        
        # Mock de l'image
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"fake_image_bytes"
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        # Simuler un score de qualité faible (scan)
        mock_scorer.return_value = {
            "score": 0.1, "is_usable": False, 
            "suspected_scan": True, "suspected_table": False, 
            "reasons": ["Texte vide"]
        }
        
        # Simuler la réponse du LLM
        processor.llm_client.vision.return_value = "Texte extrait par l'IA Vision"
        
        result = processor._process_pdf(Path("scan.pdf"))
        
        # Vérification
        assert "Texte extrait par l'IA Vision" in result
        assert "Méthode : mixed" in result
        processor.llm_client.vision.assert_called_once()

def test_cache_hit_deuxieme_ingestion(ingestion_service, tmp_path):
    """Vérifie que la deuxième ingestion avec mêmes paramètres utilise le cache SQLite/JSON."""
    dummy_dir = tmp_path / "secure_dir"
    dummy_dir.mkdir()
    dummy_file = dummy_dir / "dummy.pdf"
    dummy_file.write_text("fake pdf content")
    
    with patch("services.cache_service.CacheService.get_cache_key") as mock_hash, \
         patch("services.cache_service.CacheService.get_cached_extraction") as mock_get_cache, \
         patch("services.cache_service.CacheService.set_cached_extraction") as mock_set_cache:
        
        mock_hash.return_value = "fake_hash_123"
        # Simuler un cache Hit
        mock_get_cache.return_value = {"extracted_text": "Texte mis en cache", "filename": "dummy.pdf"}
        
        # Mock de processor
        ingestion_service.processor.analyze_document = MagicMock()
        
        # Mock email et son composant 'msg' pour _process_attachments
        mock_email = MagicMock()
        mock_email.subject = "Test Subject"
        mock_email.date = "2026-06-16 10:00"
        mock_email.uid = "123"
        
        mock_msg = MagicMock()
        mock_msg.is_multipart.return_value = True
        
        mock_part = MagicMock()
        mock_part.get_content_maintype.return_value = "application"
        mock_part.get.return_value = "attachment"
        mock_part.get_filename.return_value = "dummy.pdf"
        mock_part.get_payload.return_value = b"fake content"
        
        mock_msg.walk.return_value = [mock_part]
        mock_email.msg = mock_msg
        
        # S'assurer que la pièce jointe n'est pas rejetée
        ingestion_service.cleaner.is_valid_attachment.return_value = True
        ingestion_service.ragproxy_client.ingest_document.return_value = {"status": "ok", "chunks_created": 1}
        
        # L'appel à la méthode
        ingestion_service._process_attachments(mock_email, "test_workspace", dummy_dir, "secure_123")
        
        # Assertions
        mock_get_cache.assert_called()
        ingestion_service.processor.analyze_document.assert_not_called()
        mock_set_cache.assert_not_called()

def test_concurrence_vision_limitee(processor):
    """Vérifie que la limite de concurrence du Semaphore est respectée."""
    assert processor._vision_semaphore._value == 1, "La limite de concurrence par défaut doit être 1"

def test_fallback_si_qwen_indisponible(processor):
    """Vérifie le comportement si l'API Vision échoue (timeout/indisponible)."""
    with patch("fitz.open") as mock_fitz_open, \
         patch("services.quality_scorer.QualityScorer.score_extraction_quality") as mock_scorer:
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Texte illisible"
        
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"fake_image"
        mock_page.get_pixmap.return_value = mock_pix
        
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        mock_scorer.return_value = {
            "score": 0.2, "is_usable": False, "suspected_scan": True, "suspected_table": False, "reasons": []
        }
        
        # Simuler une exception API (timeout)
        processor.llm_client.vision.side_effect = Exception("Timeout API")
        
        result = processor._process_pdf(Path("error.pdf"))
        assert result is None, "Le pipeline doit retourner None suite à l'exception non rattrapable du LLM"

def test_invalidation_cache_composite(ingestion_service):
    """Vérifie que la modification d'un paramètre d'extraction invalide le cache."""
    dummy_path = Path("/tmp/dummy.pdf")
    
    # Écrire un faux fichier pour tester le hash
    dummy_path.write_text("fake pdf content")
    
    try:
        # Params originaux
        params_1 = {"vision_mode": "low_quality_pages", "dpi": 150}
        key_1 = ingestion_service.cache_service.get_cache_key(dummy_path, params_1)
        
        # Modification du DPI
        params_2 = {"vision_mode": "low_quality_pages", "dpi": 300}
        key_2 = ingestion_service.cache_service.get_cache_key(dummy_path, params_2)
        
        # Modification du mode vision
        params_3 = {"vision_mode": "all_pages_small_pdf", "dpi": 150}
        key_3 = ingestion_service.cache_service.get_cache_key(dummy_path, params_3)
        
        assert key_1 != key_2, "Le changement de DPI doit générer une nouvelle clé de cache"
        assert key_1 != key_3, "Le changement de mode vision doit générer une nouvelle clé de cache"
        
        # Le file_hash de base reste identique (première partie de la clé)
        assert key_1.split('_')[0] == key_2.split('_')[0]
    finally:
        if dummy_path.exists():
            dummy_path.unlink()

def test_pdf_multipage_cible(processor):
    """
    Vérifie le comportement sur un PDF de 3 pages où seule la page 2 nécessite la vision.
    Attend: Page 1 et 3 -> pymupdf pur, Page 2 -> mixed (Vision).
    """
    with patch("fitz.open") as mock_fitz_open, \
         patch("services.quality_scorer.QualityScorer.score_extraction_quality") as mock_scorer:
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 3
        
        # Mocks des 3 pages
        mock_page_1 = MagicMock()
        mock_page_1.get_text.return_value = "Texte propre page 1"
        
        mock_page_2 = MagicMock()
        mock_page_2.get_text.return_value = "???" # Illisible
        mock_pix = MagicMock()
        # On définit le retour pour tobytes("png")
        mock_pix.tobytes.return_value = b"fake_image"
        mock_page_2.get_pixmap.return_value = mock_pix
        
        mock_page_3 = MagicMock()
        mock_page_3.get_text.return_value = "Texte propre page 3"
        
        # Comportement de load_page selon l'index
        def load_page_side_effect(index):
            if index == 0: return mock_page_1
            if index == 1: return mock_page_2
            if index == 2: return mock_page_3
        mock_doc.load_page.side_effect = load_page_side_effect
        mock_fitz_open.return_value = mock_doc
        
        # Score de qualité selon la page
        def scorer_side_effect(text, metadata=None):
            if "propre" in text:
                return {"score": 0.9, "is_usable": True, "suspected_scan": False, "suspected_table": False, "reasons": []}
            else:
                return {"score": 0.1, "is_usable": False, "suspected_scan": True, "suspected_table": False, "reasons": []}
        mock_scorer.side_effect = scorer_side_effect
        
        # Simuler LLM pour la page 2
        processor.llm_client.vision.return_value = "Texte IA page 2"
        
        result = processor._process_pdf(Path("multi.pdf"))
        
        # Vérifications
        assert processor.llm_client.vision.call_count == 1, "Vision ne doit être appelée qu'une fois (pour la page 2)"
        
        # Analyse des tags [Page X/Y | Qualité : Z | Méthode : W] dans le résultat
        assert "[Page 1/3" in result and "Méthode : pymupdf" in result
        assert "[Page 2/3" in result and "Méthode : mixed" in result
        assert "[Page 3/3" in result and "Méthode : pymupdf" in result
        
        assert "Texte propre page 1" in result
        assert "Texte IA page 2" in result
        assert "Texte propre page 3" in result

def test_structured_format(processor, mock_config, tmp_path):
    """Vérifie que la sortie structurée retourne bien un ExtractedDocument avec pages."""
    mock_config.structured_ingestion_enabled = True
    
    with patch("fitz.open") as mock_fitz_open, \
         patch("services.processor.QualityScorer.score_extraction_quality") as mock_scorer:
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Texte propre"
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        mock_scorer.return_value = {"score": 1.0, "is_usable": True, "suspected_scan": False, "suspected_table": False, "reasons": []}
        
        # Test direct _process_pdf
        path = tmp_path / "fake.pdf"
        path.write_bytes(b"fake")
        doc = processor._process_pdf(path, return_structured=True)
            
        assert doc.__class__.__name__ == "ExtractedDocument"
        assert doc.filename == "fake.pdf"
        assert doc.total_pages == 1
        assert len(doc.pages) == 1
        assert doc.pages[0].text == "Texte propre"
        assert doc.pages[0].page_number == 1
        assert doc.pages[0].quality_score == 1.0
        
        # Pydantic v2 dump
        dump = doc.model_dump()
        assert "pages" in dump
        assert dump["pages"][0]["text"] == "Texte propre"

