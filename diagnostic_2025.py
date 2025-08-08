#!/usr/bin/env python3
"""
Diagnostic pour Bot Telegram 2025
Test de compatibilité moderne
"""
import os
import sys
import asyncio
import logging

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_telegram_bot():
    """Test du bot Telegram moderne"""
    try:
        print("🔍 TEST BOT TELEGRAM 2025")
        print("=" * 50)
        
        # 1. Variables d'environnement
        print("1️⃣ Variables d'environnement :")
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if token:
            print(f"   ✅ TELEGRAM_BOT_TOKEN : {token[:10]}...{token[-10:]}")
        else:
            print("   ❌ TELEGRAM_BOT_TOKEN manquant")
            return False
        
        # 2. Test des importations
        print("2️⃣ Test des importations :")
        try:
            import telegram
            print(f"   ✅ telegram : {telegram.__version__}")
            
            from telegram.ext import Application
            print("   ✅ telegram.ext.Application : OK")
            
            from telegram import Update
            from telegram.ext import ContextTypes
            print("   ✅ Types Telegram : OK")
            
        except ImportError as e:
            print(f"   ❌ Erreur import : {e}")
            return False
        
        # 3. Test création Application moderne
        print("3️⃣ Test création Application moderne :")
        try:
            application = Application.builder().token(token).build()
            print("   ✅ Application créée avec succès")
            
            # Test initialisation
            await application.initialize()
            print("   ✅ Application initialisée")
            
            # Nettoyage
            await application.shutdown()
            print("   ✅ Application fermée proprement")
            
        except Exception as e:
            print(f"   ❌ Erreur Application : {e}")
            return False
        
        # 4. Test base de données
        print("4️⃣ Test base de données :")
        db_url = os.environ.get('DATABASE_URL')
        if db_url:
            print(f"   ✅ DATABASE_URL configurée")
            try:
                import psycopg3
                print("   ✅ psycopg3 disponible")
                
                # Test connexion
                conn = psycopg3.connect(db_url)
                conn.close()
                print("   ✅ Connexion BDD réussie")
                
            except Exception as e:
                print(f"   ⚠️ Erreur BDD : {e}")
        else:
            print("   ⚠️ DATABASE_URL non configurée")
        
        # 5. Test PayPal
        print("5️⃣ Test PayPal :")
        paypal_id = os.environ.get('PAYPAL_CLIENT_ID')
        paypal_secret = os.environ.get('PAYPAL_CLIENT_SECRET')
        
        if paypal_id and paypal_secret:
            print("   ✅ PayPal configuré")
            try:
                import paypalrestsdk
                print("   ✅ paypalrestsdk disponible")
            except ImportError:
                print("   ⚠️ paypalrestsdk non installé")
        else:
            print("   ⚠️ PayPal non configuré")
        
        print("=" * 50)
        print("✅ DIAGNOSTIC RÉUSSI - Bot 2025 prêt !")
        return True
        
    except Exception as e:
        print(f"❌ ERREUR DIAGNOSTIC : {e}")
        return False

def diagnose():
    """Lancer le diagnostic synchrone"""
    return asyncio.run(test_telegram_bot())

if __name__ == "__main__":
    success = diagnose()
    sys.exit(0 if success else 1)
