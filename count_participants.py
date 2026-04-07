import psycopg2
import os
from datetime import datetime

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('❌ DATABASE_URL non définie dans les variables d\'environnement')
    exit(1)

def count_participants():
    try:
        # Connexion à la base de données
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Compter tous les utilisateurs (y compris les fakes)
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Compter les utilisateurs fakes (IDs spécifiques 900000000-900000009)
        cursor.execute("SELECT COUNT(*) FROM users WHERE telegram_id >= 900000000 AND telegram_id <= 900000009")
        fake_users = cursor.fetchone()[0]
        
        # Compter les utilisateurs réels (tous sauf les fakes)
        cursor.execute("SELECT COUNT(*) FROM users WHERE telegram_id < 900000000 OR telegram_id > 900000009")
        real_users = cursor.fetchone()[0]
        
        # Afficher les résultats
        print("🎮 STATISTIQUES PARTICIPANTS DINO CHALLENGE")
        print("=" * 50)
        print(f"👥 TOTAL PARTICIPANTS: {total_users}")
        print(f"✅ Vrais joueurs: {real_users}")
        print(f"🤖 Joueurs fictifs: {fake_users}")
        print("=" * 50)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    count_participants()