# 🔗 Configuration du Webhook PayPal

## 📋 **URL du Webhook**
```
https://dinochallenge-bot.onrender.com/paypal-webhook
```

## ⚙️ **Configuration dans PayPal Developer**

### **1. Accéder au Dashboard PayPal**
1. Connectez-vous à [PayPal Developer](https://developer.paypal.com/)
2. Sélectionnez votre application
3. Allez dans l'onglet **"Webhooks"**

### **2. Créer le Webhook**
1. Cliquez sur **"Add Webhook"**
2. **URL du webhook :** `https://dinochallenge-bot.onrender.com/paypal-webhook`
3. **Événements à sélectionner :**

#### **Paiements Uniques :**
- ✅ `PAYMENT.SALE.COMPLETED` - Paiement complété
- ✅ `PAYMENT.SALE.DENIED` - Paiement refusé
- ✅ `PAYMENT.SALE.PENDING` - Paiement en attente

#### **Abonnements :**
- ✅ `BILLING.SUBSCRIPTION.CREATED` - Abonnement créé
- ✅ `BILLING.SUBSCRIPTION.ACTIVATED` - Abonnement activé
- ✅ `BILLING.SUBSCRIPTION.CANCELLED` - Abonnement annulé
- ✅ `BILLING.SUBSCRIPTION.SUSPENDED` - Abonnement suspendu
- ✅ `BILLING.SUBSCRIPTION.PAYMENT.COMPLETED` - Paiement d'abonnement complété
- ✅ `BILLING.SUBSCRIPTION.PAYMENT.FAILED` - Paiement d'abonnement échoué

### **3. Sauvegarder le Webhook ID**
Après création, notez le **Webhook ID** pour vos logs.

## 🔧 **Variables d'Environnement Render**

Assurez-vous que ces variables sont configurées dans Render :

```env
# PayPal Configuration
PAYPAL_CLIENT_ID=votre_client_id_paypal
PAYPAL_SECRET_KEY=votre_secret_key_paypal
PAYPAL_MODE=live
```

## 🧪 **Test du Webhook**

### **Test Local (Développement)**
```bash
# Test du webhook avec curl
curl -X POST https://dinochallenge-bot.onrender.com/paypal-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "PAYMENT.SALE.COMPLETED",
    "resource": {
      "id": "test_payment_123",
      "amount": {"total": "11.00"},
      "item_list": {
        "items": [{
          "sku": "dino_monthly_123456789",
          "name": "Test Payment"
        }]
      }
    }
  }'
```

### **Test en Production**
1. PayPal propose un **"Webhook Simulator"** dans le dashboard
2. Utilisez-le pour tester les différents types d'événements
3. Vérifiez les logs de votre application Render

## 📊 **Flux de Paiement**

### **Paiement Unique :**
1. Utilisateur clique sur "Paiement Unique" dans le bot
2. Bot génère un lien PayPal via `/create-payment`
3. Utilisateur paye sur PayPal
4. PayPal envoie `PAYMENT.SALE.COMPLETED` au webhook
5. Bot active l'accès de l'utilisateur pour le mois
6. Notification envoyée à l'utilisateur via Telegram

### **Abonnement :**
1. Utilisateur choisit "Abonnement Mensuel" dans le bot
2. Bot génère un lien d'abonnement via `/create-subscription`
3. Utilisateur configure l'abonnement sur PayPal
4. PayPal envoie `BILLING.SUBSCRIPTION.ACTIVATED` au webhook
5. Bot crée l'abonnement en base et active l'accès
6. Chaque mois : `BILLING.SUBSCRIPTION.PAYMENT.COMPLETED` → renouvellement

## 🔒 **Sécurité**

### **Vérification des Webhooks PayPal**
Le webhook vérifie automatiquement :
- ✅ Signature PayPal (si configurée)
- ✅ Origine des requêtes
- ✅ Format des données JSON

### **Protection contre les Doublons**
- Les paiements sont identifiés par leur `payment_id` PayPal
- Les abonnements par leur `subscription_id`
- Impossible de traiter deux fois le même paiement

## 🚨 **Surveillance**

### **Logs à Surveiller**
- ✅ `🔔 Webhook PayPal reçu: [TYPE]`
- ✅ `✅ Paiement unique traité: [ID] = [MONTANT] CHF`
- ✅ `✅ Abonnement activé: [ID] = [SUBSCRIPTION_ID]`
- ❌ `❌ Erreur webhook PayPal: [ERREUR]`

### **Tableau de Bord Render**
Consultez régulièrement les logs dans Render pour détecter d'éventuels problèmes.

## 🎯 **URLs de Test**

### **Interface de Paiement :**
- Paiement unique : `https://dinochallenge-bot.onrender.com/create-payment?telegram_id=123456789`
- Abonnement : `https://dinochallenge-bot.onrender.com/create-subscription?telegram_id=123456789`

### **Health Check :**
- API Status : `https://dinochallenge-bot.onrender.com/health`

## 💡 **Bonnes Pratiques**

1. **Testez d'abord en mode Sandbox** avant de passer en Live
2. **Surveillez les logs** pendant les premiers jours
3. **Configurez des alertes** pour les erreurs de webhook
4. **Documentez tous les IDs** de transactions importantes
5. **Sauvegardez régulièrement** la base PostgreSQL

---

🎮 **Votre système de paiement PayPal est maintenant configuré !**
