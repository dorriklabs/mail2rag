#!/bin/bash

# ==========================================
# Script de lancement automatique Mail2RAG
# ==========================================

echo "🚀 Démarrage du serveur LM Studio en arrière-plan..."
# On lance le serveur LM Studio sur l'adresse 0.0.0.0 pour qu'il soit accessible par Docker
# Les logs sont redirigés vers lms_server.log
nohup lms server start --bind 0.0.0.0 > lms_server.log 2>&1 &

echo "⏳ Attente du démarrage du serveur (5 secondes)..."
sleep 5

# --- CHARGEMENT DES MODELES ---
# Vous pouvez modifier ici le nom exact des modèles selon ce qui est installé sur votre machine

echo "🧠 Déchargement de tous les modeles de LM Studio"
lms unload --all
sleep 2

echo "🧠 Chargement du modèle de langage (Qwen3-VL) avec un contexte de 5500 tokens..."
# Le flag -c définit le contexte, -y valide automatiquement les choix
lms load "qwen3-vl-8b" -c 5500 --gpu max --parallel 1 -y

echo "📚 Chargement du modèle d'embedding (BGE-M3)..."
lms load "text-embedding-bge-m3" --gpu max -y

echo "🐳 Lancement des conteneurs Docker Mail2RAG..."
docker compose down
docker compose up -d

echo "✅ Démarrage complet ! Mail2RAG est prêt et l'IA est chargée."

nvidia-smi
