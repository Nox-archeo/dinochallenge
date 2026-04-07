import psycopg2
import os
from decimal import Decimal

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('❌ DATABASE_URL non définie dans les variables d\'environnement')
    exit(1)

def add_tom_payment():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Ajouter un paiement pour Tom (ID=14)
        cursor.execute("""
            INSERT INTO payments (user_id, telegram_id, amount, status, month_year) 
            VALUES (14, 900000000, 5.00, 'completed', '2026-04')
        """)
        
        conn.commit()
        print("✅ Paiement ajouté pour Tom (5.00 CHF)")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    add_tom_payment()