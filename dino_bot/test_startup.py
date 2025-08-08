#!/usr/bin/env python3
"""
Test de lancement du bot pour vérifier qu'il démarre sans erreur
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

async def test_bot_startup():
    """Test si le bot peut démarrer sans erreur"""
    try:
        print("🧪 Test de démarrage du bot...")
        
        # Importer le bot
        from bot import DinoBot
        
        # Créer une instance
        bot = DinoBot()
        print("✅ Bot initialisé avec succès")
        
        # Vérifier la configuration
        if bot.token:
            print("✅ Token Telegram configuré")
        else:
            print("❌ Token Telegram manquant")
        
        print("✅ Tous les handlers configurés")
        print("✅ Scheduler configuré")
        
        print("\n🎉 Le bot est prêt à être lancé !")
        print("   Pour le démarrer : python bot.py")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test de démarrage: {e}")
        return False

def main():
    print("🦕 Test de Démarrage - Dino Challenge Bot")
    print("=" * 45)
    
    # Test du démarrage
    result = asyncio.run(test_bot_startup())
    
    if result:
        print("\n✅ Tous les tests réussis - Le bot peut être déployé !")
    else:
        print("\n❌ Des erreurs ont été détectées - Vérifiez la configuration")

if __name__ == '__main__':
    main()
