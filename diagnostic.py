#!/usr/bin/env python3
"""
Diagnostic Telegram Bot - Identifier le problème
"""
import os
import sys

def diagnose():
    """Diagnostic complet du problème"""
    print("🔍 DIAGNOSTIC TELEGRAM BOT")
    print("=" * 50)
    
    # 1. Vérifier les variables d'environnement
    print("1️⃣ Variables d'environnement:")
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if token:
        print(f"   ✅ TELEGRAM_BOT_TOKEN: {token[:10]}...{token[-10:]}")
    else:
        print("   ❌ TELEGRAM_BOT_TOKEN: MANQUANT")
        return
    
    # 2. Vérifier les imports
    print("\n2️⃣ Test des imports:")
    try:
        import telegram
        print(f"   ✅ telegram: {telegram.__version__}")
    except Exception as e:
        print(f"   ❌ telegram: {e}")
        return
        
    try:
        from telegram.ext import Application
        print("   ✅ telegram.ext.Application: OK")
    except Exception as e:
        print(f"   ❌ telegram.ext.Application: {e}")
        return
    
    # 3. Test création Application
    print("\n3️⃣ Test création Application:")
    try:
        app = Application.builder().token(token).build()
        print("   ✅ Application créée avec succès")
    except Exception as e:
        print(f"   ❌ Erreur création Application: {e}")
        return
    
    # 4. Test basique polling
    print("\n4️⃣ Test polling (5 secondes):")
    try:
        import asyncio
        
        async def test_polling():
            try:
                print("   🚀 Démarrage polling...")
                # Test très court
                await asyncio.wait_for(
                    app.run_polling(drop_pending_updates=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                print("   ✅ Polling OK - timeout normal")
            except Exception as e:
                print(f"   ❌ Erreur polling: {e}")
                print(f"   📝 Type d'erreur: {type(e)}")
        
        asyncio.run(test_polling())
        
    except Exception as e:
        print(f"   ❌ Erreur test polling: {e}")
    
    print("\n🏁 Diagnostic terminé")

if __name__ == '__main__':
    diagnose()
