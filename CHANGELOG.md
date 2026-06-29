# Changelog

## [v4.13.1] - Stable (Production / Main)
- **Fix**: Résolution des erreurs de typage strict et des faux positifs Pylance sur tous les services.

## [v4.13.0]
- **Feat**: Amélioration du rapport SLA (Heures ouvrées) et correctifs du routage sémantique.

## [v4.12.0 - v4.12.3]
- **Feat**: Envoi du rapport SLA par e-mail avec synthèse IA (LLM).
- **Perf**: Ajout du multithreading et activation du mode WAL SQLite pour de très hautes performances.
- **Test**: Implémentation des assertions strictes E2E pour le SLA et la boucle de feedback BCC.
- **Fix**: Implémentation de `send_generated_email` et refactoring DRY pour les pièces jointes.

## [v4.11.0]
- **Feat**: Ajout du tableau de bord SLA et du suivi des temps de réponse globaux.

## [v4.10.0 - v4.10.1]
- **Feat**: Auto-ingestion BCC et boucle de feedback IA (Self-reflection / Correction autonome).
- **Fix**: Filtre GIGO pour protéger l'ingestion BCC des bruits.

## [v3.35.0] - En attente (Branche: feature/v3.35.0-structured-ingestion)
- **Feat**: Ingestion JSON structurée opt-in via `STRUCTURED_INGESTION_ENABLED`.
- Remplacement des métadonnées injectées dans le texte par une structure `ExtractedDocument` (Pydantic v2).
- Nouveau endpoint cible optionnel `/admin/ingest/structured`.

## [v3.34.0] - Stable (Production / Main)
- **Feat**: Pipeline PDF optimisé page par page via PyMuPDF.
- **Feat**: Vision sélective (`low_quality_pages`) avec limite de concurrence.
- **Feat**: Cache composite (hash fichier + paramètres d'extraction).
- Suppression définitive de `pdf2image`.
