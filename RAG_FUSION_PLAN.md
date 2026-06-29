# Amélioration du Score RAG (Passage à l'Agentic RAG / Query Expansion)

Le score de 3/7 indique que la limite du "RAG naïf" est atteinte. L'IA juge nous a expliqué pourquoi ça échoue : quand une question parle de la *Zone UA*, le moteur de recherche se focalise tellement sur *Zone UA* qu'il oublie de remonter le chapitre *Dispositions Communes* (qui s'applique à toutes les zones).

Pour résoudre ce problème de façon systémique et viser les 6/7 ou 7/7, je propose d'améliorer notre architecture avec le **RAG-Fusion (Multi-Query Expansion + RRF)**. C'est l'une des architectures les plus performantes à ce jour pour les documents complexes.

## User Review Required
Cette amélioration va transformer le "Query Router" actuel en un orchestrateur complet de recherche (RAG-Fusion). Lisez les ajouts ci-dessous (particulièrement le tri par score fusionné) et validez-vous cette approche pour que je commence le code ?

## Proposed Changes

### [RAG Proxy Core]

#### [MODIFY] [pipeline.py](file:///home/woz/SynologyDrive/Antigravity/Mail2Rag/ragproxy/app/pipeline.py)
- **`query_router()` (Domain-Aware Query Expansion)** :
  - Le *System Prompt* sera spécialisé pour l'urbanisme et le juridique. L'IA devra comprendre qu'un terme hyper-spécifique (ex: "Zone UA") cache souvent des règles générales.
  - Au lieu de renvoyer une seule `clean_query`, le LLM renverra une liste `expanded_queries` contenant 3 variantes stratégiques :
    1. La question stricte et corrigée.
    2. Une question "Dé-contextualisée" (axée sur le thème de fond, ex: "aspect extérieur clôture rue").
    3. Une question "Règles Générales" (ex: "dispositions communes et règles applicables à toutes les zones").
- **`run()` (RAG-Fusion & Multi-Threading)** :
  - **Parallélisation** : Création simultanée des vecteurs (Embeddings) et exécution des 3 recherches Qdrant (très rapide).
  - **Fusion RRF (Reciprocal Rank Fusion)** : Au lieu d'une simple déduplication, nous allons calculer un score global pour chaque morceau de texte. Si un paragraphe remonte dans le Top 5 de la requête 1 ET de la requête 3, son score RRF explose et il passe en tête de liste !
  - **Protection du Reranker** : Nous ne passerons au Reranker local que les X meilleurs résultats issus de la fusion mathématique, afin de ne pas ralentir le système (temps de réponse conservé sous les 5-10 secondes). Le Reranker n'aura plus qu'à affiner une sélection déjà quasi-parfaite.

## Verification Plan

### Automated Tests
- Je relancerai le script automatisé `./run_grid_search.sh` avec les paramètres actuels (Chunk de 1200, Overlap de 300).
- **Objectif** : Vérifier que le score grimpe de 3/7 à au moins 5/7 ou 6/7 grâce à la nouvelle stratégie de recherche multicritères.
