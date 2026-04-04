#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import psycopg2
import random
from datetime import datetime, timedelta
from decimal import Decimal

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('❌ DATABASE_URL non définie dans les variables d\'environnement')
    exit(1)

def create_fake_players():
    """Créer 10 joueurs fictifs avec des scores entre 800-1000"""
    
    # Noms fictifs plausibles
    fake_players = [
        {"name": "Alex", "username": "AlexGamer92"},
        {"name": "Mia", "username": "MiaRunner"},
        {"name": "Lucas", "username": "LucasSpeed"},
        {"name": "Emma", "username": "EmmaJumper"},
        {"name": "Noah", "username": "NoahRush"},
        {"name": "Sophie", "username": "SophieQuick"},
        {"name": "Leo", "username": "LeoFast"},
        {"name": "Chloe", "username": "ChloeBoost"},
        {"name": "Tom", "username": "TomDash"},
        {"name": "Zoe", "username": "ZoeLeap"}
    ]
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("🎮 CRÉATION DE 10 JOUEURS FICTIFS")
        print("="*50)
        
        current_month = datetime.now().strftime('%Y-%m')
        
        for i, player in enumerate(fake_players):
            # Générer un ID Telegram fictif (commençant par 9 pour les différencier)
            fake_telegram_id = 900000000 + i
            
            # Score aléatoire entre 800-1000
            score = random.randint(800, 1000)
            
            # Date d'inscription fictive (dans les dernières semaines)
            days_ago = random.randint(7, 30)
            registration_date = datetime.now() - timedelta(days=days_ago)
            
            # Date de score fictive (dans les derniers jours)
            score_days_ago = random.randint(1, 7)
            score_date = datetime.now() - timedelta(days=score_days_ago)
            
            print(f"{i+1}. 👤 {player['name']} (@{player['username']})")
            print(f"   🎯 Score: {score} points")
            print(f"   📅 Inscrit il y a {days_ago} jours")
            
            # Insérer l'utilisateur
            cursor.execute("""
                INSERT INTO users (telegram_id, username, first_name, display_name, registration_date)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (telegram_id) DO NOTHING
            """, (fake_telegram_id, player['username'], player['name'], player['name'], registration_date))
            
            # Insérer le score
            cursor.execute("""
                INSERT INTO scores (telegram_id, score, month_year, created_at)
                VALUES (%s, %s, %s, %s)
            """, (fake_telegram_id, score, current_month, score_date))
            
        conn.commit()
        print("\n✅ 10 joueurs fictifs créés avec succès !")
        print("🏆 Ils apparaîtront dans le classement automatiquement")
        print("⚡ Les vrais joueurs pourront les dépasser normalement")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    create_fake_players()