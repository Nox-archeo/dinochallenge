#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import psycopg2
from datetime import datetime, timedelta

# Configuration base de données
DATABASE_URL = 'postgresql://dinochallenge_db_user:aa3SYFKmJBvq88GedqvZa2tNOKboberh@dpg-d2auslruibrs73f350tg-a.frankfurt-postgres.render.com/dinochallenge_db'

def get_inscriptions_today():
    """Récupérer les inscriptions d'aujourd'hui avec l'heure exacte"""
    try:
        # Connexion
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Aujourd'hui en format string 
        today = datetime.now().strftime('%Y-%m-%d')
        
        print(f"🔍 RECHERCHE DES INSCRIPTIONS DU {today}")
        print("="*60)
        
        # Requête pour avoir tous les utilisateurs d'aujourd'hui avec l'heure précise
        cursor.execute("""
            SELECT 
                display_name,
                telegram_id, 
                username,
                registration_date,
                paypal_email
            FROM users 
            WHERE DATE(registration_date) = %s
            ORDER BY registration_date DESC
        """, (today,))
        
        results = cursor.fetchall()
        
        if not results:
            print("❌ Aucune inscription aujourd'hui")
            return
        
        print(f"✅ {len(results)} INSCRIPTION(S) AUJOURD'HUI:")
        print("="*60)
        
        for i, user in enumerate(results, 1):
            display_name = user[0] or "Nom non défini"
            telegram_id = user[1]
            username = user[2] or "N/A"
            registration_date = user[3]
            paypal_email = user[4] or "Pas d'email"
            
            # Formatage de l'heure précise
            if registration_date:
                heure_exacte = registration_date.strftime('%H:%M:%S')
                date_formatee = registration_date.strftime('%d/%m/%Y')
            else:
                heure_exacte = "Heure inconnue"
                date_formatee = "Date inconnue"
            
            print(f"\n{i}. 👤 {display_name}")
            print(f"   🆔 ID Telegram: {telegram_id}")
            print(f"   👤 Username: @{username}")
            print(f"   📅 Date: {date_formatee}")
            print(f"   🕒 Heure EXACTE: {heure_exacte}")
            print(f"   💰 PayPal: {paypal_email}")
        
        print("\n" + "="*60)
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    get_inscriptions_today()