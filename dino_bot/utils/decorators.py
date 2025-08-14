from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import sys
import os

# Ajouter le répertoire parent au path pour importer depuis app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

def require_payment(func):
    """Décorateur pour vérifier que l'utilisateur a payé sa mise mensuelle"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            from app import db  # Utiliser la base de données principale
            
            user_id = update.effective_user.id
            has_paid = db.has_valid_payment(user_id)
            
            if not has_paid:
                await update.message.reply_text(
                    "⚠️ **Accès requis pour le mode compétition**\n\n"
                    "💰 **Deux options de participation :**\n"
                    "• 💳 Paiement unique : 0.05 CHF pour le mois en cours\n"
                    "• 🔄 Abonnement mensuel : 0.05 CHF/mois automatique\n\n"
                    "✅ **Avantages :**\n"
                    "• Scores comptabilisés dans le classement\n"
                    "• Éligibilité aux prix mensuels\n"
                    "• Accès illimité tout le mois\n\n"
                    "🆓 **En attendant :** Vous pouvez essayer le mode démo\n\n"
                    "Pour participer à la cagnotte, utilisez /payment",
                    parse_mode='Markdown'
                )
                return
            
            return await func(update, context)
        except Exception as e:
            print(f"❌ Erreur décorateur payment: {e}")
            # En cas d'erreur, afficher le message de paiement par sécurité
            await update.message.reply_text(
                "⚠️ **Erreur lors de la vérification du paiement**\n\n"
                "Pour participer au mode compétition, veuillez utiliser /payment\n"
                "En attendant, vous pouvez essayer le mode démo."
            )
            return
    return wrapper

def require_registration(func):
    """Décorateur pour vérifier que l'utilisateur est enregistré"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            from app import db  # Utiliser la base de données principale
            
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name or "Utilisateur"
            first_name = update.effective_user.first_name or username
            
            # Créer ou récupérer l'utilisateur dans la base de données
            user = db.create_or_get_user(user_id, username, first_name)
            
            if not user:
                await update.message.reply_text(
                    "❌ Erreur lors de la création du profil. Veuillez réessayer."
                )
                return
            
            return await func(update, context)
        except Exception as e:
            print(f"❌ Erreur décorateur registration: {e}")
            return await func(update, context)  # Continuer en cas d'erreur
    return wrapper
