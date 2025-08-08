#!/usr/bin/env python3
"""
Bot Telegram séparé - Production
"""
import asyncio
import os
import sys

# Importer la configuration depuis app.py
from app import setup_telegram_bot, setup_bot_commands, logger

async def main():
    """Lancer uniquement le bot Telegram"""
    try:
        logger.info("🤖 Démarrage du bot Telegram en mode production")
        
        app = setup_telegram_bot()
        if app:
            await setup_bot_commands()
            logger.info("🚀 Bot Telegram configuré - démarrage polling...")
            
            # Démarrage du polling avec gestion d'erreur améliorée
            await app.run_polling(
                poll_interval=1.0,
                timeout=10,
                bootstrap_retries=-1,
                read_timeout=6.0,
                write_timeout=6.0,
                connect_timeout=7.0,
                pool_timeout=1.0,
                drop_pending_updates=True,
                close_loop=False
            )
        else:
            logger.error("❌ Impossible de configurer le bot Telegram")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt du bot demandé")
    except Exception as e:
        logger.error(f"❌ Erreur fatale bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
