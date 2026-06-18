#!/bin/bash

# Script de lancement facile pour le test hybride E2E
# Trouve dynamiquement le conteneur et gère les variables d'environnement (PYTHONPATH)

echo "🔍 Recherche du conteneur Mail2Rag en cours d'exécution..."

# Vérifie si LM Studio tourne sur le port 1234
if ! curl -s http://localhost:1234/v1/models > /dev/null; then
    echo "⚠️ ATTENTION : LM Studio ne semble pas être lancé sur le port 1234."
    echo "Il est fortement recommandé d'exécuter './start.sh' avant de lancer ce script."
    echo "Le test va continuer, mais les appels à l'IA (RAG, etc.) risquent d'échouer."
    echo "--------------------------------------------------------------------------------"
    sleep 3
fi

# On cherche en priorité l'instance "accueil" (qui contient le moteur principal), 
# sinon on prend n'importe quelle instance mail2rag (sauf les services annexes)
CONTAINER=$(docker ps --format '{{.Names}}' | grep -m 1 'mail2rag_accueil')

if [ -z "$CONTAINER" ]; then
    CONTAINER=$(docker ps --format '{{.Names}}' | grep 'mail2rag' | grep -v 'tika' | grep -v 'archive' | grep -v 'proxy' | head -n 1)
fi

if [ -z "$CONTAINER" ]; then
    echo "❌ Erreur : Aucun conteneur applicatif Mail2Rag n'est actuellement en cours d'exécution."
    echo "Assurez-vous que vos conteneurs sont lancés (ex: docker-compose up -d)."
    exit 1
fi

echo "✅ Conteneur applicatif trouvé : $CONTAINER"
echo "🚀 Lancement du test hybride (run_hybrid_test.py)..."
echo "--------------------------------------------------------------------------------"

# Utilisation de docker exec avec le bon PYTHONPATH et sans buffer pour l'affichage en temps réel
docker exec -it "$CONTAINER" sh -c 'cd /app && PYTHONPATH=/app PYTHONUNBUFFERED=1 python scripts/run_hybrid_test.py'

echo "--------------------------------------------------------------------------------"
echo "✅ Test terminé."
