#!/usr/bin/env python3
"""
DINO CHALLENGE - Visualiseur d'utilisateurs
Script pour voir tous les utilisateurs inscrits dans la base PostgreSQL
"""

import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

def get_database_url():
    """Récupérer l'URL de la base de données"""
    # Essayer les variables d'environnement
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        # URL par défaut depuis repair_profile.py
        db_url = 'postgresql://default:iIQmdHNMT0Rt@ep-orange-tree-a2vpbfig-pooler.eu-central-1.aws.neon.tech:5432/verceldb?sslmode=require'
    return db_url

def connect_to_db():
    """Se connecter à la base PostgreSQL"""
    try:
        db_url = get_database_url()
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        print("✅ Connexion à PostgreSQL réussie!")
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return None

def get_all_users(conn):
    """Récupérer tous les utilisateurs"""
    try:
        cursor = conn.cursor()
        query = """
        SELECT 
            telegram_id,
            username,
            first_name,
            last_name,
            registration_date,
            premium_status,
            daily_games,
            total_games,
            high_score,
            last_payment_date
        FROM users 
        ORDER BY registration_date DESC
        """
        cursor.execute(query)
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des utilisateurs: {e}")
        return []

def get_user_stats(conn):
    """Récupérer les statistiques générales"""
    try:
        cursor = conn.cursor()
        
        # Nombre total d'utilisateurs
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']
        
        # Utilisateurs premium
        cursor.execute("SELECT COUNT(*) as premium FROM users WHERE premium_status = true")
        premium_users = cursor.fetchone()['premium']
        
        # Utilisateurs actifs (qui ont joué)
        cursor.execute("SELECT COUNT(*) as active FROM users WHERE total_games > 0")
        active_users = cursor.fetchone()['active']
        
        # Scores totaux
        cursor.execute("SELECT COUNT(*) as total_scores FROM scores")
        total_scores = cursor.fetchone()['total_scores']
        
        return {
            'total_users': total_users,
            'premium_users': premium_users,
            'active_users': active_users,
            'total_scores': total_scores
        }
    except Exception as e:
        print(f"❌ Erreur lors du calcul des statistiques: {e}")
        return None

def format_date(date_str):
    """Formater une date pour l'affichage"""
    if not date_str:
        return "N/A"
    try:
        if isinstance(date_str, str):
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            date_obj = date_str
        return date_obj.strftime("%d/%m/%Y %H:%M")
    except:
        return str(date_str)

def display_users(users, show_details=False):
    """Afficher la liste des utilisateurs"""
    if not users:
        print("❌ Aucun utilisateur trouvé")
        return
    
    print(f"\n📊 {len(users)} utilisateur(s) trouvé(s):")
    print("=" * 100)
    
    for i, user in enumerate(users, 1):
        status_icon = "💎" if user.get('premium_status') else "🆓"
        username = user.get('username') or "N/A"
        first_name = user.get('first_name') or "Anonyme"
        last_name = user.get('last_name') or ""
        full_name = f"{first_name} {last_name}".strip()
        
        print(f"\n{i}. {status_icon} {full_name} (@{username})")
        print(f"   🆔 Telegram ID: {user.get('telegram_id')}")
        print(f"   📅 Inscrit le: {format_date(user.get('registration_date'))}")
        print(f"   🎮 Parties: {user.get('total_games', 0)} (dont {user.get('daily_games', 0)} aujourd'hui)")
        print(f"   🏆 Meilleur score: {user.get('high_score', 0)}")
        
        if show_details and user.get('last_payment_date'):
            print(f"   💰 Dernier paiement: {format_date(user.get('last_payment_date'))}")

def main():
    """Fonction principale"""
    print("🦕 DINO CHALLENGE - Visualiseur d'utilisateurs")
    print("=" * 50)
    
    # Se connecter à la base
    conn = connect_to_db()
    if not conn:
        return
    
    try:
        # Afficher les statistiques générales
        print("\n📈 STATISTIQUES GÉNÉRALES:")
        stats = get_user_stats(conn)
        if stats:
            print(f"   👥 Total utilisateurs: {stats['total_users']}")
            print(f"   💎 Utilisateurs premium: {stats['premium_users']}")
            print(f"   🎮 Utilisateurs actifs: {stats['active_users']}")
            print(f"   🎯 Total scores enregistrés: {stats['total_scores']}")
        
        # Récupérer et afficher les utilisateurs
        users = get_all_users(conn)
        
        # Options d'affichage
        if len(sys.argv) > 1 and sys.argv[1] == "--details":
            display_users(users, show_details=True)
        else:
            display_users(users, show_details=False)
            print(f"\n💡 Utilisez --details pour plus d'informations")
        
        # Top scores
        try:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT u.first_name, u.username, u.high_score
            FROM users u 
            WHERE u.high_score > 0 
            ORDER BY u.high_score DESC 
            LIMIT 5
            """)
            top_scores = cursor.fetchall()
            
            if top_scores:
                print(f"\n🏆 TOP 5 SCORES:")
                for i, user in enumerate(top_scores, 1):
                    name = user.get('first_name') or user.get('username') or "Anonyme"
                    print(f"   {i}. {name}: {user.get('high_score')} points")
        except:
            pass
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
    finally:
        conn.close()
        print(f"\n✅ Connexion fermée")

if __name__ == "__main__":
    main()