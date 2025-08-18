#!/bin/bash
# Script de démarrage pour Render
echo "🚀 Démarrage du Dino Challenge - Production"

# Utiliser app.py qui gère déjà les 2 services en production
echo "🔥 Démarrage app.py complet (API Flask + Bot Telegram)"
exec python app.py
    exec python telegram_bot.py
fi
    python bot.py
else
    echo "❌ Aucun fichier principal trouvé"
    exit 1
fi
