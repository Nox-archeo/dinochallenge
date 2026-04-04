#!/usr/bin/env python3
"""
DINO CHALLENGE - Vérification COMPLÈTE des utilisateurs
Audit détaillé pour s'assurer qu'on voit TOUS les utilisateurs
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

def connect_to_db():
    """Se connecter à la base PostgreSQL"""
    try:
        db_url = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        print("✅ Connexion à PostgreSQL réussie!")
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return None

def verify_all_users(conn):
    """Vérification complète de tous les utilisateurs"""
    try:
        cursor = conn.cursor()
        
        print("🔍 VÉRIFICATION COMPLÈTE DES UTILISATEURS:")
        print("=" * 60)
        
        # 1. Compter TOUS les utilisateurs
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_count = cursor.fetchone()['total']
        print(f"📊 Total utilisateurs dans la table: {total_count}")
        
        # 2. Récupérer TOUTES les colonnes de TOUS les utilisateurs
        cursor.execute("SELECT * FROM users ORDER BY id ASC")
        all_users = cursor.fetchall()
        
        print(f"\n👥 LISTE COMPLÈTE DE TOUS LES {len(all_users)} UTILISATEUR(S):")
        print("-" * 80)
        
        for i, user in enumerate(all_users, 1):
            print(f"\n{i}. 🆔 ID: {user['id']} | Telegram ID: {user['telegram_id']}")
            print(f"   👤 Nom: {user['first_name'] or 'N/A'}")
            print(f"   📱 Username: @{user['username'] or 'N/A'}")
            print(f"   📧 Email: {user['email'] or 'N/A'}")
            print(f"   💳 PayPal: {user['paypal_email'] or 'N/A'}")
            print(f"   📅 Inscription: {user['registration_date'] or 'N/A'}")
            print(f"   💰 Payé ce mois: {user['has_paid_current_month']}")
            print(f"   🎮 Tentatives aujourd'hui: {user['total_attempts_today'] or 0}")
            print(f"   📆 Dernière tentative: {user['last_attempt_date'] or 'Jamais'}")
            print(f"   🏷️  Nom d'affichage: {user['display_name'] or 'N/A'}")
        
        # 3. Vérifier s'il y a des utilisateurs dans d'autres tables
        print(f"\n🔍 RECHERCHE D'UTILISATEURS DANS AUTRES TABLES:")
        print("-" * 50)
        
        # Utilisateurs mentionnés dans scores mais pas dans users
        cursor.execute("""
        SELECT DISTINCT s.telegram_id, COUNT(*) as score_count
        FROM scores s
        LEFT JOIN users u ON s.telegram_id = u.telegram_id
        WHERE u.telegram_id IS NULL
        GROUP BY s.telegram_id
        """)
        
        orphan_scores = cursor.fetchall()
        if orphan_scores:
            print(f"⚠️  {len(orphan_scores)} Telegram ID(s) avec scores mais SANS compte utilisateur:")
            for orphan in orphan_scores:
                print(f"   - ID {orphan['telegram_id']}: {orphan['score_count']} score(s)")
        else:
            print("✅ Tous les scores correspondent à des utilisateurs existants")
        
        # Utilisateurs mentionnés dans payments mais pas dans users
        cursor.execute("""
        SELECT DISTINCT p.telegram_id, COUNT(*) as payment_count
        FROM payments p
        LEFT JOIN users u ON p.telegram_id = u.telegram_id
        WHERE u.telegram_id IS NULL
        GROUP BY p.telegram_id
        """)
        
        orphan_payments = cursor.fetchall()
        if orphan_payments:
            print(f"⚠️  {len(orphan_payments)} Telegram ID(s) avec paiements mais SANS compte utilisateur:")
            for orphan in orphan_payments:
                print(f"   - ID {orphan['telegram_id']}: {orphan['payment_count']} paiement(s)")
        else:
            print("✅ Tous les paiements correspondent à des utilisateurs existants")
        
        # 4. Vérifier les doublons potentiels
        print(f"\n🔍 RECHERCHE DE DOUBLONS:")
        print("-" * 30)
        
        # Doublons par Telegram ID
        cursor.execute("""
        SELECT telegram_id, COUNT(*) as count
        FROM users
        GROUP BY telegram_id
        HAVING COUNT(*) > 1
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            print(f"⚠️  {len(duplicates)} Telegram ID(s) en doublon:")
            for dup in duplicates:
                print(f"   - ID {dup['telegram_id']}: {dup['count']} comptes")
        else:
            print("✅ Aucun doublon de Telegram ID")
        
        # Doublons par email
        cursor.execute("""
        SELECT email, COUNT(*) as count
        FROM users
        WHERE email IS NOT NULL AND email != ''
        GROUP BY email
        HAVING COUNT(*) > 1
        """)
        
        email_dups = cursor.fetchall()
        if email_dups:
            print(f"⚠️  {len(email_dups)} email(s) en doublon:")
            for dup in email_dups:
                print(f"   - {dup['email']}: {dup['count']} comptes")
        else:
            print("✅ Aucun doublon d'email")
        
        # 5. Résumé final
        print(f"\n📋 RÉSUMÉ FINAL:")
        print("-" * 20)
        print(f"✅ Total utilisateurs confirmés: {len(all_users)}")
        print(f"✅ Utilisateurs avec email: {len([u for u in all_users if u['email']])}")
        print(f"✅ Utilisateurs avec PayPal: {len([u for u in all_users if u['paypal_email']])}")
        print(f"✅ Utilisateurs ayant payé ce mois: {len([u for u in all_users if u['has_paid_current_month']])}")
        
        # Plus ancien et plus récent
        if all_users:
            oldest = min(all_users, key=lambda x: x['registration_date'] if x['registration_date'] else datetime.min)
            newest = max(all_users, key=lambda x: x['registration_date'] if x['registration_date'] else datetime.min)
            
            print(f"👴 Plus ancien: {oldest['first_name']} ({oldest['registration_date']})")
            print(f"👶 Plus récent: {newest['first_name']} ({newest['registration_date']})")
        
    except Exception as e:
        print(f"❌ Erreur vérification utilisateurs: {e}")

def main():
    """Fonction principale"""
    print("🔍 DINO CHALLENGE - Audit COMPLET Utilisateurs")
    print("=" * 55)
    
    conn = connect_to_db()
    if not conn:
        return
    
    try:
        verify_all_users(conn)
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
    finally:
        conn.close()
        print(f"\n✅ Audit terminé - TOUS les utilisateurs vérifiés")

if __name__ == "__main__":
    main()