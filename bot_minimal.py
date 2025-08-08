#!/usr/bin/env python3
"""
Bot Telegram minimal pour test - Production
"""
import asyncio
import os
import logging
from telegram.ext import Application

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Test minimal du bot"""
    try:
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            logger.error("❌ TELEGRAM_BOT_TOKEN manquant")
            return
            
        logger.info("🤖 Création du bot minimal...")
        
        # Créer l'application de manière très simple
        app = Application.builder().token(token).build()
        
        logger.info("🚀 Démarrage du polling minimal...")
        
        # Test avec paramètres minimaux
        await app.run_polling(
            poll_interval=2.0,
            timeout=30,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur bot minimal: {e}")
        logger.exception("Détails de l'erreur:")

if __name__ == '__main__':
    asyncio.run(main())
