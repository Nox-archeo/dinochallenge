import psycopg2
import os

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('❌ DATABASE_URL non définie dans les variables d\'environnement')
    exit(1)

def check_fake_users():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Voir les utilisateurs avec ID >= 900000000
        cursor.execute("""
            SELECT telegram_id, first_name 
            FROM users 
            WHERE telegram_id >= 900000000 
            ORDER BY telegram_id
        """)
        fake_users = cursor.fetchall()
        
        print("🤖 UTILISATEURS AVEC ID >= 900000000:")
        print("=" * 60)
        for user in fake_users:
            print(f"ID: {user[0]} | Nom: {user[1]}")
        
        print(f"\n📊 TOTAL: {len(fake_users)} utilisateurs")
        
        # Voir tous les IDs pour comprendre
        cursor.execute("SELECT MIN(telegram_id), MAX(telegram_id), COUNT(*) FROM users")
        result = cursor.fetchone()
        print(f"\n📈 PLAGE D'IDS: Min={result[0]}, Max={result[1]}, Total={result[2]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    check_fake_users()