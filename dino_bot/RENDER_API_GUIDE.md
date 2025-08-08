# 🚀 CONFIGURATION RENDER - DINO CHALLENGE BOT + API

## 📋 **Configuration Render**

### **1. Variables d'Environnement Requises**

Dans l'onglet **Environment** de Render, ajoutez :

```env
# OBLIGATOIRE - Bot Telegram
TELEGRAM_BOT_TOKEN=votre_token_bot_ici

# OBLIGATOIRE - Base de données PostgreSQL (fournie par Render)
DATABASE_URL=postgresql://user:password@hostname:port/database

# OBLIGATOIRE - Admin
ORGANIZER_CHAT_ID=votre_id_telegram_ici

# OPTIONNEL - PayPal
PAYPAL_CLIENT_ID=votre_paypal_client_id
PAYPAL_SECRET_KEY=votre_paypal_secret_key
PAYPAL_MODE=live

# AUTOMATIQUE - Configuration
GAME_URL=https://nox-archeo.github.io/dinochallenge/
PYTHON_VERSION=3.10.13
```

### **2. Base de Données PostgreSQL**

1. **Dans Render Dashboard** → **"New +"** → **"PostgreSQL"**
2. **Nom** : `dino-challenge-db` 
3. **Plan** : Free (jusqu'à 1GB)
4. **Copiez l'URL de connexion** générée
5. **Ajoutez-la** comme `DATABASE_URL` dans votre Web Service

### **3. Web Service**

```
Name: dino-challenge-bot-api
Runtime: Python 3
Build Command: pip install -r requirements.txt  
Start Command: python app.py
Health Check Path: /health
```

### **4. Commandes Render**

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
python app.py
```

## 🔗 **Endpoints de l'API**

Une fois déployé, votre API sera disponible à :

- **Page d'accueil** : `https://votre-app.onrender.com/`
- **Health check** : `https://votre-app.onrender.com/health`
- **Soumettre score** : `POST https://votre-app.onrender.com/api/score`
- **Classement** : `GET https://votre-app.onrender.com/api/leaderboard`

## 📊 **API Endpoints**

### **POST /api/score**
Soumettre un score depuis le jeu :
```json
{
  "telegram_id": 123456789,
  "score": 2500,
  "username": "player_name",
  "first_name": "Player"
}
```

### **GET /api/leaderboard**
Récupérer le classement :
```json
{
  "leaderboard": [
    {
      "position": 1,
      "telegram_id": 123456789,
      "first_name": "Player",
      "best_score": 2500,
      "total_games": 5
    }
  ],
  "month": "2024-12",
  "total_players": 10
}
```

## 🎮 **Intégration avec le Jeu**

Dans votre jeu HTML/JavaScript, ajoutez :

```javascript
// Soumettre le score à l'API
async function submitScore(score) {
    try {
        const response = await fetch('https://votre-app.onrender.com/api/score', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                telegram_id: getUserTelegramId(), // À implémenter
                score: score,
                username: 'player_name',
                first_name: 'Player Name'
            })
        });
        
        const result = await response.json();
        console.log('Score soumis:', result);
    } catch (error) {
        console.error('Erreur soumission score:', error);
    }
}
```

## 🚀 **Déploiement**

1. **Pousser sur GitHub** avec les nouveaux fichiers
2. **Créer la base PostgreSQL** sur Render
3. **Créer le Web Service** sur Render
4. **Configurer les variables d'environnement**
5. **Déployer** !

Le bot sera accessible à la fois :
- 📱 **Via Telegram** pour les utilisateurs
- 🌐 **Via API REST** pour recevoir les scores du jeu
