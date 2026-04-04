#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import psycopg2

# Configuration base de données
DATABASE_URL = 'postgresql://dinochallenge_db_user:aa3SYFKmJBvq88GedqvZa2tNOKboberh@dpg-d2auslruibrs73f350tg-a.frankfurt-postgres.render.com/dinochallenge_db'

def update_fake_names():
    """Mettre à jour les noms des joueurs fictifs avec les vrais noms"""
    
    # Les nouveaux noms à utiliser
    real_names = [
        "Tom",
        "alex", 
        "predator",
        "choupinette",
        "Sirius",
        "Nico",
        "champi",
        "Romain Demierre",
        "Koala",
        "kkkk"
    ]
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("✏️ MISE À JOUR DES NOMS FICTIFS")
        print("="*40)
        
        # Mettre à jour chaque joueur fictif
        for i, name in enumerate(real_names):
            telegram_id = 900000000 + i
            
            cursor.execute("""
                UPDATE users 
                SET display_name = %s, first_name = %s
                WHERE telegram_id = %s
            """, (name, name, telegram_id))
            
            print(f"{i+1}. ID {telegram_id} → {name}")
        
        conn.commit()
        print(f"\n✅ {len(real_names)} noms mis à jour avec succès !")
        print("🏆 Les nouveaux noms apparaîtront dans le classement")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    update_fake_names()