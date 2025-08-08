# Dino Challenge Bot

Bot Telegram pour un concours mensuel basé sur le jeu Chrome Dino Runner.

## 🎯 Fonctionnalités

- **Abonnement payant** : 10 CHF/mois via PayPal
- **Jeu quotidien** : 5 tentatives par jour maximum  
- **Classement mensuel** : Basé sur le meilleur score
- **Récompenses automatiques** : 40%, 15%, 5% de la cagnotte
- **Paiements sécurisés** : Via PayPal (CB acceptée)

## 🚀 Installation

### Prérequis
- Python 3.8+
- Compte PayPal Developer
- Bot Telegram créé via @BotFather

### Installation locale

1. **Cloner le projet**
```bash
git clone <votre-repo>
cd dino_bot
```

2. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

3. **Configurer l'environnement**
Copiez `.env.example` vers `.env` et remplissez :
```env
TELEGRAM_BOT_TOKEN=votre_token_bot
PAYPAL_CLIENT_ID=votre_client_id
PAYPAL_SECRET_KEY=votre_secret_key
PAYPAL_SANDBOX=True
GAME_URL=https://votre-username.github.io/dinochallenge/
```

4. **Lancer le bot**
```bash
python bot.py
```

## 🏗️ Déploiement sur Render.com

### 1. Préparer le projet

Créer un `Procfile` :
```
web: python bot.py
```

### 2. Déployer sur Render

1. Connectez votre repository GitHub à Render
2. Créez un nouveau "Web Service"
3. Configurez les variables d'environnement
4. Déployez

### 3. Variables d'environnement Render

```
TELEGRAM_BOT_TOKEN=7961900456:AAE74vPKYN-hPaP5KMZwH_FdD7wcJomEMeM
PAYPAL_CLIENT_ID=AaAJyRluWJz3jb-I4RxO2aNECXT1ZFrXKrWUb4xxSTakgT_064EMdxIXtt4-Uao0xuPqFsQOeYNLld_G
PAYPAL_SECRET_KEY=EErXvGqa4rnz-eJkPPs7sYdG435wzXVVKGgpQa8SMNjg_arFfIq9LFyoeCShpcIV7b8rFMta8Z7eV-WA
PAYPAL_SANDBOX=False
GAME_URL=https://nox-archeo.github.io/dinochallenge/
```

## 📋 Structure du projet

```
dino_bot/
├── bot.py                 # Point d'entrée principal
├── handlers/              # Gestionnaires des commandes
│   ├── start.py          # Menu principal
│   ├── play.py           # Gestion du jeu
│   ├── profile.py        # Profil utilisateur
│   ├── leaderboard.py    # Classements
│   ├── payment.py        # Paiements
│   └── help.py           # Aide et règles
├── services/              # Services métier
│   ├── user_manager.py   # Gestion utilisateurs
│   ├── score_manager.py  # Gestion scores
│   ├── game_manager.py   # Logique de jeu
│   └── paypal.py         # Intégration PayPal
├── data/                  # Données JSON
│   ├── users.json        # Utilisateurs
│   ├── scores.json       # Scores
│   └── payments.json     # Paiements
├── utils/                 # Utilitaires
│   ├── decorators.py     # Décorateurs
│   └── time_utils.py     # Gestion du temps
├── .env                   # Variables d'environnement
├── requirements.txt       # Dépendances Python
└── README.md             # Ce fichier
```

## 🎮 Commandes du bot

### Commandes principales
- `/start` - Menu principal
- `/play` - Jouer au jeu
- `/score XXXX` - Soumettre un score
- `/profile` - Gérer son profil
- `/leaderboard` - Voir le classement
- `/top` - Top 3 du mois

### Commandes utilitaires
- `/help` - Aide et règles
- `/setpaypal email` - Configurer PayPal
- `/checkpayment ID` - Vérifier un paiement
- `/payments` - Historique des paiements

## 💳 Configuration PayPal

### 1. Compte Developer
1. Créez un compte sur [PayPal Developer](https://developer.paypal.com/)
2. Créez une application
3. Récupérez les clés Client ID et Secret

### 2. Mode Sandbox vs Live
- **Sandbox** : Tests avec faux argent
- **Live** : Vrais paiements

Changez `PAYPAL_SANDBOX` dans `.env`

## 🔧 Tests

### Test local rapide
```bash
# Lancer le bot
python bot.py

# Dans Telegram :
/start
/score 1500
/leaderboard
```

### Test de paiement
1. Utilisez le mode Sandbox
2. Créez un compte PayPal test
3. Testez le flux de paiement complet

## 🛡️ Sécurité

- Tokens et clés dans `.env` (non versionné)
- Validation stricte des scores
- Limite de tentatives quotidiennes
- Logs de toutes les transactions

## 📊 Monitoring

Le bot log automatiquement :
- Erreurs et exceptions
- Paiements effectués
- Distribution des prix
- Activité des utilisateurs

## 🆘 Support

### Problèmes courants

1. **Bot ne répond pas**
   - Vérifiez le token Telegram
   - Vérifiez les logs d'erreur

2. **Paiements échouent**
   - Vérifiez les clés PayPal
   - Mode Sandbox vs Live

3. **Scores non enregistrés**
   - Vérifiez les permissions de fichier
   - Vérifiez les logs

### Logs
```bash
# Voir les logs en temps réel
tail -f logs/bot.log
```

## 📈 Évolutions futures

- [ ] Intégration automatique des scores
- [ ] Webhooks PayPal pour confirmation instantanée
- [ ] Interface web d'administration
- [ ] Statistiques avancées
- [ ] Notifications push
- [ ] Support multi-langues

## 📄 Licence

Projet privé - Tous droits réservés.

## 👥 Auteur

Développé pour le Dino Challenge - Bot Telegram v1.0
