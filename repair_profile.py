#!/usr/bin/env python3
"""
SCRIPT DE RÉPARATION URGENTE - PROFIL MARGAUX
Répare le profil utilisateur 5932296330 sans toucher aux scores
"""

import os
import psycopg2
from urllib.parse import urlparse

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://default:iIQmdHNMT0Rt@ep-orange-tree-a2vpbfig-pooler.eu-central-1.aws.neon.tech:5432/verceldb?sslmode=require')

def repair_profile():
    try:
        # Connexion à la base
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Vérifier l'utilisateur actuel
        cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (5932296330,))
        user = cursor.fetchone()
        print(f"Utilisateur actuel: {user}")
        
        # Vérifier les scores
        cursor.execute("SELECT * FROM scores WHERE telegram_id = %s ORDER BY score DESC", (5932296330,))
        scores = cursor.fetchall()
        print(f"Scores trouvés: {len(scores)} scores")
        for score in scores[:3]:
            print(f"  - Score: {score}")
        
        # Réparer le profil
        cursor.execute("""
            UPDATE users 
            SET display_name = %s, 
                paypal_email = %s,
                has_paid_current_month = TRUE
            WHERE telegram_id = %s
        """, ("margaux", "seb.chappss@gmail.com", 5932296330))
        
        conn.commit()
        print("✅ Profil réparé !")
        
        # Vérifier après réparation
        cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (5932296330,))
        user_fixed = cursor.fetchone()
        print(f"Utilisateur après réparation: {user_fixed}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    repair_profile()
