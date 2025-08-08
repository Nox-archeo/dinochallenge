#!/bin/bash
# Script de démarrage rapide pour le Dino Challenge Bot

echo "🦕 Dino Challenge Bot - Démarrage"
echo "================================="

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 n'est pas installé"
    exit 1
fi

# Vérifier les dépendances
echo "📦 Vérification des dépendances..."
pip install -r requirements.txt

# Vérifier le fichier .env
if [ ! -f .env ]; then
    echo "❌ Fichier .env manquant"
    echo "Copiez .env.example vers .env et configurez vos tokens"
    exit 1
fi

# Lancer les tests
echo "🧪 Lancement des tests..."
python test_bot.py

echo ""
echo "🚀 Prêt à lancer le bot !"
echo "Tapez: python bot.py"
