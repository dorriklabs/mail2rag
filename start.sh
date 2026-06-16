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

echo "🧠 Chargement du modèle de langage (Qwen) avec un contexte de 8192 tokens..."
# Le flag -c définit le contexte, -y valide automatiquement les choix
lms load "qwen" -c 8192 -y

echo "📚 Chargement du modèle d'embedding (BGE-M3)..."
lms load "bge-m3" -y

echo "🐳 Lancement des conteneurs Docker Mail2RAG..."
docker compose up -d

echo "✅ Démarrage complet ! Mail2RAG est prêt et l'IA est chargée."
