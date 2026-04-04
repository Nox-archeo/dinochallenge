#!/usr/bin/env python3
"""
DINO CHALLENGE - Visualiseur d'utilisateurs ADAPTÉ
Script pour voir tous les utilisateurs avec la vraie structure DB
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

def connect_to_db():
    """Se connecter à la base PostgreSQL"""
    try:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            print("❌ DATABASE_URL non définie")
            return None
            
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        print("✅ Connexion à PostgreSQL réussie!")
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return None

def get_all_users(conn):
    """Récupérer tous les utilisateurs avec leurs stats"""
    try:
        cursor = conn.cursor()
        
        # Requête adaptée à votre vraie structure
        query = """
        SELECT 
            u.id,
            u.telegram_id,
            u.username,
            u.first_name,
            u.email,
            u.paypal_email,
            u.registration_date,
            u.has_paid_current_month,
            u.total_attempts_today,
            u.last_attempt_date,
            u.display_name,
            -- Stats des scores
            COUNT(s.id) as total_games,
            MAX(s.score) as high_score,
            MIN(s.score) as low_score,
            AVG(s.score) as avg_score,
            -- Stats des paiements
            COUNT(p.id) as total_payments,
            SUM(p.amount) as total_paid
        FROM users u
        LEFT JOIN scores s ON u.telegram_id = s.telegram_id
        LEFT JOIN payments p ON u.telegram_id = p.telegram_id
        GROUP BY u.id, u.telegram_id, u.username, u.first_name, u.email, 
                 u.paypal_email, u.registration_date, u.has_paid_current_month, 
                 u.total_attempts_today, u.last_attempt_date, u.display_name
        ORDER BY u.registration_date DESC;
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
        
        # Total utilisateurs
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']
        
        # Utilisateurs payants ce mois
        cursor.execute("SELECT COUNT(*) as paid FROM users WHERE has_paid_current_month = true")
        paid_users = cursor.fetchone()['paid']
        
        # Utilisateurs avec email PayPal
        cursor.execute("SELECT COUNT(*) as with_paypal FROM users WHERE paypal_email IS NOT NULL")
        paypal_users = cursor.fetchone()['with_paypal']
        
        # Total scores
        cursor.execute("SELECT COUNT(*) as total_scores FROM scores")
        total_scores = cursor.fetchone()['total_scores']
        
        # Total paiements
        cursor.execute("SELECT COUNT(*) as payments, COALESCE(SUM(amount), 0) as revenue FROM payments")
        payment_stats = cursor.fetchone()
        
        return {
            'total_users': total_users,
            'paid_users': paid_users,
            'paypal_users': paypal_users,
            'total_scores': total_scores,
            'total_payments': payment_stats['payments'],
            'total_revenue': float(payment_stats['revenue'] or 0)
        }
    except Exception as e:
        print(f"❌ Erreur lors du calcul des statistiques: {e}")
        return None

def format_date(date_obj):
    """Formater une date pour l'affichage"""
    if not date_obj:
        return "N/A"
    try:
        if isinstance(date_obj, str):
            date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
        return date_obj.strftime("%d/%m/%Y %H:%M")
    except:
        return str(date_obj)

def display_users(users):
    """Afficher la liste des utilisateurs"""
    if not users:
        print("❌ Aucun utilisateur trouvé")
        return
    
    print(f"\n👥 {len(users)} UTILISATEUR(S) INSCRIT(S):")
    print("=" * 100)
    
    for i, user in enumerate(users, 1):
        # Status
        status_icon = "💰" if user.get('has_paid_current_month') else "🆓"
        paypal_icon = "📧" if user.get('paypal_email') else ""
        
        # Nom
        name = user.get('first_name') or "Anonyme"
        display_name = user.get('display_name')
        if display_name and display_name != name:
            name = f"{name} ({display_name})"
        
        username = user.get('username') or "N/A"
        
        print(f"\n{i}. {status_icon} {paypal_icon} {name}")
        print(f"   🆔 Telegram ID: {user.get('telegram_id')}")
        print(f"   👤 Username: @{username}")
        print(f"   📅 Inscrit le: {format_date(user.get('registration_date'))}")
        
        # Statut paiement
        if user.get('has_paid_current_month'):
            print(f"   💰 ✅ A payé ce mois")
        else:
            print(f"   💰 ❌ Pas encore payé ce mois")
        
        # Email PayPal
        if user.get('paypal_email'):
            print(f"   📧 PayPal: {user.get('paypal_email')}")
        
        # Stats de jeu
        total_games = user.get('total_games') or 0
        print(f"   🎮 Parties jouées: {total_games}")
        
        if total_games > 0:
            high_score = user.get('high_score') or 0
            avg_score = user.get('avg_score') or 0
            print(f"   🏆 Meilleur score: {high_score}")
            print(f"   📊 Score moyen: {avg_score:.1f}")
        
        # Stats paiements
        total_payments = user.get('total_payments') or 0
        total_paid = user.get('total_paid') or 0
        if total_payments > 0:
            print(f"   💵 Paiements: {total_payments} (total: {total_paid}€)")
        
        print(f"   📱 Tentatives aujourd'hui: {user.get('total_attempts_today') or 0}")

def main():
    """Fonction principale"""
    print("🦕 DINO CHALLENGE - Dashboard Utilisateurs")
    print("=" * 50)
    
    conn = connect_to_db()
    if not conn:
        return
    
    try:
        # Statistiques générales
        print("\n📈 STATISTIQUES GÉNÉRALES:")
        stats = get_user_stats(conn)
        if stats:
            print(f"   👥 Total utilisateurs: {stats['total_users']}")
            print(f"   💰 Payants ce mois: {stats['paid_users']}")
            print(f"   📧 Avec PayPal: {stats['paypal_users']}")
            print(f"   🎯 Total parties jouées: {stats['total_scores']}")
            print(f"   💵 Total paiements: {stats['total_payments']} ({stats['total_revenue']}€)")
        
        # Liste des utilisateurs
        users = get_all_users(conn)
        display_users(users)
        
        # Top scores
        print(f"\n🏆 TOP SCORES:")
        cursor = conn.cursor()
        cursor.execute("""
        SELECT u.first_name, u.username, s.score, s.created_at
        FROM users u
        JOIN scores s ON u.telegram_id = s.telegram_id
        ORDER BY s.score DESC 
        LIMIT 5
        """)
        top_scores = cursor.fetchall()
        
        if top_scores:
            for i, score in enumerate(top_scores, 1):
                name = score.get('first_name') or score.get('username') or "Anonyme"
                date = format_date(score.get('created_at'))
                print(f"   {i}. {name}: {score.get('score')} points ({date})")
        else:
            print("   Aucun score enregistré")
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
    finally:
        conn.close()
        print(f"\n✅ Connexion fermée")

if __name__ == "__main__":
    main()