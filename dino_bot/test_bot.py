#!/usr/bin/env python3
"""
Script de test pour vérifier les fonctionnalités du Dino Bot
"""

import os
import sys
import json
from datetime import datetime

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_data_files():
    """Test la création et lecture des fichiers de données"""
    print("🧪 Test des fichiers de données...")
    
    files_to_check = [
        'data/users.json',
        'data/scores.json', 
        'data/payments.json'
    ]
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                print(f"  ✅ {file_path} - OK ({len(data)} éléments)")
            except Exception as e:
                print(f"  ❌ {file_path} - Erreur: {e}")
        else:
            print(f"  ❌ {file_path} - Fichier manquant")

def test_services():
    """Test les services principaux"""
    print("\n🧪 Test des services...")
    
    try:
        from services.user_manager import UserManager
        user_manager = UserManager()
        print("  ✅ UserManager - OK")
        
        from services.score_manager import ScoreManager
        score_manager = ScoreManager()
        print("  ✅ ScoreManager - OK")
        
        from services.game_manager import GameManager
        game_manager = GameManager()
        print("  ✅ GameManager - OK")
        
        from services.paypal import PayPalService
        paypal_service = PayPalService()
        print("  ✅ PayPalService - OK")
        
    except Exception as e:
        print(f"  ❌ Erreur d'import des services: {e}")

def test_user_flow():
    """Test du flux utilisateur complet"""
    print("\n🧪 Test du flux utilisateur...")
    
    try:
        from services.user_manager import UserManager
        from services.score_manager import ScoreManager
        from services.game_manager import GameManager
        
        user_manager = UserManager()
        score_manager = ScoreManager()
        game_manager = GameManager()
        
        # Test utilisateur
        test_user_id = 999999
        test_username = "TestUser"
        
        # 1. Enregistrement
        if user_manager.register_user(test_user_id, test_username):
            print("  ✅ Enregistrement utilisateur - OK")
        else:
            print("  ⚠️ Utilisateur déjà existant")
        
        # 2. Activation abonnement
        if user_manager.activate_subscription(test_user_id):
            print("  ✅ Activation abonnement - OK")
        else:
            print("  ❌ Erreur activation abonnement")
        
        # 3. Vérifier l'abonnement
        has_subscription = user_manager.has_valid_subscription(test_user_id)
        print(f"  ✅ Statut abonnement: {'Actif' if has_subscription else 'Inactif'}")
        
        # 4. Test de jeu
        can_play = game_manager.can_user_play(test_user_id)
        if can_play['can_play']:
            print("  ✅ Vérification jeu autorisé - OK")
            
            # 5. Soumission de score
            result = game_manager.submit_score(test_user_id, test_username, 1500)
            if result['success']:
                print("  ✅ Soumission score - OK")
            else:
                print(f"  ❌ Erreur score: {result['message']}")
        else:
            print(f"  ⚠️ Jeu refusé: {can_play['reason']}")
        
        # 6. Vérification classement
        stats = game_manager.get_game_stats(test_user_id)
        print(f"  ✅ Statistiques - Meilleur score: {stats['best_score']}")
        
        print(f"  📊 Résumé du test utilisateur:")
        print(f"     - Abonnement: {'✅' if has_subscription else '❌'}")
        print(f"     - Peut jouer: {'✅' if can_play['can_play'] else '❌'}")
        print(f"     - Tentatives restantes: {stats['attempts_remaining']}")
        
    except Exception as e:
        print(f"  ❌ Erreur dans le flux: {e}")

def test_environment():
    """Test des variables d'environnement"""
    print("\n🧪 Test de l'environnement...")
    
    required_vars = [
        'TELEGRAM_BOT_TOKEN',
        'PAYPAL_CLIENT_ID', 
        'PAYPAL_SECRET_KEY',
        'GAME_URL'
    ]
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Masquer les secrets partiellement
            if 'TOKEN' in var or 'SECRET' in var:
                display_value = value[:8] + "..."
            else:
                display_value = value
            print(f"  ✅ {var} = {display_value}")
        else:
            print(f"  ❌ {var} - Non défini")

def main():
    """Fonction principale de test"""
    print("🦕 Test du Dino Challenge Bot")
    print("=" * 40)
    
    # Charger les variables d'environnement
    from dotenv import load_dotenv
    load_dotenv()
    
    test_environment()
    test_data_files()
    test_services()
    test_user_flow()
    
    print("\n" + "=" * 40)
    print("✅ Tests terminés !")
    print("\n💡 Pour lancer le bot:")
    print("   python bot.py")
    print("\n📝 Commandes de test dans Telegram:")
    print("   /start")
    print("   /score 1500")
    print("   /leaderboard")

if __name__ == '__main__':
    main()
