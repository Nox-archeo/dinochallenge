# 🔧 CONFIGURATION RENDER - GUIDE COMPLET

## ⚠️ PROBLÈME IDENTIFIÉ
Render exécute `python bot.py` au lieu de suivre notre configuration `python app.py`.

## 💡 SOLUTIONS APPLIQUÉES

### 1. Fichiers créés/mis à jour :
- ✅ `app.py` - Application complète (1385 lignes)
- ✅ `bot.py` - Redirection vers app.py
- ✅ `start.sh` - Script de démarrage robuste
- ✅ `Procfile` - Configuration Heroku-style
- ✅ `render.yaml` - Configuration Render mise à jour

### 2. Configuration manuelle dans Render :

#### Étape 1 : Aller dans le tableau de bord Render
1. Connectez-vous à render.com
2. Sélectionnez votre service "dino-challenge-bot-api"

#### Étape 2 : Modifier la commande de démarrage
1. Cliquez sur **Settings** (Paramètres)
2. Trouvez la section **Start Command**
3. Remplacez par une de ces options :

**Option A (recommandée) :**
```bash
./start.sh
```

**Option B :**
```bash
python app.py
```

**Option C (fallback) :**
```bash
python bot.py
```

#### Étape 3 : Variables d'environnement requises
Assurez-vous que ces variables sont configurées :
- `TELEGRAM_BOT_TOKEN` = votre token de bot
- `DATABASE_URL` = votre PostgreSQL de Render
- `ORGANIZER_CHAT_ID` = votre ID Telegram
- `PAYPAL_CLIENT_ID` = votre ID client PayPal
- `PAYPAL_SECRET_KEY` = votre clé secrète PayPal
- `PAYPAL_MODE` = "live" (déjà configuré)
- `GAME_URL` = "https://nox-archeo.github.io/dinochallenge/" (déjà configuré)
- `PORT` = 10000 (déjà configuré)

#### Étape 4 : Redéployer
1. Cliquez sur **Manual Deploy** ou attendez le déploiement automatique
2. Surveillez les logs de déploiement

## 🎯 RÉSULTAT ATTENDU

Avec ces configurations, Render devrait :
1. ✅ Trouver les fichiers requis
2. ✅ Installer les dépendances Python
3. ✅ Exécuter l'application correctement
4. ✅ Démarrer le bot Telegram + API Flask

## 📋 VÉRIFICATION POST-DÉPLOIEMENT

Une fois déployé, testez :
1. **Santé de l'API :** https://dinochallenge-bot.onrender.com/health
2. **Page d'accueil :** https://dinochallenge-bot.onrender.com/
3. **Bot Telegram :** Envoyez `/start` à votre bot

## 🔥 EN CAS D'ÉCHEC

Si ça ne marche toujours pas :
1. Vérifiez les logs de Render
2. Assurez-vous que la commande de démarrage est bien `./start.sh` ou `python app.py`
3. Vérifiez que toutes les variables d'environnement sont configurées
4. Contactez le support si nécessaire

---
**Date de création :** 8 août 2025
**Fichiers mis à jour :** app.py, bot.py, start.sh, render.yaml, Procfile
