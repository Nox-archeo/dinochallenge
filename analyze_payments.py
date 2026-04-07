import psycopg2
import os

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('❌ DATABASE_URL non définie dans les variables d\'environnement')
    exit(1)

def analyze_payments():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print('💰 ANALYSE DES PAIEMENTS AVRIL 2026:')
        print('=' * 50)
        
        # Voir tous les paiements d'avril 2026
        cursor.execute("""
            SELECT user_id, telegram_id, amount, status 
            FROM payments 
            WHERE month_year = '2026-04'
            ORDER BY user_id
        """)
        payments = cursor.fetchall()
        
        total = 0
        real_users = 0
        fake_users = 0
        
        for payment in payments:
            user_type = 'FAKE' if payment[1] >= 900000000 and payment[1] <= 900000009 else 'REAL'
            print(f'User ID: {payment[0]}, Telegram ID: {payment[1]}, Montant: {payment[2]} CHF, Type: {user_type}')
            
            if payment[3] == 'completed':
                total += float(payment[2])
                if user_type == 'FAKE':
                    fake_users += 1
                else:
                    real_users += 1
        
        print('=' * 50)
        print(f'TOTAL CALCULÉ: {total} CHF')
        print(f'PAIEMENTS RÉELS: {real_users}')
        print(f'PAIEMENTS FICTIFS: {fake_users}')
        print(f'TOTAL PAIEMENTS: {len(payments)}')
        
        # Calculer ce que ça devrait être
        expected = (real_users + fake_users) * 5.0
        print(f'ATTENDU (11 x 5 CHF): {expected} CHF')
        print(f'DIFFÉRENCE: {total - expected} CHF')
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    analyze_payments()