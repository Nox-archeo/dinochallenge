# 🚀 Guide de Déploiement sur Render

## 📋 Prérequis

1. **Compte Render** : [render.com](https://render.com)
2. **Repository GitHub** : Le bot doit être poussé sur GitHub
3. **Token Telegram Bot** : Obtenu via @BotFather
4. **Votre ID Telegram** : Obtenu via @userinfobot

## 🛠️ Configuration Render

### 1. Créer un Web Service

1. Connectez-vous à [Render Dashboard](https://dashboard.render.com)
2. Cliquez **"New +"** → **"Web Service"**
3. Connectez votre repository GitHub `dinochallenge`
4. Configurez le service :

```
Name: dino-challenge-bot
Environment: Python 3
Region: Frankfurt (EU) ou Oregon (US)
Branch: main
Root Directory: dino_bot
Build Command: pip install -r requirements.txt
Start Command: python bot.py
```

### 2. Variables d'Environnement

Dans l'onglet **Environment**, ajoutez :

```env
TELEGRAM_BOT_TOKEN=votre_token_bot_ici
ORGANIZER_CHAT_ID=votre_id_telegram_ici
PAYPAL_CLIENT_ID=votre_paypal_client_id (optionnel)
PAYPAL_CLIENT_SECRET=votre_paypal_client_secret (optionnel)
PAYPAL_MODE=sandbox
PYTHON_VERSION=3.10.13
```

### 3. Plan Render

- **Plan gratuit** : 750h/mois (suffisant pour débuter)
- **Plan payant** : $7/mois pour un service 24/7

## 🔧 Configuration Spéciale pour Render

Le bot est configuré pour fonctionner en tant que **Web Service** sur Render, pas comme un Worker. Cela permet :

- ✅ Démarrage automatique
- ✅ Redémarrage en cas de crash
- ✅ Logs accessibles
- ✅ Compatible avec le plan gratuit

## 📊 Monitoring

### Logs Render

Accédez aux logs via le dashboard Render pour :
- Voir les messages du bot
- Déboguer les erreurs
- Surveiller l'activité

### Commandes de Test

Une fois déployé, testez avec :
- `/start` - Menu principal
- `/admin_prizes` - Test distribution prix (réservé organisateur)
- `/play` - Lancer le jeu

## 🐛 Dépannage

### Bot ne démarre pas
1. Vérifiez `TELEGRAM_BOT_TOKEN` dans les variables d'environnement
2. Consultez les logs Render pour les erreurs
3. Vérifiez que `ORGANIZER_CHAT_ID` est un nombre valide

### Variables d'environnement manquantes
```bash
# Erreur typique dans les logs :
ValueError: TELEGRAM_BOT_TOKEN non trouvé
```
**Solution** : Ajoutez la variable manquante dans l'onglet Environment

### Service se met en veille (plan gratuit)
Le plan gratuit Render met le service en veille après 15 minutes d'inactivité.
**Solution** : Passez au plan payant pour un service 24/7

## ✅ Validation du Déploiement

1. **Dashboard Render** : Service status "Live"
2. **Logs** : "🦕 Démarrage du Dino Challenge Bot..."
3. **Telegram** : Le bot répond aux commandes
4. **Menu** : Toutes les commandes disponibles dans le menu hamburger

## 🔄 Mises à Jour

Pour déployer des mises à jour :

1. Modifiez le code localement
2. Commit et push sur GitHub
3. Render redéploie automatiquement

```bash
git add .
git commit -m "Update bot features"
git push origin main
```

## 📞 Support

En cas de problème :
1. Consultez les logs Render
2. Vérifiez les variables d'environnement
3. Testez localement avec `python bot.py`

Le bot est maintenant prêt pour Render ! 🚀
