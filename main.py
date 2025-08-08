#!/usr/bin/env python3
"""
Point d'entrée principal - Production 2025
Version moderne avec architecture async
"""
import os
import subprocess
import sys
import threading
import time
import asyncio

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
            """Démarrer le bot Telegram - Version production 2025"""
            try:
                # Essayer le bot 2025 moderne (compatible async)
                print("🚀 Tentative bot 2025 (architecture moderne)...")
                import bot_2025
                asyncio.run(bot_2025.main())
                
            except Exception as e:
                print(f"❌ Erreur Bot 2025: {e}")
                
                # Fallback vers bot fonctionnel
                print("🔄 Tentative bot fonctionnel...")
                try:
                    import bot_fonctionnel
                    asyncio.run(bot_fonctionnel.main())
                except Exception as e2:
                    print(f"❌ Erreur Bot fonctionnel: {e2}")
                    
                    # En dernier recours, bot minimal
                    print("🔄 Fallback vers bot minimal...")
                    try:
                        import bot_minimal
                        asyncio.run(bot_minimal.main())
                    except Exception as e3:
                        print(f"❌ Erreur Bot minimal: {e3}")
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
            import bot_2025
            asyncio.run(bot_2025.main())
        except Exception as e:
            print(f"❌ Erreur Bot: {e}")
            sys.exit(1)
else:
    print("🔧 Mode développement local")
    import bot_2025
    asyncio.run(bot_2025.main())
