#!/bin/bash
# Script de démarrage pour Render
echo "🚀 Démarrage du Dino Challenge - Production"

# TOUJOURS utiliser main.py qui gère les 2 services
echo "🌐 Démarrage API Flask + Bot Telegram via main.py"
exec python main.py
    exec python telegram_bot.py
fi
    python bot.py
else
    echo "❌ Aucun fichier principal trouvé"
    exit 1
fi
