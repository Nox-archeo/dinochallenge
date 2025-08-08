from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from utils.decorators import require_registration
from services.user_manager import UserManager
from services.paypal import PayPalService

@require_registration
async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour afficher et gérer le profil"""
    user_id = update.effective_user.id
    user_manager = UserManager()
    user = user_manager.get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ Erreur : Profil utilisateur non trouvé.")
        return
    
    # Vérifier le statut du paiement mensuel
    has_paid = user_manager.has_paid_this_month(user_id)
    payment_status = "✅ Payé ce mois" if has_paid else "❌ Non payé ce mois"
    
    # Tentatives restantes
    attempts_used = user_manager.get_daily_attempts(user_id)
    attempts_remaining = 5 - attempts_used
    
    # Email PayPal
    paypal_email = user.get('paypal_email', '')
    paypal_status = f"✅ {paypal_email}" if paypal_email else "❌ Non configuré"
    
    message = f"""
👤 **Votre Profil**

📝 **Informations :**
• Nom : {user['username']}
• ID Telegram : `{user_id}`
• Inscription : {user['registration_date'][:10]}

💳 **Participation au concours :**
• Statut : {payment_status}
• Email PayPal : {paypal_status}

🎮 **Jeu d'aujourd'hui :**
• Tentatives utilisées : {attempts_used}/5
• Tentatives restantes : {attempts_remaining}

**Actions disponibles :**
"""
    
    # Créer les boutons selon le statut
    keyboard = []
    
    if not has_paid:
        keyboard.append([InlineKeyboardButton("� Payer la mise mensuelle (10 CHF)", callback_data="pay_monthly_bet")])
    
    keyboard.append([InlineKeyboardButton("📧 Configurer email PayPal", callback_data="set_paypal")])
    keyboard.append([InlineKeyboardButton("📊 Mes statistiques", callback_data="my_stats")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def profile_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour les callbacks du profil"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "pay_monthly_bet":
        await handle_payment_request(query, context)
    elif data == "set_paypal":
        await handle_paypal_setup(query, context)
    elif data == "my_stats":
        await handle_stats_request(query, context)
    elif data == "back_to_profile":
        await profile_handler_from_callback(query, context)

async def handle_payment_request(query, context):
    """Gère la demande de paiement de la mise mensuelle"""
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    paypal_service = PayPalService()
    result = paypal_service.create_monthly_bet_payment(user_id, username)
    
    if result['success']:
        keyboard = [[InlineKeyboardButton("💳 Payer avec PayPal", url=result['payment_url'])]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"""
� **Paiement de la mise mensuelle**

💰 Montant : **10 CHF**
🎯 Participation : **Concours du mois en cours**

**Instructions :**
1. Cliquez sur le bouton ci-dessous
2. Connectez-vous à PayPal (ou payez par CB)
3. Confirmez le paiement
4. Votre participation sera activée automatiquement

🔒 Paiement sécurisé via PayPal
⚠️ **Attention :** Paiement nécessaire chaque mois pour participer
"""
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            f"❌ Erreur lors de la création du paiement :\n{result['error']}"
        )

async def handle_paypal_setup(query, context):
    """Gère la configuration de l'email PayPal"""
    keyboard = [
        [InlineKeyboardButton("🆕 Créer un compte PayPal", url="https://www.paypal.com/signin?returnUri=%2Fwebapps%2Fmpp%2Faccount-setup%2Fstart")],
        [InlineKeyboardButton("🔙 Retour au profil", callback_data="back_to_profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📧 **Configuration email PayPal**\n\n"
        "Tapez simplement votre email PayPal dans le chat :\n\n"
        "💡 **Exemple :** `votre.email@exemple.com`\n\n"
        "✅ **C'est tout !** Le bot détecte automatiquement votre email\n\n"
        "⚠️ **Important :** Vous devez avoir un compte PayPal valide pour recevoir vos gains.\n\n"
        "📝 Vous n'avez pas de compte PayPal ? Créez-en un gratuitement !",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_stats_request(query, context):
    """Affiche les statistiques détaillées de l'utilisateur"""
    user_id = query.from_user.id
    
    from services.game_manager import GameManager
    game_manager = GameManager()
    stats = game_manager.get_game_stats(user_id)
    
    message = f"""
📊 **Vos Statistiques**

🎮 **Ce mois-ci :**
• Parties jouées : {stats['total_games']}
• Meilleur score : {stats['best_score']}
• Score moyen : {stats['average_score']}
• Rang actuel : #{stats['current_rank'] if stats['current_rank'] > 0 else 'Non classé'}

⏰ **Aujourd'hui :**
• Tentatives utilisées : {stats['attempts_today']}/5
• Tentatives restantes : {stats['attempts_remaining']}

🏆 Continuez à jouer pour améliorer votre classement !
"""
    
    await query.edit_message_text(message, parse_mode='Markdown')

async def profile_handler_from_callback(query, context):
    """Affiche le profil depuis un callback"""
    user_id = query.from_user.id
    user_manager = UserManager()
    user_data = user_manager.get_user_info(user_id)
    
    from services.game_manager import GameManager
    game_manager = GameManager()
    can_play, reason = game_manager.can_user_play(user_id)
    
    # Statut du paiement
    has_paid = user_manager.has_paid_this_month(user_id)
    payment_status = "✅ Payé" if has_paid else "❌ Non payé"
    
    # Tentatives aujourd'hui
    attempts_today = game_manager.get_daily_attempts(user_id)
    attempts_remaining = max(0, 5 - attempts_today)
    
    message = f"""
👤 **Profil de {user_data['name']}**

💰 **Pari ce mois :** {payment_status}
🎮 **Tentatives aujourd'hui :** {attempts_today}/5
⏳ **Tentatives restantes :** {attempts_remaining}

📧 **Email PayPal :** {user_data.get('paypal_email', 'Non configuré')}

🏆 **Historique :**
• Total parties : {user_data.get('total_games', 0)}
• Meilleur score global : {user_data.get('best_score', 0)}

💡 **Configuration rapide :**
• Tapez votre nom pour le changer
• Tapez votre email pour configurer PayPal
"""

    # Boutons d'action
    buttons = []
    
    if not has_paid:
        buttons.append([InlineKeyboardButton("💳 Parier 10 CHF", callback_data="pay_monthly_bet")])
    
    buttons.extend([
        [InlineKeyboardButton("📧 Config. PayPal", callback_data="set_paypal")],
        [InlineKeyboardButton("📊 Mes stats", callback_data="my_stats")]
    ])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

@require_registration
async def setpaypal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour configurer l'email PayPal"""
    user_id = update.effective_user.id
    
    if not context.args:
        message = """📧 **Configuration email PayPal**

🎯 **Méthode simple :** Tapez juste votre email dans le chat
💡 **Exemple :** `john.doe@gmail.com`

🎯 **Méthode avec commande :** `/setpaypal votre.email@exemple.com`

🆕 **Pas de compte PayPal ?** Créez-en un gratuitement :
https://www.paypal.com/signup

⚠️ **Important :** Vous devez avoir un compte PayPal valide à cette adresse pour recevoir les paiements."""
        
        await update.message.reply_text(message, parse_mode='Markdown')
        return
    
    email = context.args[0]
    
    # Validation basique de l'email
    if '@' not in email or '.' not in email:
        await update.message.reply_text(
            "❌ Format d'email invalide.\n"
            "💡 **Exemple :** `/setpaypal votre.email@exemple.com`",
            parse_mode='Markdown'
        )
        return
    
    user_manager = UserManager()
    if user_manager.set_paypal_email(user_id, email):
        message = f"""✅ **Email PayPal configuré avec succès !**

📧 Email : `{email}`

Vous pourrez maintenant recevoir vos gains directement sur ce compte PayPal. 💰"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "❌ Erreur lors de la configuration de l'email. Veuillez réessayer."
        )
