#!/usr/bin/env python3
"""
Script pour récupérer votre ID Telegram
"""

import os
from telegram import Bot
import asyncio

async def get_telegram_id():
    """Récupère votre ID Telegram"""
    
    # Récupérer le token du bot
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN non défini dans les variables d'environnement")
        return
    
    print("🤖 Connexion au bot Telegram...")
    bot = Bot(token=token)
    
    try:
        # Obtenir les informations du bot
        bot_info = await bot.get_me()
        print(f"✅ Bot connecté: @{bot_info.username}")
        
        print("\n📱 INSTRUCTIONS:")
        print("1. Envoyez un message privé à votre bot Telegram")
        print("2. Tapez n'importe quoi (ex: /start)")
        print("3. Puis relancez ce script")
        print("\n🔍 Recherche des messages récents...")
        
        # Obtenir les dernières mises à jour
        updates = await bot.get_updates(limit=10)
        
        if updates:
            print(f"\n✅ {len(updates)} messages trouvés:")
            for update in updates:
                if update.message:
                    user = update.message.from_user
                    print(f"👤 {user.first_name} ({user.username}): ID = {user.id}")
            
            # Prendre le dernier utilisateur
            last_user = updates[-1].message.from_user
            print(f"\n🎯 VOTRE ID TELEGRAM: {last_user.id}")
            print(f"💡 Ajoutez cette ligne à vos variables d'environnement:")
            print(f"export ORGANIZER_CHAT_ID={last_user.id}")
            
        else:
            print("❌ Aucun message trouvé.")
            print("Envoyez un message à votre bot d'abord!")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    asyncio.run(get_telegram_id())
