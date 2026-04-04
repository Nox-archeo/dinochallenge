#!/usr/bin/env python3
"""
DINO CHALLENGE - Analyse RÉELLE des paiements
Vérification détaillée des paiements effectifs
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

def analyze_payments(conn):
    """Analyser tous les paiements en détail"""
    try:
        cursor = conn.cursor()
        
        print("💰 ANALYSE DÉTAILLÉE DES PAIEMENTS:")
        print("=" * 60)
        
        # Récupérer TOUS les paiements
        cursor.execute("""
        SELECT 
            p.*,
            u.first_name,
            u.username
        FROM payments p
        LEFT JOIN users u ON p.telegram_id = u.telegram_id
        ORDER BY p.payment_date DESC;
        """)
        
        payments = cursor.fetchall()
        
        if not payments:
            print("❌ Aucun paiement trouvé dans la base")
            return
        
        print(f"📊 {len(payments)} enregistrement(s) de paiement trouvé(s):\n")
        
        total_recu = 0
        total_pending = 0
        
        for i, payment in enumerate(payments, 1):
            user_name = payment.get('first_name') or payment.get('username') or "Anonyme"
            
            print(f"{i}. 👤 {user_name} (ID: {payment['telegram_id']})")
            print(f"   💵 Montant: {payment['amount']} {payment['currency'] or 'devise inconnue'}")
            print(f"   📅 Date: {payment['payment_date'] or 'N/A'}")
            print(f"   📋 Statut: {payment['status'] or 'N/A'}")
            print(f"   🏷️  Type: {payment['payment_type'] or 'N/A'}")
            print(f"   🗓️  Période: {payment['month_year']}")
            
            if payment['paypal_payment_id']:
                print(f"   💳 PayPal Payment ID: {payment['paypal_payment_id']}")
            if payment['paypal_subscription_id']:
                print(f"   🔄 PayPal Subscription: {payment['paypal_subscription_id']}")
            
            # Compter selon le statut
            status = payment['status'] or ''
            amount = float(payment['amount'] or 0)
            
            if status.lower() in ['completed', 'success', 'paid', 'confirmed']:
                total_recu += amount
                print(f"   ✅ PAIEMENT CONFIRMÉ")
            elif status.lower() in ['pending', 'processing', 'waiting']:
                total_pending += amount
                print(f"   ⏳ PAIEMENT EN ATTENTE")
            elif status.lower() in ['failed', 'cancelled', 'denied', 'error']:
                print(f"   ❌ PAIEMENT ÉCHOUÉ")
            else:
                print(f"   ❓ STATUT INCERTAIN")
            
            print()
        
        # Résumé financier
        print("💰 RÉSUMÉ FINANCIER:")
        print(f"   ✅ Paiements confirmés: {total_recu:.2f}")
        print(f"   ⏳ Paiements en attente: {total_pending:.2f}")
        print(f"   📊 Total enregistrements: {len(payments)}")
        
        # Analyse par devise
        cursor.execute("""
        SELECT currency, COUNT(*) as count, SUM(amount) as total
        FROM payments 
        GROUP BY currency
        ORDER BY total DESC;
        """)
        
        currencies = cursor.fetchall()
        print(f"\n💱 RÉPARTITION PAR DEVISE:")
        for curr in currencies:
            currency = curr['currency'] or 'Inconnue'
            print(f"   {currency}: {curr['count']} paiement(s) = {curr['total']:.2f}")
        
        # Analyse par statut
        cursor.execute("""
        SELECT status, COUNT(*) as count, SUM(amount) as total
        FROM payments 
        GROUP BY status
        ORDER BY count DESC;
        """)
        
        statuses = cursor.fetchall()
        print(f"\n📊 RÉPARTITION PAR STATUT:")
        for stat in statuses:
            status = stat['status'] or 'Statut vide'
            print(f"   {status}: {stat['count']} paiement(s) = {stat['total']:.2f}")
        
    except Exception as e:
        print(f"❌ Erreur analyse paiements: {e}")

def check_real_revenue(conn):
    """Vérifier les vrais revenus effectifs"""
    try:
        cursor = conn.cursor()
        
        print("\n💸 REVENUS EFFECTIFS (paiements confirmés uniquement):")
        print("-" * 55)
        
        # Seuls les paiements avec statuts confirmés
        cursor.execute("""
        SELECT 
            SUM(amount) as total_confirmed,
            COUNT(*) as count_confirmed,
            currency
        FROM payments 
        WHERE LOWER(status) IN ('completed', 'success', 'paid', 'confirmed')
        GROUP BY currency;
        """)
        
        confirmed = cursor.fetchall()
        
        if confirmed:
            total_revenue = 0
            for rev in confirmed:
                amount = float(rev['total_confirmed'] or 0)
                currency = rev['currency'] or 'devise inconnue'
                count = rev['count_confirmed']
                print(f"✅ {amount:.2f} {currency} ({count} paiement(s) confirmé(s))")
                total_revenue += amount
            
            print(f"\n💰 TOTAL REVENUS CONFIRMÉS: {total_revenue:.2f}")
        else:
            print("❌ AUCUN PAIEMENT CONFIRMÉ TROUVÉ")
            print("💡 Tous les paiements sont soit en attente soit échoués")
        
    except Exception as e:
        print(f"❌ Erreur calcul revenus: {e}")

def main():
    """Fonction principale"""
    print("🔍 DINO CHALLENGE - Audit Paiements RÉEL")
    print("=" * 50)
    
    conn = connect_to_db()
    if not conn:
        return
    
    try:
        analyze_payments(conn)
        check_real_revenue(conn)
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
    finally:
        conn.close()
        print(f"\n✅ Audit terminé")

if __name__ == "__main__":
    main()