#!/usr/bin/env python3
"""
Point d'entrée principal - Production
Lancement intelligent selon la plateforme
"""
import os
import subprocess
import sys
import threading
import time

if os.environ.get('RENDER'):
    print("🏭 Mode production Render détecté")
    
    if os.environ.get('PORT'):
        print("🌐 Service Web - Démarrage API Flask + Bot Telegram")
        
        # En production, lancer à la fois l'API et le Bot dans le même processus
        def start_api():
            """Démarrer l'API Flask avec Gunicorn en arrière-plan"""
            port = os.environ.get('PORT', '5000')
            try:
                subprocess.Popen([
                    'gunicorn', 
                    'wsgi:application',
                    '--bind', f'0.0.0.0:{port}',
                    '--workers', '1',
                    '--timeout', '120',
                    '--log-level', 'info'
                ])
                print(f"✅ API Gunicorn démarrée sur le port {port}")
            except Exception as e:
                print(f"❌ Erreur Gunicorn: {e}")
        
        def start_bot():
            """Démarrer le bot Telegram"""
            try:
                import app
                app.main()
            except Exception as e:
                print(f"❌ Erreur Bot: {e}")
                sys.exit(1)
        
        # Démarrer l'API en arrière-plan
        api_thread = threading.Thread(target=start_api, daemon=True)
        api_thread.start()
        
        # Attendre un peu que l'API démarre
        time.sleep(3)
        print("✅ API démarrée, lancement du bot...")
        
        # Démarrer le bot en premier plan
        start_bot()
        
    else:
        print("🤖 Service Worker - Bot Telegram seulement")
        try:
            import telegram_bot
        except Exception as e:
            print(f"❌ Erreur Bot: {e}")
            sys.exit(1)
else:
    print("🔧 Mode développement local")
    import app
    app.main()
