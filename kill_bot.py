#!/usr/bin/env python3
"""
Script d'arrêt d'urgence pour le bot Telegram
Utilise l'API Telegram pour forcer l'arrêt de toutes les instances
"""

import os
import requests
import time

# Récupérer le token depuis les variables d'environnement ou le définir directement
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'VOTRE_TOKEN_ICI')

def stop_all_bot_instances():
    """Arrêter toutes les instances du bot via l'API Telegram"""
    
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'VOTRE_TOKEN_ICI':
        print("❌ ERREUR: Token Telegram manquant!")
        print("💡 Ajoutez votre token dans le script ou comme variable d'environnement")
        return False
    
    print("🛑 ARRÊT D'URGENCE - Toutes les instances du bot")
    print("=" * 50)
    
    # 1. Récupérer les informations du bot
    try:
        response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe")
        if response.status_code == 200:
            bot_info = response.json()
            print(f"🤖 Bot trouvé: {bot_info['result']['username']}")
        else:
            print("❌ Impossible de contacter le bot")
            return False
    except Exception as e:
        print(f"❌ Erreur connexion: {e}")
        return False
    
    # 2. Arrêter le webhook (si configuré)
    try:
        print("🔄 Suppression du webhook...")
        response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
        if response.status_code == 200:
            print("✅ Webhook supprimé")
        else:
            print("⚠️ Pas de webhook à supprimer")
    except Exception as e:
        print(f"⚠️ Erreur suppression webhook: {e}")
    
    # 3. Récupérer et ignorer toutes les mises à jour en attente
    try:
        print("🧹 Nettoyage des mises à jour en attente...")
        
        # Récupérer toutes les mises à jour
        response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=100")
        
        if response.status_code == 200:
            updates = response.json().get('result', [])
            print(f"📦 {len(updates)} mises à jour trouvées")
            
            if updates:
                # Marquer toutes comme lues en utilisant le dernier offset + 1
                last_update_id = updates[-1]['update_id']
                response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id + 1}&limit=1")
                print("✅ Toutes les mises à jour marquées comme lues")
            else:
                print("✅ Aucune mise à jour en attente")
        else:
            print("⚠️ Impossible de récupérer les mises à jour")
            
    except Exception as e:
        print(f"⚠️ Erreur nettoyage: {e}")
    
    # 4. Effectuer plusieurs appels pour interrompre les connexions actives
    print("💥 Interruption forcée des connexions...")
    for i in range(5):
        try:
            # Appels simultanés pour surcharger et interrompre
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?timeout=1", timeout=2)
            time.sleep(0.5)
        except:
            pass
        print(f"🔄 Tentative {i+1}/5")
    
    print("=" * 50)
    print("✅ ARRÊT D'URGENCE TERMINÉ")
    print("💡 Toutes les instances du bot devraient maintenant être arrêtées")
    print("💡 Si le bot redémarre automatiquement, vérifiez:")
    print("   - Render.com (service suspendu ?)")
    print("   - GitHub Actions (workflows actifs ?)")
    print("   - Autres services cloud (Heroku, Railway, etc.)")
    print("   - Serveurs personnels ou VPS")
    
    return True

if __name__ == "__main__":
    stop_all_bot_instances()
