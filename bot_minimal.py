#!/usr/bin/env python3
"""
Bot Telegram ultra-minimal pour test - Production
"""
import asyncio
import os
import logging
from telegram.ext import Application, CommandHandler

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start_command(update, context):
    """Commande /start simple"""
    await update.message.reply_text(
        "🦕 Dino Challenge Bot opérationnel!\n"
        "🔧 Mode maintenance - fonctionnalités limitées"
    )

async def main():
    """Test ultra-minimal du bot"""
    try:
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            logger.error("❌ TELEGRAM_BOT_TOKEN manquant")
            return
            
        logger.info("🤖 Création du bot ultra-minimal...")
        
        # Créer l'application de manière très basique
        app = Application.builder().token(token).build()
        
        # Ajouter seulement une commande /start
        app.add_handler(CommandHandler("start", start_command))
        
        logger.info("🚀 Démarrage du polling ultra-minimal...")
        
        # Paramètres ultra-conservateurs
        await app.run_polling(
            poll_interval=3.0,
            timeout=20,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur bot ultra-minimal: {e}")
        logger.exception("Détails de l'erreur:")
        
        # Essayer une version encore plus basique
        try:
            logger.info("🔄 Tentative version basique sans handlers...")
            app = Application.builder().token(token).build()
            await app.run_polling(drop_pending_updates=True)
        except Exception as e2:
            logger.error(f"❌ Erreur version basique: {e2}")

if __name__ == '__main__':
    asyncio.run(main())
