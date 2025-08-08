# 🔒 GUIDE DE SÉCURITÉ - DINO CHALLENGE BOT

## ⚠️ **AVERTISSEMENT SÉCURITÉ**

**JAMAIS** commiter les fichiers suivants :
- `.env` (contient vos vrais tokens)
- `data/users.json` (données utilisateurs)
- `data/scores.json` (scores)
- `data/payments.json` (paiements)

## 🛡️ **TOKENS ET CLÉS SECRÈTES**

### **Variables d'environnement requises**

Créez un fichier `.env` LOCAL avec :

```env
# Bot Telegram - CRITIQUE
TELEGRAM_BOT_TOKEN=your_bot_token_here

# PayPal - SENSIBLE  
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_SECRET_KEY=your_paypal_secret_key
PAYPAL_MODE=sandbox

# Admin - PRIVÉ
ORGANIZER_CHAT_ID=your_telegram_id_here
```

### **Obtenir les tokens**

**Bot Telegram :**
1. @BotFather → `/newbot`
2. Copiez le token (format: `123456:ABC-DEF...`)

**PayPal :**
1. [developer.paypal.com](https://developer.paypal.com)
2. Créez une app
3. Copiez Client ID et Secret

**Votre ID Telegram :**
1. @userinfobot
2. Copiez votre ID numérique

## 🔐 **BONNES PRATIQUES**

### ✅ **À FAIRE**
- Utilisez `.env` pour les secrets
- Gardez `.env` en local uniquement
- Utilisez `.env.example` pour les templates
- Configurez les variables sur Render
- Régénérez les tokens si compromis

### ❌ **JAMAIS FAIRE**
- Commiter `.env` sur GitHub
- Mettre des vrais tokens dans la documentation
- Partager les tokens en public
- Laisser les tokens en dur dans le code

## 🚨 **EN CAS DE COMPROMISSION**

1. **Révoquez immédiatement** tous les tokens
2. **Régénérez** de nouveaux tokens
3. **Mettez à jour** vos variables d'environnement
4. **Vérifiez** l'historique Git

## 📋 **DÉPLOIEMENT SÉCURISÉ**

### **Local**
```bash
cp .env.example .env
# Éditez .env avec vos vrais tokens
python bot.py
```

### **Render**
- Variables d'environnement dans le dashboard
- Jamais de secrets dans le code
- Utilisez les secret management features

## 🔍 **VÉRIFICATION**

Avant chaque commit :
```bash
git status
git diff
# Vérifiez qu'aucun secret n'est inclus
```

⚠️ **Ce bot traite des paiements réels - la sécurité est CRITIQUE !**
