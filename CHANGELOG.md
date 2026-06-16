# Changelog

## [v3.35.0] - En attente (Branche: feature/v3.35.0-structured-ingestion)
- **Feat**: Ingestion JSON structurée opt-in via `STRUCTURED_INGESTION_ENABLED`.
- Remplacement des métadonnées injectées dans le texte par une structure `ExtractedDocument` (Pydantic v2).
- Nouveau endpoint cible optionnel `/admin/ingest/structured`.

## [v3.34.0] - Stable (Production / Main)
- **Feat**: Pipeline PDF optimisé page par page via PyMuPDF.
- **Feat**: Vision sélective (`low_quality_pages`) avec limite de concurrence.
- **Feat**: Cache composite (hash fichier + paramètres d'extraction).
- Suppression définitive de `pdf2image`.
