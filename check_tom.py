import psycopg2
import os

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('❌ DATABASE_URL non définie dans les variables d\'environnement')
    exit(1)

def check_tom_status():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("🤖 VÉRIFICATION DE TOM (ID: 900000000)")
        print("=" * 50)
        
        # Vérifier si Tom existe
        cursor.execute("SELECT telegram_id, first_name FROM users WHERE telegram_id = 900000000")
        tom_user = cursor.fetchone()
        if tom_user:
            print(f"✅ Tom existe: ID {tom_user[0]}, Nom: {tom_user[1]}")
        else:
            print("❌ Tom n'existe pas dans users")
            
        # Vérifier si Tom a payé
        cursor.execute("SELECT user_id, amount FROM payments WHERE user_id = 900000000")
        tom_payment = cursor.fetchone()
        if tom_payment:
            print(f"💰 Tom a payé: {tom_payment[1]} CHF")
        else:
            print("💰 Tom n'a PAS payé")
            
        # Vérifier si Tom a un score
        cursor.execute("SELECT player_id, best_score FROM scores WHERE player_id = 900000000")
        tom_score = cursor.fetchone()
        if tom_score:
            print(f"🎯 Score de Tom: {tom_score[1]} pts")
        else:
            print("🎯 Tom n'a PAS de score")
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    check_tom_status()