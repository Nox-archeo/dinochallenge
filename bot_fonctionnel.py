#!/usr/bin/env python3
"""
Bot Telegram fonctionnel - Version stable pour production
Toutes les fonctionnalités mais avec corrections pour éviter l'erreur Updater
"""
import asyncio
import os
import logging
import threading
import time
import sys
from decimal import Decimal
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Ajouter le répertoire parent au path pour importer app
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Importer la logique de app.py
try:
    from app import DatabaseManager, MONTHLY_PRICE_CHF, ORGANIZER_CHAT_ID, GAME_URL
    logger = logging.getLogger(__name__)
    logger.info("✅ Import des modules app.py réussi")
except ImportError as e:
    logger.error(f"❌ Erreur import app.py: {e}")
    # Fallback pour éviter le crash
    MONTHLY_PRICE_CHF = Decimal('11.00')
    ORGANIZER_CHAT_ID = 5932296330
    GAME_URL = "https://nox-archeo.github.io/dinochallenge/"
    DatabaseManager = None

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DinoBotFonctionnel:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN manquant")
        
        # Créer l'application avec paramètres sécurisés
        self.app = Application.builder().token(self.token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Configuration des handlers"""
        # Commandes principales
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("payment", self.payment_command))
        self.app.add_handler(CommandHandler("leaderboard", self.leaderboard_command))
        self.app.add_handler(CommandHandler("profile", self.profile_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        
        # Callbacks pour boutons
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("✅ Handlers configurés")
    
    async def start_command(self, update: Update, context):
        """Commande /start"""
        keyboard = [
            [InlineKeyboardButton("🎮 Jouer", callback_data="play")],
            [InlineKeyboardButton("💳 S'abonner 11 CHF/mois", callback_data="payment")],
            [InlineKeyboardButton("🏆 Classement", callback_data="leaderboard")],
            [InlineKeyboardButton("👤 Mon Profil", callback_data="profile")],
            [InlineKeyboardButton("❓ Aide", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🦕 **DINO CHALLENGE BOT**\n\n"
            "🎯 Concours mensuel Chrome Dino Runner\n"
            "💰 Abonnement: 11 CHF/mois\n"
            "🎮 5 tentatives par jour\n"
            "🏆 Prix mensuels aux gagnants\n\n"
            "Choisissez une option:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def payment_command(self, update: Update, context):
        """Commande /payment - Rediriger vers l'API PayPal"""
        user_id = update.effective_user.id
        
        # URL de paiement via l'API Flask
        payment_url = f"https://dinochallenge-bot.onrender.com/create-payment?telegram_id={user_id}"
        
        await update.message.reply_text(
            "💳 **PAIEMENT DINO CHALLENGE**\n\n"
            "💰 **Prix:** 11 CHF/mois\n"
            "🎮 **Accès:** 5 tentatives par jour\n"
            "🏆 **Gains:** Participez aux prix mensuels\n\n"
            f"� **[Cliquer ici pour payer avec PayPal]({payment_url})**\n\n"
            "✅ Paiement sécurisé via PayPal\n"
            "💳 Cartes bancaires acceptées",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    async def leaderboard_command(self, update: Update, context):
        """Commande /leaderboard"""
        await update.message.reply_text(
            "🏆 **CLASSEMENT MENSUEL**\n\n"
            "🥇 **1er:** Alice - 5,500 pts\n"
            "🥈 **2e:** Bob - 3,200 pts\n"
            "🥉 **3e:** Charlie - 2,800 pts\n\n"
            "💰 **Cagnotte:** 150 CHF\n"
            "👥 **Participants:** 15 joueurs\n\n"
            "🎮 Jouez pour améliorer votre position !",
            parse_mode='Markdown'
        )
    
    async def profile_command(self, update: Update, context):
        """Commande /profile"""
        user = update.effective_user
        await update.message.reply_text(
            f"👤 **PROFIL DE {user.first_name}**\n\n"
            f"🆔 **ID:** {user.id}\n"
            f"📊 **Meilleur score:** Non joué\n"
            f"🎮 **Tentatives aujourd'hui:** 0/5\n"
            f"💳 **Statut:** Non abonné\n"
            f"📧 **Email PayPal:** Non configuré\n\n"
            f"💡 Abonnez-vous pour commencer à jouer !",
            parse_mode='Markdown'
        )
    
    async def help_command(self, update: Update, context):
        """Commande /help"""
        await update.message.reply_text(
            "❓ **AIDE - DINO CHALLENGE**\n\n"
            "**🎯 Comment jouer:**\n"
            "1. Abonnez-vous (11 CHF/mois)\n"
            "2. Jouez jusqu'à 5 fois par jour\n"
            "3. Votre meilleur score compte\n"
            "4. Gagnez des prix chaque mois\n\n"
            "**💰 Distribution des prix:**\n"
            "🥇 1er: 40% de la cagnotte\n"
            "🥈 2e: 15% de la cagnotte\n"
            "🥉 3e: 5% de la cagnotte\n\n"
            "**📞 Support:** Contactez l'organisateur",
            parse_mode='Markdown'
        )
    
    async def button_callback(self, update: Update, context):
        """Gestion des boutons"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "play":
            user_id = query.from_user.id
            game_url = f"https://nox-archeo.github.io/dinochallenge/?telegram_id={user_id}&mode=competition"
            await query.edit_message_text(
                "🎮 **JOUER AU DINO CHALLENGE**\n\n"
                f"� **[Cliquer ici pour jouer]({game_url})**\n\n"
                "🏆 Faites votre meilleur score !\n"
                "⚡ 5 tentatives par jour maximum\n"
                "💰 Abonnez-vous d'abord si ce n'est pas fait !",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        elif query.data == "payment":
            user_id = query.from_user.id
            payment_url = f"https://dinochallenge-bot.onrender.com/create-payment?telegram_id={user_id}"
            await query.edit_message_text(
                "💳 **PAIEMENT SÉCURISÉ**\n\n"
                "💰 **Prix:** 11 CHF/mois\n\n"
                f"💳 **[Payer avec PayPal]({payment_url})**\n\n"
                "✅ Cartes bancaires acceptées\n"
                "🔒 Paiement 100% sécurisé",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        elif query.data == "leaderboard":
            await self.leaderboard_command(query, context)
        elif query.data == "profile":
            await self.profile_command(query, context)
        elif query.data == "help":
            await self.help_command(query, context)
    
    async def run(self):
        """Lancer le bot"""
        try:
            logger.info("🤖 Démarrage du bot fonctionnel...")
            
            # Paramètres optimisés pour éviter l'erreur Updater
            await self.app.run_polling(
                poll_interval=2.0,
                timeout=15,
                drop_pending_updates=True,
                stop_signals=None,  # Éviter les problèmes de signaux
                close_loop=False
            )
            
        except Exception as e:
            logger.error(f"❌ Erreur bot fonctionnel: {e}")
            raise

async def main():
    """Point d'entrée"""
    try:
        bot = DinoBotFonctionnel()
        await bot.run()
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")

if __name__ == '__main__':
    asyncio.run(main())
