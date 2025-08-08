#!/usr/bin/env python3
"""
Point d'entrée principal - Production
En production, on lance soit l'API soit le Bot selon la configuration
"""
import os

if os.environ.get('RENDER'):
    # En production Render - lancer selon le type de service
    if os.environ.get('PORT'):
        # Service Web - API Flask
        print("🌐 Mode production - démarrage API Flask via Gunicorn")
        from wsgi import application
    else:
        # Service Worker - Bot Telegram
        print("🤖 Mode production - démarrage Bot Telegram")
        import telegram_bot
else:
    # Développement local - lancer les deux
    print("🔧 Mode développement - démarrage complet")
    import app
    app.main()
