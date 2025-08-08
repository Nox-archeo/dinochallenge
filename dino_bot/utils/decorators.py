from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from services.user_manager import UserManager

def require_payment(func):
    """Décorateur pour vérifier que l'utilisateur a payé sa mise mensuelle"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_manager = UserManager()
        
        if not user_manager.has_paid_this_month(user_id):
            await update.message.reply_text(
                "🚫 Vous devez payer votre mise mensuelle (10 CHF) pour participer au concours.\n"
                "Utilisez 👤 Profil pour effectuer le paiement."
            )
            return
        
        return await func(update, context)
    return wrapper

def require_registration(func):
    """Décorateur pour vérifier que l'utilisateur est enregistré"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_manager = UserManager()
        
        if not user_manager.user_exists(user_id):
            # Enregistrer automatiquement l'utilisateur
            user_manager.register_user(
                user_id,
                update.effective_user.username or update.effective_user.first_name
            )
        
        return await func(update, context)
    return wrapper
