#!/bin/bash
# Script de démarrage pour Render
echo "🚀 Démarrage du Dino Challenge - Production"

# Déterminer le type de service
if [ -n "$PORT" ]; then
    echo "🌐 Service Web détecté - démarrage API Flask avec Gunicorn"
    exec gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
else
    echo "🤖 Service Worker détecté - démarrage Bot Telegram"
    exec python telegram_bot.py
fi
    python bot.py
else
    echo "❌ Aucun fichier principal trouvé"
    exit 1
fi
