#!/bin/bash

# run_test_rag_evaluation.sh
# Script pour lancer le test d'évaluation complet RAG avec LLM-as-a-judge
# Ce test s'occupe automatiquement d'ingérer le PDF PLUI puis de poser 4 questions.

cd "$(dirname "$0")"
echo "🚀 Lancement de l'évaluation RAG (LLM-as-a-judge)..."

# Vérifie si LM Studio tourne sur le port 1234
if ! curl -s http://localhost:1234/v1/models > /dev/null; then
    echo "❌ ERREUR CRITIQUE : LM Studio ne semble pas être lancé sur le port 1234."
    echo "Ce test d'évaluation IA a impérativement besoin d'un LLM fonctionnel pour :"
    echo "  1) Lire le PDF via Vision."
    echo "  2) Agir comme Juge IA pour évaluer les réponses."
    echo "Veuillez démarrer LM Studio avant de lancer ce script."
    exit 1
fi

CONTAINER=$(docker ps --format '{{.Names}}' | grep -m 1 'mail2rag_accueil')

if [ -z "$CONTAINER" ]; then
    CONTAINER=$(docker ps --format '{{.Names}}' | grep 'mail2rag' | grep -v 'tika' | grep -v 'archive' | grep -v 'proxy' | head -n 1)
fi

if [ -z "$CONTAINER" ]; then
    echo "❌ Erreur : Aucun conteneur applicatif Mail2Rag n'est en cours d'exécution."
    exit 1
fi

echo "✅ Conteneur trouvé : $CONTAINER"

# On s'assure que pytest est installé (au cas où le conteneur a été recréé en mode prod)
docker exec -it "$CONTAINER" sh -c 'python -m pytest --version > /dev/null 2>&1 || pip install pytest pytest-mock > /dev/null'

# On passe explicitement le nom du modèle chargé par start.sh pour éviter l'erreur 400 Bad Request de LM Studio
docker exec -it "$CONTAINER" sh -c 'cd /app && PYTHONPATH=/app AI_MODEL_NAME="qwen/qwen3-vl-8b" pytest tests/test_rag_evaluation.py -v -s'
