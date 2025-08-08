#!/bin/bash

echo "🦕 Dino Challenge Bot - Démarrage sur Render"
echo "========================================"

# Afficher les variables d'environnement (sans les secrets)
echo "📋 Configuration:"
echo "- Python version: $(python --version)"
echo "- Current directory: $(pwd)"
echo "- Files in directory: $(ls -la)"

# Vérifier les variables d'environnement critiques
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ ERREUR: TELEGRAM_BOT_TOKEN manquant"
    exit 1
fi

if [ -z "$ORGANIZER_CHAT_ID" ]; then
    echo "⚠️ ATTENTION: ORGANIZER_CHAT_ID manquant"
fi

echo "✅ Variables d'environnement OK"
echo "🚀 Démarrage du bot..."

# Démarrer le bot
python bot.py
