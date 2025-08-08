#!/bin/bash
# Script de démarrage pour Render
echo "🚀 Démarrage du Dino Challenge Bot..."

# Vérifier que les fichiers existent
if [ -f "app.py" ]; then
    echo "✅ app.py trouvé"
    python app.py
elif [ -f "bot.py" ]; then
    echo "✅ bot.py trouvé, exécution via bot.py"
    python bot.py
else
    echo "❌ Aucun fichier principal trouvé"
    exit 1
fi
