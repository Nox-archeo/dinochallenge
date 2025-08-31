#!/bin/bash

echo "🚀 DÉPLOIEMENT AUTOMATIQUE SUR RENDER"
echo "======================================"

# Vérifier qu'on est sur Git
if [ ! -d ".git" ]; then
    echo "❌ Erreur: Ce dossier n'est pas un dépôt Git"
    exit 1
fi

# Ajouter tous les fichiers
echo "📁 Ajout des fichiers modifiés..."
git add .

# Commit avec message automatique
echo "💾 Commit des modifications..."
git commit -m "🏆 Ajout système distribution automatique des prix + commande admin

✅ NOUVEAUTÉS:
- Distribution automatique le 1er de chaque mois à 00:01
- Paiement PayPal automatique au top 3
- Notifications aux gagnants
- Remise à zéro des scores
- Commande /admin_distribute pour distribution manuelle
- Système de vérification quotidienne intégré

🐛 CORRECTIONS:
- Fix du scheduler qui ne fonctionnait pas
- Intégration complète dans app.py pour Render
- Gestion async/await correcte

$(date '+%d/%m/%Y %H:%M')"

# Push vers GitHub
echo "🌐 Push vers GitHub..."
git push origin main

echo ""
echo "✅ DÉPLOIEMENT TERMINÉ !"
echo "🔄 Render va automatiquement redéployer dans quelques minutes"
echo "📱 Vérifie les logs sur https://dashboard.render.com"
echo ""
echo "🏆 NOUVEAU SYSTÈME AUTOMATIQUE:"
echo "   - Distribution automatique le 1er de chaque mois"
echo "   - Commande admin: /admin_distribute 8 2025 (pour août)"
echo ""
