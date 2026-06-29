#!/bin/bash

# run_grid_search.sh
# Script d'automatisation (Grid Search) pour trouver les paramètres RAG parfaits.

cd "$(dirname "$0")"
echo "🚀 Lancement du Grid Search (LLM-as-a-judge)..."

if ! curl -s http://localhost:1234/v1/models > /dev/null; then
    echo "❌ ERREUR CRITIQUE : LM Studio n'est pas lancé sur le port 1234."
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

docker exec -i "$CONTAINER" sh -c 'python -m pytest --version > /dev/null 2>&1 || pip install pytest pytest-mock > /dev/null'

# Combinations: (CHUNK_SIZE CHUNK_OVERLAP CHUNKING_STRATEGY TOP_K FINAL_K USE_BM25 LLM_TEMPERATURE LLM_MAX_TOKENS)
CONFIGS=(
    "500 150 recursive 25 12 true 0.1 1000"
    "800 200 recursive 20 8 true 0.1 1000"
    "1200 300 recursive 15 5 true 0.1 1000"
)

TOTAL=${#CONFIGS[@]}
RESULTS_FILE="grid_search_results.log"
echo "--- RESULTATS DU GRID SEARCH ---" > $RESULTS_FILE

for i in "${!CONFIGS[@]}"; do
    CFG=(${CONFIGS[$i]})
    CHUNK_SIZE=${CFG[0]}
    CHUNK_OVERLAP=${CFG[1]}
    CHUNKING_STRATEGY=${CFG[2]}
    TOP_K=${CFG[3]}
    FINAL_K=${CFG[4]}
    USE_BM25=${CFG[5]}
    LLM_TEMPERATURE=${CFG[6]}
    LLM_MAX_TOKENS=${CFG[7]}
    
    echo "=========================================================================="
    echo "Passe $((i+1))/$TOTAL : CHUNK_SIZE=$CHUNK_SIZE, OVERLAP=$CHUNK_OVERLAP, TOP_K=$TOP_K, FINAL_K=$FINAL_K, BM25=$USE_BM25"
    if [ $i -eq 0 ]; then
        echo "⏳ Première passe : L'extraction PDF (Vision IA) va prendre ~4 minutes."
    else
        echo "⏳ Passes suivantes : L'extraction est en cache. Temps estimé : ~1 minute."
    fi
    echo "=========================================================================="
    
    # Exécution du test en transmettant toutes les variables
    OUTPUT=$(docker exec -i "$CONTAINER" sh -c "cd /app && PYTHONPATH=/app AI_MODEL_NAME='qwen/qwen3-vl-8b' CHUNK_SIZE=$CHUNK_SIZE CHUNK_OVERLAP=$CHUNK_OVERLAP CHUNKING_STRATEGY=$CHUNKING_STRATEGY TOP_K=$TOP_K FINAL_K=$FINAL_K USE_BM25=$USE_BM25 LLM_TEMPERATURE=$LLM_TEMPERATURE LLM_MAX_TOKENS=$LLM_MAX_TOKENS pytest tests/test_rag_evaluation.py -v -s")
    
    # Parcourt OUTPUT pour compter les "PASS" et extraire le score total
    PASSED=$(echo "$OUTPUT" | grep -c "STATUS: PASS")
    FAILED=$(echo "$OUTPUT" | grep -c "STATUS: FAIL")
    
    echo "✅ Résultat de la passe $((i+1)) : PASS=$PASSED, FAIL=$FAILED"
    
    echo "" >> $RESULTS_FILE
    echo "=== Configuration $((i+1)) : CS=$CHUNK_SIZE, CO=$CHUNK_OVERLAP, TK=$TOP_K, FK=$FINAL_K ===" >> $RESULTS_FILE
    echo "Bilan : PASS=$PASSED, FAIL=$FAILED" >> $RESULTS_FILE
    echo "--- RAW OUTPUT START ---" >> $RESULTS_FILE
    echo "$OUTPUT" >> $RESULTS_FILE
    echo "--- RAW OUTPUT END ---" >> $RESULTS_FILE
    # Récupère toutes les notes pour le log
    echo "$OUTPUT" | grep "NOTE:" >> $RESULTS_FILE
done

echo ""
echo "🎉 GRID SEARCH TERMINE ! Voici le récapitulatif :"
cat $RESULTS_FILE
