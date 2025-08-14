from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils.decorators import require_registration

@require_registration
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la commande /start"""
    user_name = update.effective_user.first_name or update.effective_user.username
    
    # Créer le clavier principal
    keyboard = [
        ['🎮 Jouer', '📊 Classement'],
        ['👤 Profil', 'ℹ️ Aide / Règles']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_message = f"""
🦕 **Bienvenue dans Dino Challenge, {user_name}!**

🎯 **Concept :** Concours mensuel basé sur le célèbre jeu Chrome Dino Runner
💰 **Pari mensuel :** 10 CHF (optionnel)
🎮 **Tentatives :** 5 parties par jour maximum
🏆 **Récompenses mensuelles :**
  🥇 1er place : 40% de la cagnotte
  🥈 2e place : 15% de la cagnotte  
  🥉 3e place : 5% de la cagnotte

**Choisissez une option ci-dessous :**
"""
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour les boutons du menu principal"""
    text = update.message.text
    
    if text == '🎮 Jouer':
        # Vérifier d'abord si l'utilisateur a payé
        try:
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from app import db
            
            user_id = update.effective_user.id
            has_paid = db.has_valid_payment(user_id)
            
            if not has_paid:
                # Afficher le message de paiement au lieu de lancer le jeu
                from handlers.payment import payment_handler
                await payment_handler(update, context)
                return
            
            # Si l'utilisateur a payé, lancer le jeu normalement
            from handlers.play import play_handler
            await play_handler(update, context)
            
        except Exception as e:
            print(f"❌ Erreur vérification paiement: {e}")
            # En cas d'erreur, afficher le message de paiement par sécurité
            from handlers.payment import payment_handler
            await payment_handler(update, context)
    elif text == '📊 Classement':
        from handlers.leaderboard import leaderboard_handler
        await leaderboard_handler(update, context)
    elif text == '👤 Profil':
        from handlers.profile import profile_handler
        await profile_handler(update, context)
    elif text == 'ℹ️ Aide / Règles':
        from handlers.help import help_handler
        await help_handler(update, context)
    else:
        # Vérifier si c'est un email
        if '@' in text and '.' in text and len(text.split('@')) == 2:
            await handle_email_input(update, context)
        # Vérifier si c'est peut-être un nom (texte simple sans symboles)
        elif text.replace(' ', '').replace('-', '').replace("'", '').isalpha() and len(text) <= 50:
            await handle_name_input(update, context)
        else:
            await update.message.reply_text(
                "❓ Commande non reconnue. Utilisez les boutons du menu ou tapez /start"
            )

async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la saisie d'un email PayPal"""
    user_id = update.effective_user.id
    email = update.message.text.strip()
    
    # Validation basique de l'email
    email_parts = email.split('@')
    if len(email_parts) != 2 or '.' not in email_parts[1]:
        await update.message.reply_text(
            "❌ Format d'email invalide.\n"
            "💡 Exemple : `votre.email@exemple.com`",
            parse_mode='Markdown'
        )
        return
    
    from services.user_manager import UserManager
    user_manager = UserManager()
    
    if user_manager.set_paypal_email(user_id, email):
        await update.message.reply_text(
            f"✅ **Email PayPal configuré avec succès !**\n\n"
            f"📧 Email : `{email}`\n\n"
            f"Vous pourrez maintenant recevoir vos gains directement sur ce compte PayPal. 💰",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ Erreur lors de la configuration de l'email. Veuillez réessayer."
        )

async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la saisie d'un nom d'affichage"""
    user_id = update.effective_user.id
    name = update.message.text.strip()
    
    from services.user_manager import UserManager
    user_manager = UserManager()
    
    if user_manager.set_display_name(user_id, name):
        await update.message.reply_text(
            f"✅ **Nom d'affichage configuré !**\n\n"
            f"👤 Votre nom : `{name}`\n\n"
            f"Ce nom apparaîtra dans les classements et communications du bot. 🏆",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ Erreur lors de la configuration du nom. Veuillez réessayer."
        )
