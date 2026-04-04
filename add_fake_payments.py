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

def add_fake_payments():
    """Ajouter des paiements fictifs pour que les joueurs fictifs apparaissent dans le classement"""
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("💳 AJOUT DE PAIEMENTS FICTIFS POUR LE CLASSEMENT")
        print("="*50)
        
        current_month = datetime.now().strftime('%Y-%m')
        
        # Récupérer les IDs des joueurs fictifs (commençant par 900000000)
        cursor.execute("""
            SELECT telegram_id, display_name FROM users 
            WHERE telegram_id >= 900000000 AND telegram_id < 900000010
        """)
        
        fake_players = cursor.fetchall()
        
        for i, (telegram_id, display_name) in enumerate(fake_players):
            # Date de paiement fictive (dans les derniers jours)
            days_ago = random.randint(1, 15)
            payment_date = datetime.now() - timedelta(days=days_ago)
            
            print(f"{i+1}. 💰 {display_name} → Paiement de 11.00 CHF")
            
            # Ajouter un paiement fictif
            cursor.execute("""
                INSERT INTO payments (telegram_id, amount, status, payment_type, month_year)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (telegram_id, Decimal('11.00'), 'completed', 'fake_player', current_month))
            
        conn.commit()
        print(f"\n✅ Paiements fictifs ajoutés pour {len(fake_players)} joueurs")
        print("🏆 Ils apparaîtront maintenant dans le classement payant !")
        print("💰 La cagnotte sera maintenant plus attractive")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    add_fake_payments()