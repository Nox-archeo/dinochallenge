from telegram import Update
from telegram.ext import ContextTypes
from services.paypal import PayPalService

async def payment_success_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour confirmer un paiement réussi"""
    # Ce handler serait appelé via un webhook en production
    # Pour le moment, simulation du processus
    
    await update.message.reply_text(
        "✅ **Paiement confirmé !**\n\n"
        "Votre abonnement a été activé avec succès.\n"
        "Vous pouvez maintenant jouer au Dino Challenge !\n\n"
        "🎮 Tapez /start pour commencer",
        parse_mode='Markdown'
    )

async def payment_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour un paiement annulé"""
    
    await update.message.reply_text(
        "❌ **Paiement annulé**\n\n"
        "Votre paiement a été annulé.\n"
        "Vous pouvez réessayer via votre profil.\n\n"
        "👤 Tapez /profile pour réessayer",
        parse_mode='Markdown'
    )

async def check_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour vérifier le statut d'un paiement"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Veuillez spécifier l'ID de paiement.\n"
            "Exemple : `/checkpayment PAY-XXXXX`"
        )
        return
    
    payment_id = context.args[0]
    paypal_service = PayPalService()
    
    # Chercher le paiement dans l'historique
    user_payments = paypal_service.get_user_payments(user_id)
    payment = None
    
    for p in user_payments:
        if p['payment_id'] == payment_id:
            payment = p
            break
    
    if not payment:
        await update.message.reply_text(
            "❌ Paiement non trouvé ou non associé à votre compte."
        )
        return
    
    status_emoji = {
        'created': '⏳',
        'pending': '⏳',
        'completed': '✅',
        'failed': '❌',
        'cancelled': '❌'
    }
    
    message = f"""
💳 **Statut du paiement**

🆔 ID : `{payment['payment_id']}`
{status_emoji.get(payment['status'], '❓')} Statut : {payment['status'].title()}
💰 Montant : {payment['amount']} {payment['currency']}
📅 Date : {payment['created_at'][:10]}

"""
    
    if payment['status'] == 'completed':
        message += "✅ Abonnement activé avec succès !"
    elif payment['status'] == 'created':
        message += "⏳ En attente de confirmation PayPal"
    elif payment['status'] == 'failed':
        message += "❌ Échec du paiement - Veuillez réessayer"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def payment_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour afficher l'historique des paiements"""
    user_id = update.effective_user.id
    paypal_service = PayPalService()
    
    user_payments = paypal_service.get_user_payments(user_id)
    
    if not user_payments:
        await update.message.reply_text(
            "📋 **Historique des paiements**\n\n"
            "Aucun paiement trouvé."
        )
        return
    
    message = "📋 **Historique des paiements**\n\n"
    
    for payment in user_payments[-10:]:  # Derniers 10 paiements
        status_emoji = {
            'created': '⏳',
            'pending': '⏳', 
            'completed': '✅',
            'failed': '❌',
            'cancelled': '❌',
            'sent': '💸'
        }
        
        payment_type = payment.get('type', 'unknown')
        type_emoji = '💳' if payment_type == 'subscription' else '🏆' if payment_type == 'prize' else '❓'
        
        message += f"{type_emoji} {payment['created_at'][:10]} - "
        message += f"{status_emoji.get(payment['status'], '❓')} "
        message += f"{payment['amount']} {payment['currency']}\n"
        
        if payment_type == 'prize':
            message += f"   🏆 {payment.get('description', 'Récompense')}\n"
        
        message += "\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')
