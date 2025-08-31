#!/usr/bin/env python3
"""
Dino Challenge Bot + API - Bot Telegram et API web pour le jeu Dino
Fonctionnalités :
- Bot Telegram pour interaction utilisateurs
- API REST pour recevoir scores depuis le jeu
- Base de données PostgreSQL/SQLite
- Système de classement en temps réel
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
import json

# Imports pour le bot Telegram
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Imports pour l'API web
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import threading
import time

# Imports pour PayPal
import paypalrestsdk
import hmac
import hashlib
import requests
from decimal import Decimal

# Imports pour la base de données
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
from urllib.parse import urlparse

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration depuis les variables d'environnement
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///dino_challenge.db')
ORGANIZER_CHAT_ID = int(os.getenv('ORGANIZER_CHAT_ID', '123456789'))
PORT = int(os.getenv('PORT', 5000))
GAME_URL = os.getenv('GAME_URL', 'https://nox-archeo.github.io/dinochallenge/')

# Configuration PayPal
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_SECRET_KEY = os.getenv('PAYPAL_SECRET_KEY')
PAYPAL_MODE = os.getenv('PAYPAL_MODE', 'sandbox')  # 'sandbox' ou 'live'
PAYPAL_WEBHOOK_URL = 'https://dinochallenge-bot.onrender.com/paypal-webhook'

# Prix en CHF (taxes incluses)
MONTHLY_PRICE_CHF = Decimal('11.00')  # Prix final en production

# Configuration PayPal SDK
if PAYPAL_CLIENT_ID and PAYPAL_SECRET_KEY:
    paypalrestsdk.configure({
        "mode": PAYPAL_MODE,
        "client_id": PAYPAL_CLIENT_ID,
        "client_secret": PAYPAL_SECRET_KEY
    })

# Variables globales
telegram_app = None
flask_app = Flask(__name__)
CORS(flask_app)  # Permettre les requêtes CORS depuis le jeu

class DatabaseManager:
    """Gestionnaire de base de données - supporte PostgreSQL et SQLite"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_postgres = database_url.startswith('postgresql://') or database_url.startswith('postgres://')
        self.init_database()
    
    def get_connection(self):
        """Obtenir une connexion à la base de données"""
        if self.is_postgres:
            return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
        else:
            # SQLite
            db_path = self.database_url.replace('sqlite:///', '').replace('sqlite://', '')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row  # Pour avoir des dictionnaires
            return conn
    
    def init_database(self):
        """Initialiser les tables de la base de données"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    # Tables PostgreSQL
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id SERIAL PRIMARY KEY,
                            telegram_id BIGINT UNIQUE NOT NULL,
                            username VARCHAR(255),
                            first_name VARCHAR(255),
                            email VARCHAR(255),
                            paypal_email VARCHAR(255),
                            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            has_paid_current_month BOOLEAN DEFAULT FALSE,
                            total_attempts_today INTEGER DEFAULT 0,
                            last_attempt_date DATE
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS scores (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER REFERENCES users(id),
                            telegram_id BIGINT NOT NULL,
                            score INTEGER NOT NULL,
                            game_date DATE DEFAULT CURRENT_DATE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            month_year VARCHAR(7) NOT NULL
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS payments (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER REFERENCES users(id),
                            telegram_id BIGINT NOT NULL,
                            amount DECIMAL(10,2) NOT NULL,
                            currency VARCHAR(3) DEFAULT 'CHF',
                            payment_type VARCHAR(20) DEFAULT 'one_time',
                            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            month_year VARCHAR(7) NOT NULL,
                            status VARCHAR(20) DEFAULT 'completed',
                            paypal_payment_id VARCHAR(255),
                            paypal_subscription_id VARCHAR(255)
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS subscriptions (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER REFERENCES users(id),
                            telegram_id BIGINT NOT NULL,
                            paypal_subscription_id VARCHAR(255) UNIQUE NOT NULL,
                            status VARCHAR(20) DEFAULT 'active',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            cancelled_at TIMESTAMP,
                            next_billing_date DATE,
                            amount DECIMAL(10,2) NOT NULL,
                            currency VARCHAR(3) DEFAULT 'CHF'
                        )
                    """)
                else:
                    # Tables SQLite
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            telegram_id INTEGER UNIQUE NOT NULL,
                            username TEXT,
                            first_name TEXT,
                            email TEXT,
                            paypal_email TEXT,
                            registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                            has_paid_current_month BOOLEAN DEFAULT 0,
                            total_attempts_today INTEGER DEFAULT 0,
                            last_attempt_date DATE
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS scores (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            telegram_id INTEGER NOT NULL,
                            score INTEGER NOT NULL,
                            game_date DATE DEFAULT (DATE('now')),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            month_year TEXT NOT NULL,
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS payments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            telegram_id INTEGER NOT NULL,
                            amount REAL NOT NULL,
                            currency TEXT DEFAULT 'CHF',
                            payment_type TEXT DEFAULT 'one_time',
                            payment_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                            month_year TEXT NOT NULL,
                            status TEXT DEFAULT 'completed',
                            paypal_payment_id TEXT,
                            paypal_subscription_id TEXT,
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS subscriptions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            telegram_id INTEGER NOT NULL,
                            paypal_subscription_id TEXT UNIQUE NOT NULL,
                            status TEXT DEFAULT 'active',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            cancelled_at DATETIME,
                            next_billing_date DATE,
                            amount REAL NOT NULL,
                            currency TEXT DEFAULT 'CHF',
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )
                    """)
                
                conn.commit()
                logger.info("✅ Base de données initialisée avec succès")
                
        except Exception as e:
            logger.error(f"❌ Erreur initialisation base de données: {e}")
            raise
    
    def create_or_get_user(self, telegram_id: int, username: str = None, first_name: str = None) -> Dict:
        """Créer ou récupérer un utilisateur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Vérifier si l'utilisateur existe
                cursor.execute("SELECT * FROM users WHERE telegram_id = %s" if self.is_postgres else 
                             "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
                user = cursor.fetchone()
                
                if user:
                    return dict(user)
                
                # Créer nouvel utilisateur
                if self.is_postgres:
                    cursor.execute("""
                        INSERT INTO users (telegram_id, username, first_name, email)
                        VALUES (%s, %s, %s, %s) RETURNING *
                    """, (telegram_id, username, first_name, username + '@telegram.user' if username else None))
                    user = cursor.fetchone()
                else:
                    cursor.execute("""
                        INSERT INTO users (telegram_id, username, first_name, email)
                        VALUES (?, ?, ?, ?)
                    """, (telegram_id, username, first_name, username + '@telegram.user' if username else None))
                    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
                    user = cursor.fetchone()
                
                conn.commit()
                logger.info(f"✅ Utilisateur créé: {telegram_id}")
                return dict(user)
                
        except Exception as e:
            logger.error(f"❌ Erreur création utilisateur: {e}")
            return {}
    
    def add_score(self, telegram_id: int, score: int) -> bool:
        """Ajouter un score pour un utilisateur"""
        try:
            # S'assurer que l'utilisateur existe
            user = self.create_or_get_user(telegram_id)
            if not user:
                return False
            
            current_month = datetime.now().strftime('%Y-%m')
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        INSERT INTO scores (user_id, telegram_id, score, month_year)
                        VALUES (%s, %s, %s, %s)
                    """, (user['id'], telegram_id, score, current_month))
                else:
                    cursor.execute("""
                        INSERT INTO scores (user_id, telegram_id, score, month_year)
                        VALUES (?, ?, ?, ?)
                    """, (user['id'], telegram_id, score, current_month))
                
                conn.commit()
                logger.info(f"✅ Score ajouté: {telegram_id} = {score}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Erreur ajout score: {e}")
            return False
    
    def get_leaderboard(self, month_year: str = None, limit: int = 10) -> List[Dict]:
        """Récupérer le classement"""
        if not month_year:
            month_year = datetime.now().strftime('%Y-%m')
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        SELECT 
                            u.telegram_id,
                            u.first_name,
                            u.username,
                            MAX(s.score) as best_score,
                            COUNT(s.id) as total_games,
                            u.has_paid_current_month
                        FROM users u
                        JOIN scores s ON u.telegram_id = s.telegram_id
                        WHERE s.month_year = %s
                        GROUP BY u.telegram_id, u.first_name, u.username, u.has_paid_current_month
                        ORDER BY best_score DESC
                        LIMIT %s
                    """, (month_year, limit))
                else:
                    cursor.execute("""
                        SELECT 
                            u.telegram_id,
                            u.first_name,
                            u.username,
                            MAX(s.score) as best_score,
                            COUNT(s.id) as total_games,
                            u.has_paid_current_month
                        FROM users u
                        JOIN scores s ON u.telegram_id = s.telegram_id
                        WHERE s.month_year = ?
                        GROUP BY u.telegram_id, u.first_name, u.username, u.has_paid_current_month
                        ORDER BY best_score DESC
                        LIMIT ?
                    """, (month_year, limit))
                
                results = cursor.fetchall()
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"❌ Erreur récupération classement: {e}")
            return []
    
    def record_payment(self, telegram_id: int, amount: Decimal, payment_type: str = 'one_time', 
                      paypal_payment_id: str = None, paypal_subscription_id: str = None) -> bool:
        """Enregistrer un paiement"""
        try:
            user = self.create_or_get_user(telegram_id)
            if not user:
                return False
            
            current_month = datetime.now().strftime('%Y-%m')
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        INSERT INTO payments (user_id, telegram_id, amount, payment_type, month_year, 
                                            paypal_payment_id, paypal_subscription_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (user['id'], telegram_id, amount, payment_type, current_month, 
                         paypal_payment_id, paypal_subscription_id))
                else:
                    cursor.execute("""
                        INSERT INTO payments (user_id, telegram_id, amount, payment_type, month_year,
                                            paypal_payment_id, paypal_subscription_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user['id'], telegram_id, amount, payment_type, current_month,
                         paypal_payment_id, paypal_subscription_id))
                
                # Mettre à jour le statut de paiement de l'utilisateur
                if self.is_postgres:
                    cursor.execute("""
                        UPDATE users SET has_paid_current_month = TRUE WHERE telegram_id = %s
                    """, (telegram_id,))
                else:
                    cursor.execute("""
                        UPDATE users SET has_paid_current_month = 1 WHERE telegram_id = ?
                    """, (telegram_id,))
                
                conn.commit()
                logger.info(f"✅ Paiement enregistré: {telegram_id} = {amount} CHF ({payment_type})")
                return True
                
        except Exception as e:
            logger.error(f"❌ Erreur enregistrement paiement: {e}")
            return False
    
    def create_subscription(self, telegram_id: int, paypal_subscription_id: str, 
                          amount: Decimal, next_billing_date: str = None) -> bool:
        """Créer un abonnement"""
        try:
            user = self.create_or_get_user(telegram_id)
            if not user:
                return False
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        INSERT INTO subscriptions (user_id, telegram_id, paypal_subscription_id, 
                                                 amount, next_billing_date)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (paypal_subscription_id) DO UPDATE SET
                        status = 'active', next_billing_date = EXCLUDED.next_billing_date
                    """, (user['id'], telegram_id, paypal_subscription_id, amount, next_billing_date))
                else:
                    cursor.execute("""
                        INSERT OR REPLACE INTO subscriptions (user_id, telegram_id, paypal_subscription_id,
                                                            amount, next_billing_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user['id'], telegram_id, paypal_subscription_id, amount, next_billing_date))
                
                conn.commit()
                logger.info(f"✅ Abonnement créé: {telegram_id} = {paypal_subscription_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Erreur création abonnement: {e}")
            return False
    
    def cancel_subscription(self, paypal_subscription_id: str) -> bool:
        """Annuler un abonnement"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        UPDATE subscriptions 
                        SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
                        WHERE paypal_subscription_id = %s
                    """, (paypal_subscription_id,))
                else:
                    cursor.execute("""
                        UPDATE subscriptions 
                        SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
                        WHERE paypal_subscription_id = ?
                    """, (paypal_subscription_id,))
                
                conn.commit()
                logger.info(f"✅ Abonnement annulé: {paypal_subscription_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Erreur annulation abonnement: {e}")
            return False
    
    def check_user_access(self, telegram_id: int) -> bool:
        """Vérifier si l'utilisateur a accès ce mois-ci"""
        try:
            current_month = datetime.now().strftime('%Y-%m')
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Vérifier les paiements uniques pour ce mois
                cursor.execute("""
                    SELECT COUNT(*) FROM payments 
                    WHERE telegram_id = %s AND month_year = %s AND status = 'completed'
                """ if self.is_postgres else """
                    SELECT COUNT(*) FROM payments 
                    WHERE telegram_id = ? AND month_year = ? AND status = 'completed'
                """, (telegram_id, current_month))
                
                payment_count = cursor.fetchone()[0]
                if payment_count > 0:
                    return True
                
                # Vérifier les abonnements actifs
                cursor.execute("""
                    SELECT COUNT(*) FROM subscriptions 
                    WHERE telegram_id = %s AND status = 'active'
                """ if self.is_postgres else """
                    SELECT COUNT(*) FROM subscriptions 
                    WHERE telegram_id = ? AND status = 'active'
                """, (telegram_id,))
                
                subscription_count = cursor.fetchone()[0]
                return subscription_count > 0
                
        except Exception as e:
            logger.error(f"❌ Erreur vérification accès: {e}")
            return False

# Instance globale du gestionnaire de base de données
db = DatabaseManager(DATABASE_URL)

# =============================================================================
# API WEB FLASK
# =============================================================================

@flask_app.route('/health', methods=['GET'])
def health_check():
    """Point de santé pour Render"""
    return jsonify({
        'status': 'ok',
        'bot': 'running',
        'database': 'connected',
        'timestamp': datetime.now().isoformat()
    })

@flask_app.route('/debug/commands', methods=['GET'])
def debug_commands():
    """Vérifier les commandes disponibles"""
    try:
        if telegram_app and telegram_app.bot:
            commands_info = {
                'admin_commands_loaded': True,
                'organizer_id': ORGANIZER_CHAT_ID,
                'paypal_mode': PAYPAL_MODE,
                'commands': [
                    '/admin_distribute',
                    '/payout_august', 
                    '/reset_scores'
                ]
            }
            return jsonify(commands_info)
        else:
            return jsonify({'error': 'Bot not initialized'})
    except Exception as e:
        return jsonify({'error': str(e)})

@flask_app.route('/', methods=['GET'])
def home():
    """Page d'accueil avec informations du bot"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🦕 Dino Challenge Bot</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .header { text-align: center; background: #4CAF50; color: white; padding: 20px; border-radius: 10px; }
            .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
            .endpoint { background: #f5f5f5; padding: 10px; margin: 5px 0; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🦕 Dino Challenge Bot</h1>
            <p>Bot Telegram + API Web pour le jeu Chrome Dino Runner</p>
        </div>
        
        <div class="section">
            <h2>📊 API Endpoints</h2>
            <div class="endpoint"><strong>POST /api/score</strong> - Soumettre un score</div>
            <div class="endpoint"><strong>GET /api/leaderboard</strong> - Récupérer le classement</div>
            <div class="endpoint"><strong>GET /health</strong> - Status du service</div>
        </div>
        
        <div class="section">
            <h2>🎮 Jeu</h2>
            <p><a href="{{ game_url }}" target="_blank">Jouer au Dino Challenge →</a></p>
        </div>
        
        <div class="section">
            <h2>📱 Bot Telegram</h2>
            <p>Recherchez <strong>@DinoChallenge_Bot</strong> sur Telegram pour participer !</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, game_url=GAME_URL)

@flask_app.route('/api/score', methods=['POST'])
def submit_score():
    """Recevoir un score depuis le jeu Dino"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Aucune donnée reçue'}), 400
        
        telegram_id = data.get('telegram_id') or data.get('user_id')
        score = data.get('score')
        username = data.get('username')
        first_name = data.get('first_name')
        
        if not telegram_id or score is None:
            return jsonify({'error': 'telegram_id et score requis'}), 400
        
        # Convertir en entiers
        telegram_id = int(telegram_id)
        score = int(score)
        
        # Validation du score
        if score < 0:
            return jsonify({'error': 'Score invalide'}), 400
        
        # Sauvegarder le score
        success = db.add_score(telegram_id, score)
        
        if success:
            # Notifier le bot Telegram si possible
            if telegram_app:
                asyncio.create_task(notify_new_score(telegram_id, score))
            
            return jsonify({
                'success': True,
                'message': 'Score enregistré avec succès',
                'score': score,
                'telegram_id': telegram_id
            })
        else:
            return jsonify({'error': 'Erreur lors de l\'enregistrement'}), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur soumission score: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    """Récupérer le classement actuel"""
    try:
        month_year = request.args.get('month', datetime.now().strftime('%Y-%m'))
        limit = int(request.args.get('limit', 10))
        
        leaderboard = db.get_leaderboard(month_year, limit)
        
        # Ajouter les positions
        for i, player in enumerate(leaderboard):
            player['position'] = i + 1
        
        return jsonify({
            'leaderboard': leaderboard,
            'month': month_year,
            'total_players': len(leaderboard)
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération classement: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# ENDPOINTS PAYPAL
# =============================================================================

@flask_app.route('/create-payment', methods=['POST'])
def create_payment():
    """Créer un paiement unique PayPal"""
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        
        if not telegram_id:
            return jsonify({'error': 'telegram_id requis'}), 400
        
        # Créer le paiement PayPal
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": f"{GAME_URL}?payment=success&telegram_id={telegram_id}",
                "cancel_url": f"{GAME_URL}?payment=cancelled"
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": "Dino Challenge - Accès Mensuel",
                        "sku": f"dino_monthly_{telegram_id}",
                        "price": str(MONTHLY_PRICE_CHF),
                        "currency": "CHF",
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": str(MONTHLY_PRICE_CHF),
                    "currency": "CHF"
                },
                "description": f"Accès Dino Challenge pour le mois {datetime.now().strftime('%B %Y')}"
            }]
        })
        
        if payment.create():
            # Trouver l'URL d'approbation
            approval_url = None
            for link in payment.links:
                if link.rel == "approval_url":
                    approval_url = link.href
                    break
            
            return jsonify({
                'payment_id': payment.id,
                'approval_url': approval_url,
                'telegram_id': telegram_id
            })
        else:
            logger.error(f"❌ Erreur création paiement PayPal: {payment.error}")
            return jsonify({'error': 'Erreur création paiement'}), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur endpoint create-payment: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/create-subscription', methods=['POST'])
def create_subscription():
    """Créer un abonnement mensuel PayPal"""
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        
        if not telegram_id:
            return jsonify({'error': 'telegram_id requis'}), 400
        
        # Créer le plan d'abonnement (si pas déjà créé)
        plan_id = create_billing_plan()
        if not plan_id:
            return jsonify({'error': 'Erreur création plan abonnement'}), 500
        
        # Créer l'accord d'abonnement
        billing_agreement = paypalrestsdk.BillingAgreement({
            "name": "Dino Challenge - Abonnement Mensuel",
            "description": f"Abonnement mensuel au Dino Challenge pour {telegram_id}",
            "start_date": (datetime.now() + timedelta(minutes=1)).isoformat() + "Z",
            "plan": {
                "id": plan_id
            },
            "payer": {
                "payment_method": "paypal"
            }
        })
        
        if billing_agreement.create():
            # Trouver l'URL d'approbation
            approval_url = None
            for link in billing_agreement.links:
                if link.rel == "approval_url":
                    approval_url = link.href
                    break
            
            return jsonify({
                'agreement_id': billing_agreement.id,
                'approval_url': approval_url,
                'telegram_id': telegram_id
            })
        else:
            logger.error(f"❌ Erreur création abonnement PayPal: {billing_agreement.error}")
            return jsonify({'error': 'Erreur création abonnement'}), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur endpoint create-subscription: {e}")
        return jsonify({'error': str(e)}), 500

def create_billing_plan():
    """Créer un plan de facturation PayPal"""
    try:
        billing_plan = paypalrestsdk.BillingPlan({
            "name": "Dino Challenge Monthly Plan",
            "description": "Plan mensuel pour l'accès au Dino Challenge",
            "type": "INFINITE",
            "payment_definitions": [{
                "name": "Monthly Payment",
                "type": "REGULAR",
                "frequency": "MONTH",
                "frequency_interval": "1",
                "cycles": "0",  # 0 = infini
                "amount": {
                    "value": str(MONTHLY_PRICE_CHF),
                    "currency": "CHF"
                }
            }],
            "merchant_preferences": {
                "setup_fee": {
                    "value": "0",
                    "currency": "CHF"
                },
                "return_url": f"{GAME_URL}?subscription=success",
                "cancel_url": f"{GAME_URL}?subscription=cancelled",
                "auto_bill_amount": "YES",
                "initial_fail_amount_action": "CONTINUE",
                "max_fail_attempts": "3"
            }
        })
        
        if billing_plan.create():
            # Activer le plan
            if billing_plan.activate():
                return billing_plan.id
        
        logger.error(f"❌ Erreur création plan: {billing_plan.error}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Erreur create_billing_plan: {e}")
        return None

@flask_app.route('/paypal-webhook', methods=['POST'])
def paypal_webhook():
    """Webhook PayPal pour traiter les événements de paiement"""
    try:
        # Récupérer les données du webhook
        webhook_data = request.get_json()
        event_type = webhook_data.get('event_type')
        
        logger.info(f"🔔 Webhook PayPal reçu: {event_type}")
        
        # Traiter selon le type d'événement
        if event_type == 'PAYMENT.SALE.COMPLETED':
            # Paiement unique complété
            handle_payment_completed(webhook_data)
            
        elif event_type == 'BILLING.SUBSCRIPTION.CREATED':
            # Abonnement créé
            handle_subscription_created(webhook_data)
            
        elif event_type == 'BILLING.SUBSCRIPTION.ACTIVATED':
            # Abonnement activé
            handle_subscription_activated(webhook_data)
            
        elif event_type == 'BILLING.SUBSCRIPTION.CANCELLED':
            # Abonnement annulé
            handle_subscription_cancelled(webhook_data)
            
        elif event_type == 'BILLING.SUBSCRIPTION.PAYMENT.COMPLETED':
            # Paiement d'abonnement complété
            handle_subscription_payment_completed(webhook_data)
            
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook PayPal: {e}")
        return jsonify({'error': str(e)}), 500

def handle_payment_completed(webhook_data):
    """Traiter un paiement unique complété"""
    try:
        resource = webhook_data.get('resource', {})
        payment_id = resource.get('id')
        amount = Decimal(resource.get('amount', {}).get('total', '0'))
        
        # Extraire telegram_id depuis la description ou les items
        telegram_id = extract_telegram_id_from_payment(resource)
        
        if telegram_id and amount >= MONTHLY_PRICE_CHF:
            # Enregistrer le paiement
            success = db.record_payment(
                telegram_id=telegram_id,
                amount=amount,
                payment_type='one_time',
                paypal_payment_id=payment_id
            )
            
            if success:
                # Notifier l'utilisateur
                asyncio.create_task(notify_payment_success(telegram_id, amount, 'paiement'))
                logger.info(f"✅ Paiement unique traité: {telegram_id} = {amount} CHF")
        
    except Exception as e:
        logger.error(f"❌ Erreur handle_payment_completed: {e}")

def handle_subscription_created(webhook_data):
    """Traiter la création d'abonnement"""
    try:
        resource = webhook_data.get('resource', {})
        subscription_id = resource.get('id')
        
        logger.info(f"📝 Abonnement créé: {subscription_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur handle_subscription_created: {e}")

def handle_subscription_activated(webhook_data):
    """Traiter l'activation d'abonnement"""
    try:
        resource = webhook_data.get('resource', {})
        subscription_id = resource.get('id')
        
        # Extraire telegram_id depuis les métadonnées
        telegram_id = extract_telegram_id_from_subscription(resource)
        
        if telegram_id:
            success = db.create_subscription(
                telegram_id=telegram_id,
                paypal_subscription_id=subscription_id,
                amount=MONTHLY_PRICE_CHF
            )
            
            if success:
                # Enregistrer le premier paiement
                db.record_payment(
                    telegram_id=telegram_id,
                    amount=MONTHLY_PRICE_CHF,
                    payment_type='subscription',
                    paypal_subscription_id=subscription_id
                )
                
                # Notifier l'utilisateur
                asyncio.create_task(notify_payment_success(telegram_id, MONTHLY_PRICE_CHF, 'abonnement'))
                logger.info(f"✅ Abonnement activé: {telegram_id} = {subscription_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur handle_subscription_activated: {e}")

def handle_subscription_cancelled(webhook_data):
    """Traiter l'annulation d'abonnement"""
    try:
        resource = webhook_data.get('resource', {})
        subscription_id = resource.get('id')
        
        success = db.cancel_subscription(subscription_id)
        
        if success:
            logger.info(f"✅ Abonnement annulé: {subscription_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur handle_subscription_cancelled: {e}")

def handle_subscription_payment_completed(webhook_data):
    """Traiter un paiement d'abonnement complété"""
    try:
        resource = webhook_data.get('resource', {})
        amount = Decimal(resource.get('amount', {}).get('total', '0'))
        subscription_id = resource.get('billing_agreement_id')
        
        # Récupérer l'utilisateur depuis l'abonnement
        telegram_id = get_telegram_id_from_subscription(subscription_id)
        
        if telegram_id:
            # Enregistrer le paiement récurrent
            success = db.record_payment(
                telegram_id=telegram_id,
                amount=amount,
                payment_type='subscription',
                paypal_subscription_id=subscription_id
            )
            
            if success:
                # Notifier le renouvellement
                asyncio.create_task(notify_subscription_renewal(telegram_id, amount))
                logger.info(f"✅ Paiement abonnement traité: {telegram_id} = {amount} CHF")
        
    except Exception as e:
        logger.error(f"❌ Erreur handle_subscription_payment_completed: {e}")

def extract_telegram_id_from_payment(resource):
    """Extraire telegram_id depuis les données de paiement"""
    try:
        # Chercher dans les items
        for item in resource.get('item_list', {}).get('items', []):
            sku = item.get('sku', '')
            if sku.startswith('dino_monthly_'):
                return int(sku.replace('dino_monthly_', ''))
        return None
    except:
        return None

def extract_telegram_id_from_subscription(resource):
    """Extraire telegram_id depuis les données d'abonnement"""
    try:
        description = resource.get('description', '')
        # Chercher un pattern comme "pour 123456789"
        import re
        match = re.search(r'pour (\d+)', description)
        if match:
            return int(match.group(1))
        return None
    except:
        return None

def get_telegram_id_from_subscription(subscription_id):
    """Récupérer telegram_id depuis l'ID d'abonnement"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_id FROM subscriptions 
                WHERE paypal_subscription_id = %s
            """ if db.is_postgres else """
                SELECT telegram_id FROM subscriptions 
                WHERE paypal_subscription_id = ?
            """, (subscription_id,))
            
            result = cursor.fetchone()
            return result[0] if result else None
            
    except Exception as e:
        logger.error(f"❌ Erreur get_telegram_id_from_subscription: {e}")
        return None

# =============================================================================
# BOT TELEGRAM
# =============================================================================

async def notify_payment_success(telegram_id: int, amount: Decimal, payment_type: str):
    """Notifier le succès d'un paiement"""
    try:
        if payment_type == 'abonnement':
            message = f"✅ Abonnement Activé !\n\n"
            message += f"💰 Montant : {amount} CHF/mois\n"
            message += f"🔄 Type : Abonnement mensuel automatique\n"
            message += f"📅 Prochain prélèvement : {(datetime.now() + timedelta(days=30)).strftime('%d/%m/%Y')}\n\n"
            message += f"🎮 Accès activé pour le jeu !\n"
            message += f"ℹ️ Vous pouvez annuler votre abonnement à tout moment via /cancel_subscription"
        else:
            message = f"✅ Paiement Confirmé !\n\n"
            message += f"💰 Montant : {amount} CHF\n"
            message += f"📅 Valable jusqu'au : {datetime.now().replace(day=1).replace(month=datetime.now().month+1 if datetime.now().month < 12 else 1, year=datetime.now().year+1 if datetime.now().month == 12 else datetime.now().year).strftime('%d/%m/%Y')}\n\n"
            message += f"🎮 Accès activé pour ce mois !\n"
            message += f" Pour un accès permanent, choisissez l'abonnement mensuel avec /payment"
        
        await telegram_app.bot.send_message(
            chat_id=telegram_id,
            text=message,
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur notification paiement: {e}")

# =============================================================================
# DISTRIBUTION AUTOMATIQUE MENSUELLE
# =============================================================================

async def distribute_monthly_prizes():
    """Distribution automatique des prix mensuels - Le 1er de chaque mois à 00:01"""
    try:
        logger.info("🏆 DÉBUT - Distribution automatique des prix mensuels")
        
        # Obtenir le mois précédent
        now = datetime.now()
        if now.month == 1:
            prev_month = 12
            prev_year = now.year - 1
        else:
            prev_month = now.month - 1
            prev_year = now.year
            
        month_name = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ][prev_month - 1]
        
        logger.info(f"📅 Distribution pour {month_name} {prev_year}")
        
        # Obtenir le top 3 du mois précédent
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.telegram_id, u.username, u.email, s.score, s.timestamp
                FROM scores s
                JOIN users u ON s.user_id = u.id
                WHERE EXTRACT(MONTH FROM s.timestamp) = %s 
                AND EXTRACT(YEAR FROM s.timestamp) = %s
                ORDER BY s.score DESC
                LIMIT 3
            """ if db.is_postgres else """
                SELECT u.telegram_id, u.username, u.email, s.score, s.timestamp
                FROM scores s
                JOIN users u ON s.user_id = u.id
                WHERE strftime('%m', s.timestamp) = ? 
                AND strftime('%Y', s.timestamp) = ?
                ORDER BY s.score DESC
                LIMIT 3
            """, (str(prev_month).zfill(2), str(prev_year)))
            
            winners = cursor.fetchall()
        
        if not winners:
            logger.info("❌ Aucun gagnant trouvé pour le mois précédent")
            return
        
        # Prix par position
        prizes = [
            {"position": 1, "amount": Decimal("150.00"), "emoji": "🥇"},
            {"position": 2, "amount": Decimal("100.00"), "emoji": "🥈"},
            {"position": 3, "amount": Decimal("50.00"), "emoji": "🥉"}
        ]
        
        # Distribuer les prix
        for i, winner in enumerate(winners):
            if i >= 3:  # Seulement le top 3
                break
                
            prize = prizes[i]
            telegram_id = winner[0] if db.is_postgres else winner["telegram_id"]
            username = winner[1] if db.is_postgres else winner["username"]
            email = winner[2] if db.is_postgres else winner["email"]
            score = winner[3] if db.is_postgres else winner["score"]
            
            try:
                # Envoyer le paiement PayPal
                if email and PAYPAL_CLIENT_ID:
                    payment_success = await send_paypal_payout(
                        email, 
                        prize["amount"], 
                        f"Félicitations ! Prize Dino Challenge {month_name} {prev_year} - {prize['position']}ème place"
                    )
                    
                    if payment_success:
                        # Notifier le gagnant
                        message = f"{prize['emoji']} FÉLICITATIONS !\n\n"
                        message += f"🏆 Vous êtes {prize['position']}ème du classement {month_name} {prev_year} !\n"
                        message += f"🎯 Score: {score:,} points\n"
                        message += f"💰 Prix: {prize['amount']} CHF\n\n"
                        message += f"💳 Le paiement PayPal a été envoyé à: {email}\n"
                        message += f"🎉 Félicitations et merci de jouer !"
                        
                        await telegram_app.bot.send_message(
                            chat_id=telegram_id,
                            text=message
                        )
                        
                        logger.info(f"✅ Prix envoyé à {username} ({prize['position']}ème place): {prize['amount']} CHF")
                    else:
                        logger.error(f"❌ Échec paiement PayPal pour {username}")
                else:
                    logger.warning(f"⚠️ Email manquant ou PayPal non configuré pour {username}")
                    
            except Exception as e:
                logger.error(f"❌ Erreur distribution pour {username}: {e}")
        
        # Notifier l'organisateur
        try:
            summary_message = f"📊 RÉSUMÉ DISTRIBUTION {month_name.upper()} {prev_year}\n\n"
            for i, winner in enumerate(winners[:3]):
                prize = prizes[i]
                username = winner[1] if db.is_postgres else winner["username"]
                score = winner[3] if db.is_postgres else winner["score"]
                summary_message += f"{prize['emoji']} {prize['position']}ème: {username} - {score:,} pts - {prize['amount']} CHF\n"
            
            summary_message += f"\n✅ Distribution terminée automatiquement"
            
            await telegram_app.bot.send_message(
                chat_id=ORGANIZER_CHAT_ID,
                text=summary_message
            )
        except Exception as e:
            logger.error(f"❌ Erreur notification organisateur: {e}")
        
        # Remettre les scores à zéro pour le nouveau mois
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM scores")
                conn.commit()
            logger.info("🔄 Scores remis à zéro pour le nouveau mois")
        except Exception as e:
            logger.error(f"❌ Erreur remise à zéro des scores: {e}")
        
        # Expirer les accès du mois précédent (paiements uniques seulement)
        try:
            await expire_monthly_access()
            logger.info("🔒 Accès mensuels expirés")
        except Exception as e:
            logger.error(f"❌ Erreur expiration accès: {e}")
        
        logger.info("🏆 FIN - Distribution automatique terminée")
        
    except Exception as e:
        logger.error(f"❌ Erreur distribution automatique: {e}")

async def send_paypal_payout(email: str, amount: Decimal, note: str) -> bool:
    """Envoyer un paiement PayPal"""
    try:
        if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET_KEY:
            logger.error("❌ Configuration PayPal manquante")
            return False
        
        payout = paypalrestsdk.Payout({
            "sender_batch_header": {
                "sender_batch_id": f"dino_prize_{int(time.time())}",
                "email_subject": "Félicitations ! Votre prix Dino Challenge",
                "email_message": note
            },
            "items": [{
                "recipient_type": "EMAIL",
                "amount": {
                    "value": str(amount),
                    "currency": "CHF"
                },
                "receiver": email,
                "note": note,
                "sender_item_id": f"item_{int(time.time())}"
            }]
        })
        
        if payout.create():
            logger.info(f"✅ Payout PayPal créé: {payout.batch_header.payout_batch_id}")
            return True
        else:
            logger.error(f"❌ Erreur création payout: {payout.error}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur send_paypal_payout: {e}")
        return False

async def notify_subscription_renewal(telegram_id: int, amount: Decimal):
    """Notifier le renouvellement d'abonnement"""
    try:
        message = f"🔄 Abonnement Renouvelé !\n\n"
        message += f"💰 Montant : {amount} CHF\n"
        message += f"📅 Période : {datetime.now().strftime('%B %Y')}\n"
        message += f"📅 Prochain prélèvement : {(datetime.now() + timedelta(days=30)).strftime('%d/%m/%Y')}\n\n"
        message += f"🎮 Votre accès continue !"
        
        await telegram_app.bot.send_message(
            chat_id=telegram_id,
            text=message,
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur notification renouvellement: {e}")

async def notify_new_score(telegram_id: int, score: int):
    """Notifier l'utilisateur de son nouveau score"""
    try:
        # Vérifier si l'utilisateur a accès
        has_access = db.check_user_access(telegram_id)
        
        if not has_access:
            message = f"🎮 Score enregistré !\n\n"
            message += f"📊 Score : {score:,} points\n\n"
            message += f"⚠️ Accès limité - Pour participer au concours mensuel :\n"
            message += f"💰 Payez 11 CHF avec /payment\n"
            message += f"🏆 Tentez de gagner les prix mensuels !"
        else:
            message = f"🎮 Nouveau score enregistré !\n\n"
            message += f"📊 Score : {score:,} points\n"
            message += f"🕒 Enregistré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n\n"
            message += f"🏆 Tapez /leaderboard pour voir le classement !"
        
        await telegram_app.bot.send_message(
            chat_id=telegram_id,
            text=message,
        )
    except Exception as e:
        logger.error(f"❌ Erreur notification score: {e}")

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire de la commande /start"""
    user = update.effective_user
    
    # Créer ou récupérer l'utilisateur
    db_user = db.create_or_get_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Vérifier l'accès
    has_access = db.check_user_access(user.id)
    
    message = f"""🦕 Bienvenue dans le Dino Challenge !

👋 Salut {user.first_name} !

🎮 Le jeu Chrome Dino avec des vrais prix !
🏆 Concours mensuel avec redistribution des gains

💰 Participation : 11 CHF
• Paiement unique pour le mois en cours
• OU abonnement mensuel automatique

🥇 Prix mensuels distribués au top 3 :
• 1er place : 40% de la cagnotte
• 2e place : 15% de la cagnotte  
• 3e place : 5% de la cagnotte

📋 Commandes principales :
/payment - 💰 Participer au concours
/leaderboard - 🏆 Voir le classement
/profile - 👤 Mon profil
/help - ❓ Aide complète

"""
    
    if has_access:
        message += f"✅ Vous avez accès ce mois !\n"
        message += f"🎮 Utilisez le bouton 'Jouer' pour commencer"
    else:
        message += f"⚠️ Payez pour participer : /payment\n"
        message += f"🎮 Démo gratuite : {GAME_URL}"
    
    # TEMPORAIRE: Suppression des boutons pour tester
    # keyboard = [
    #     [InlineKeyboardButton("❓ Comment jouer ?", callback_data="help_game")],
    #     [InlineKeyboardButton("📋 Règles du concours", callback_data="help_rules")],
    #     [InlineKeyboardButton("🏆 Voir le classement", callback_data="show_leaderboard")]
    # ]
    
    # reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message)

# leaderboard_handler supprimé - utilise maintenant handlers/leaderboard.py

async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le profil utilisateur"""
    user = update.effective_user
    db_user = db.create_or_get_user(user.id, user.username, user.first_name)
    
    # Récupérer les stats de l'utilisateur
    current_month = datetime.now().strftime('%Y-%m')
    user_scores = []
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT score, created_at 
                FROM scores 
                WHERE telegram_id = %s AND month_year = %s 
                ORDER BY score DESC 
                LIMIT 5
            """ if db.is_postgres else """
                SELECT score, created_at 
                FROM scores 
                WHERE telegram_id = ? AND month_year = ? 
                ORDER BY score DESC 
                LIMIT 5
            """, (user.id, current_month))
            user_scores = cursor.fetchall()
    except Exception as e:
        logger.error(f"❌ Erreur récupération profil: {e}")
    
    message = f"👤 PROFIL - {user.first_name}\n\n"
    message += f"🆔 ID Telegram: {user.id}\n"
    message += f"📧 Email: {db_user.get('email', 'Non configuré')}\n"
    message += f"📅 Inscription: {db_user.get('registration_date', 'Inconnue')}\n\n"
    
    if user_scores:
        message += f"🏆 TOP 5 DE VOS SCORES CE MOIS:\n"
        for i, score_data in enumerate(user_scores, 1):
            score = dict(score_data)['score']
            message += f"   {i}. {score:,} points\n"
        message += f"\n📊 Total parties: {len(user_scores)}\n"
    else:
        message += "🎮 Aucun score ce mois-ci\n"
        message += "Utilisez le bouton 'Jouer' pour commencer !\n"
    
    await update.message.reply_text(message)

async def payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire pour les paiements"""
    user = update.effective_user
    
    # Vérifier si l'utilisateur a déjà payé ce mois
    has_access = db.check_user_access(user.id)
    
    if has_access:
        message = f"✅ Vous avez déjà accès ce mois !\n\n"
        message += f"🎮 Utilisez le bouton 'Jouer' pour commencer\n"
        message += f"🏆 Consultez le classement avec /leaderboard"
        
        await update.message.reply_text(message)
        return
    
    # Proposer les options de paiement
    keyboard = [
        [{"text": "💳 Paiement Unique - 11 CHF", "callback_data": f"pay_once_{user.id}"}],
        [{"text": "🔄 Abonnement Mensuel - 11 CHF/mois", "callback_data": f"pay_subscription_{user.id}"}],
        [{"text": "❌ Annuler", "callback_data": "cancel_payment"}]
    ]
    
    message = "💰 PARTICIPER AU DINO CHALLENGE\n\n"
    message += "🎯 Choisissez votre option de paiement :\n\n"
    message += "💳 Paiement Unique (11 CHF)\n"
    message += "• Accès pour le mois en cours uniquement\n"
    message += "• À renouveler chaque mois manuellement\n\n"
    message += "🔄 Abonnement Mensuel (11 CHF/mois)\n"
    message += "• Accès permanent avec renouvellement automatique\n"
    message += "• Annulable à tout moment\n"
    message += "• Plus pratique, jamais d'interruption !\n\n"
    message += "🏆 Prix mensuels distribués au top 3 !"
    
    inline_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Paiement Unique - 11 CHF", callback_data=f"pay_once_{user.id}")],
        [InlineKeyboardButton("🔄 Abonnement Mensuel - 11 CHF/mois", callback_data=f"pay_subscription_{user.id}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_payment")]
    ])
    
    await update.message.reply_text(message, reply_markup=inline_keyboard)

async def payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire pour les callbacks de paiement"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        logger.info(f"🔧 Debug - Callback data: {data}")
        
        if data == "cancel_payment":
            await query.edit_message_text("❌ Paiement annulé.")
            return
        
        if data.startswith("pay_once_"):
            telegram_id = int(data.replace("pay_once_", ""))
            payment_url = f"https://dinochallenge-bot.onrender.com/create-payment?telegram_id={telegram_id}"
            
            message = "💳 Paiement Unique - 11 CHF\n\n"
            message += "🔗 Cliquez sur le lien ci-dessous pour payer :\n\n"
            message += f"{payment_url}\n\n"
            message += "📱 Vous serez redirigé vers PayPal pour finaliser le paiement.\n"
            message += "✅ Une fois payé, votre accès sera activé automatiquement !"
            
            await query.edit_message_text(message)
        
        elif data.startswith("pay_subscription_"):
            telegram_id = int(data.replace("pay_subscription_", ""))
            subscription_url = f"https://dinochallenge-bot.onrender.com/create-subscription?telegram_id={telegram_id}"
            
            # COPIE EXACTE du format du paiement unique qui fonctionne
            message = "🔄 Abonnement Mensuel - 11 CHF/mois\n\n"
            message += "🔗 Cliquez sur le lien ci-dessous pour vous abonner :\n\n"
            message += f"{subscription_url}\n\n"
            message += "📱 Vous serez redirigé vers PayPal pour configurer l'abonnement.\n"
            message += "✅ Une fois configuré, votre accès sera activé automatiquement !"
            
            await query.edit_message_text(message)
        
        elif data == "help_game":
            await help_game_callback(update, context)
            
        elif data == "help_rules":
            await help_rules_callback(update, context)
            
        elif data == "show_leaderboard":
            await show_leaderboard_callback(update, context)
    
    except Exception as e:
        logger.error(f"❌ Erreur callback query: {e}")
        try:
            await query.edit_message_text("❌ Erreur lors du traitement. Veuillez réessayer.")
        except:
            logger.error("❌ Impossible d'envoyer le message d'erreur")

async def cancel_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annuler l'abonnement PayPal"""
    user = update.effective_user
    
    message = f"🔄 Gestion de l'abonnement\n\n"
    message += f"Pour annuler votre abonnement PayPal :\n\n"
    message += f"1. Connectez-vous à votre compte PayPal\n"
    message += f"2. Allez dans 'Paiements' → 'Abonnements'\n"
    message += f"3. Trouvez 'Dino Challenge'\n"
    message += f"4. Cliquez sur 'Annuler l'abonnement'\n\n"
    message += f"📞 Besoin d'aide ? Contactez l'organisateur.\n"
    message += f"⚠️ L'accès reste valide jusqu'à la fin de la période payée."
    
    await update.message.reply_text(message)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher l'aide - VERSION ULTRA SIMPLE"""
    message = """AIDE - DINO CHALLENGE

COMMENT JOUER :
- Utilisez ESPACE pour faire sauter le dinosaure
- Utilisez FLECHE BAS pour vous baisser
- Evitez les cactus et les oiseaux
- Plus vous survivez longtemps, plus votre score est eleve

CONCOURS :
- Payez 11 CHF pour participer
- Votre meilleur score du mois compte
- Prix distribues au top 3 : 40%, 15%, 5%

COMMANDES :
/start - Menu principal
/payment - Participer
/leaderboard - Classement
/help - Cette aide

Pour toute question, contactez l'organisateur.
"""
    
    await update.message.reply_text(message)

async def admin_distribute_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande admin pour distribuer manuellement les prix"""
    user_id = update.effective_user.id
    
    # Vérifier si c'est l'admin
    if user_id != ORGANIZER_CHAT_ID:
        await update.message.reply_text("❌ Accès refusé. Seul l'organisateur peut utiliser cette commande.")
        return
    
    try:
        # Récupérer le mois et l'année depuis les arguments
        args = context.args
        if len(args) != 2:
            await update.message.reply_text(
                "❌ Usage: /admin_distribute <mois> <année>\n"
                "Exemple: /admin_distribute 8 2025 (pour août 2025)"
            )
            return
        
        month = int(args[0])
        year = int(args[1])
        
        if month < 1 or month > 12:
            await update.message.reply_text("❌ Le mois doit être entre 1 et 12")
            return
        
        month_names = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ]
        month_name = month_names[month - 1]
        
        await update.message.reply_text(f"🏆 Démarrage distribution manuelle pour {month_name} {year}...")
        
        # Distribution manuelle
        await distribute_monthly_prizes_manual(month, year, update)
        
    except ValueError:
        await update.message.reply_text("❌ Mois et année doivent être des nombres")
    except Exception as e:
        logger.error(f"❌ Erreur admin_distribute: {e}")
        await update.message.reply_text(f"❌ Erreur: {e}")

async def distribute_monthly_prizes_manual(month: int, year: int, update: Update):
    """Distribution manuelle des prix pour un mois/année spécifique"""
    try:
        month_names = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ]
        month_name = month_names[month - 1]
        
        logger.info(f"📅 Distribution manuelle pour {month_name} {year}")
        
        # Obtenir le top 3 du mois spécifique
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.telegram_id, u.username, u.email, s.score, s.timestamp
                FROM scores s
                JOIN users u ON s.user_id = u.id
                WHERE EXTRACT(MONTH FROM s.timestamp) = %s 
                AND EXTRACT(YEAR FROM s.timestamp) = %s
                ORDER BY s.score DESC
                LIMIT 3
            """ if db.is_postgres else """
                SELECT u.telegram_id, u.username, u.email, s.score, s.timestamp
                FROM scores s
                JOIN users u ON s.user_id = u.id
                WHERE strftime('%m', s.timestamp) = ? 
                AND strftime('%Y', s.timestamp) = ?
                ORDER BY s.score DESC
                LIMIT 3
            """, (str(month).zfill(2), str(year)))
            
            winners = cursor.fetchall()
        
        if not winners:
            await update.message.reply_text(f"❌ Aucun gagnant trouvé pour {month_name} {year}")
            return
        
        # Prix par position
        prizes = [
            {"position": 1, "amount": Decimal("150.00"), "emoji": "🥇"},
            {"position": 2, "amount": Decimal("100.00"), "emoji": "🥈"},
            {"position": 3, "amount": Decimal("50.00"), "emoji": "🥉"}
        ]
        
        await update.message.reply_text(f"📊 Gagnants trouvés pour {month_name} {year}:")
        
        # Distribuer les prix
        for i, winner in enumerate(winners):
            if i >= 3:  # Seulement le top 3
                break
                
            prize = prizes[i]
            telegram_id = winner[0] if db.is_postgres else winner["telegram_id"]
            username = winner[1] if db.is_postgres else winner["username"]
            email = winner[2] if db.is_postgres else winner["email"]
            score = winner[3] if db.is_postgres else winner["score"]
            
            await update.message.reply_text(
                f"{prize['emoji']} {prize['position']}ème: {username} - {score:,} pts - {prize['amount']} CHF"
            )
            
            try:
                # Envoyer le paiement PayPal
                if email and PAYPAL_CLIENT_ID:
                    payment_success = await send_paypal_payout(
                        email, 
                        prize["amount"], 
                        f"Félicitations ! Prize Dino Challenge {month_name} {year} - {prize['position']}ème place"
                    )
                    
                    if payment_success:
                        # Notifier le gagnant
                        message = f"{prize['emoji']} FÉLICITATIONS !\n\n"
                        message += f"🏆 Vous êtes {prize['position']}ème du classement {month_name} {year} !\n"
                        message += f"🎯 Score: {score:,} points\n"
                        message += f"💰 Prix: {prize['amount']} CHF\n\n"
                        message += f"💳 Le paiement PayPal a été envoyé à: {email}\n"
                        message += f"🎉 Félicitations et merci de jouer !"
                        
                        await telegram_app.bot.send_message(
                            chat_id=telegram_id,
                            text=message
                        )
                        
                        await update.message.reply_text(f"✅ Paiement envoyé à {username}")
                        logger.info(f"✅ Prix envoyé à {username} ({prize['position']}ème place): {prize['amount']} CHF")
                    else:
                        await update.message.reply_text(f"❌ Échec paiement PayPal pour {username}")
                        logger.error(f"❌ Échec paiement PayPal pour {username}")
                else:
                    await update.message.reply_text(f"⚠️ Email manquant ou PayPal non configuré pour {username}")
                    logger.warning(f"⚠️ Email manquant ou PayPal non configuré pour {username}")
                    
            except Exception as e:
                await update.message.reply_text(f"❌ Erreur pour {username}: {e}")
                logger.error(f"❌ Erreur distribution pour {username}: {e}")
        
        await update.message.reply_text(f"🏆 Distribution terminée pour {month_name} {year}")
        
    except Exception as e:
        logger.error(f"❌ Erreur distribution manuelle: {e}")
        await update.message.reply_text(f"❌ Erreur: {e}")

async def admin_payout_august_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande rapide pour distribuer les prix d'août 2025"""
    user_id = update.effective_user.id
    
    # Vérifier si c'est l'admin
    if user_id != ORGANIZER_CHAT_ID:
        await update.message.reply_text("❌ Accès refusé. Seul l'organisateur peut utiliser cette commande.")
        return
    
    await update.message.reply_text("🏆 Démarrage distribution d'août 2025...")
    await distribute_monthly_prizes_manual(8, 2025, update)

async def admin_reset_scores_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande admin pour remettre les scores à zéro"""
    user_id = update.effective_user.id
    
    # Vérifier si c'est l'admin
    if user_id != ORGANIZER_CHAT_ID:
        await update.message.reply_text("❌ Accès refusé. Seul l'organisateur peut utiliser cette commande.")
        return
    
    try:
        await update.message.reply_text("🔄 Remise à zéro des scores en cours...")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scores")
            conn.commit()
        
        await update.message.reply_text("✅ Tous les scores ont été remis à zéro !")
        logger.info("🔄 Scores remis à zéro manuellement par l'admin")
        
    except Exception as e:
        logger.error(f"❌ Erreur reset scores: {e}")
        await update.message.reply_text(f"❌ Erreur: {e}")

async def help_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher l'aide sur le gameplay via callback"""
    query = update.callback_query
    await query.answer()
    
    message = """🎮 COMMENT JOUER AU T-REX RUNNER

🦕 Le jeu :
C'est le célèbre jeu du dinosaure de Google Chrome ! Votre T-Rex court automatiquement dans le désert.

🕹️ Contrôles :
• ESPACE ou FLÈCHE HAUT : Faire sauter le dinosaure
• FLÈCHE BAS : Se baisser (pour éviter les ptérodactyles)

🌵 Obstacles :
• Cactus (petits et grands) : Sautez par-dessus
• Ptérodactyles : Sautez ou baissez-vous selon leur hauteur
• La vitesse augmente progressivement !

📊 Points :
• +1 point par obstacle évité
• Plus vous survivez longtemps, plus votre score est élevé
• Votre MEILLEUR score du mois compte pour le concours

💡 Astuces :
• Gardez le rythme, ne paniquez pas
• Anticipez les obstacles
• Entraînez-vous autant que vous voulez !
"""
    
    await query.edit_message_text(message)

async def help_rules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les règles du concours via callback"""
    query = update.callback_query
    await query.answer()
    
    message = """📋 RÈGLES DU CONCOURS DINO CHALLENGE

💰 Participation :
• Coût : 11 CHF pour participer au mois en cours
• Paiement unique OU abonnement mensuel automatique
• Seuls les participants payants peuvent soumettre des scores

🎮 Comment participer :
1. Payez avec /payment
2. Recevez votre lien de jeu personnalisé
3. Jouez autant de fois que vous voulez
4. Votre MEILLEUR score du mois compte

🏆 Prix mensuels :
La cagnotte totale est redistribuée au top 3 :
• 🥇 1er place : 40% de la cagnotte
• 🥈 2e place : 15% de la cagnotte
• 🥉 3e place : 5% de la cagnotte

📅 Cycle mensuel :
• Nouveau concours chaque mois
• Classement remis à zéro le 1er de chaque mois
• Paiements calculés automatiquement fin de mois

⚖️ Règles importantes :
• Un seul compte par personne
• Pas de triche ou manipulation
• Scores vérifiés automatiquement
• Décisions de l'organisateur finales

💳 Paiements :
• Via PayPal sécurisé
• Accès immédiat après paiement
• Remboursement possible avant premier jeu
"""
    
    await query.edit_message_text(message)

async def show_leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le classement via callback"""
    query = update.callback_query
    await query.answer()
    
    # Réutiliser la logique du leaderboard existant
    current_month = datetime.now().strftime('%Y-%m')
    leaderboard = db.get_leaderboard(current_month)
    
    if not leaderboard:
        message = f"🏆 CLASSEMENT {current_month}\n\n"
        message += "Aucun score enregistré ce mois-ci.\n"
        message += "Soyez le premier à participer ! 🎮"
    else:
        message = f"🏆 CLASSEMENT {current_month}\n\n"
        
        for i, player in enumerate(leaderboard, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            username = player['username'] or player['first_name'] or "Anonyme"
            score = player['best_score']
            games = player['total_games']
            
            message += f"{emoji} {username} - {score} pts ({games} parties)\n"
        
        message += f"\n💰 Cagnotte actuelle : {len(leaderboard) * 11:.2f} CHF"
    
    await query.edit_message_text(message)

async def setup_bot_commands():
    """Configurer les commandes du bot"""
    commands = [
        BotCommand("start", "🏠 Menu principal"),
        BotCommand("payment", "💰 Participer au concours"),
        BotCommand("leaderboard", "🏆 Classement mensuel"),
        BotCommand("profile", "👤 Mon profil"),
        BotCommand("cancel_subscription", "❌ Annuler l'abonnement"),
        BotCommand("help", "❓ Aide et règles"),
        BotCommand("admin_distribute", "🔧 [ADMIN] Distribuer prix manuellement"),
        BotCommand("payout_august", "🚀 [ADMIN] Distribuer août 2025"),
        BotCommand("reset_scores", "🔄 [ADMIN] Remettre scores à zéro"),
    ]
    
    await telegram_app.bot.set_my_commands(commands)
    logger.info("✅ Commandes du bot configurées")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour les messages texte du bot secondaire - délègue au bot principal"""
    text = update.message.text.strip()
    
    # Si c'est un nom potentiel (pas un email et pas trop long)
    if len(text) > 0 and len(text) <= 50 and not text.startswith('/') and '@' not in text:
        user_id = update.effective_user.id
        try:
            # Créer ou récupérer l'utilisateur
            username = update.effective_user.username or update.effective_user.first_name or "Utilisateur"
            first_name = update.effective_user.first_name or username
            user = db.create_or_get_user(user_id, username, first_name)
            
            if user:
                await update.message.reply_text(
                    f"✅ Profil configuré !\n\n"
                    f"👤 Nom : `{text}`\n\n"
                    f"Vous pouvez maintenant utiliser /start pour accéder au menu principal !",
                )
            else:
                await update.message.reply_text(
                    "❌ Erreur lors de la configuration. Utilisez /start pour recommencer."
                )
        except Exception as e:
            logger.error(f"❌ Erreur handle_text_message: {e}")
            await update.message.reply_text(
                "❌ Erreur lors de la configuration. Utilisez /start pour recommencer."
            )
    else:
        await update.message.reply_text(
            "❓ Message non reconnu. Utilisez /start pour voir le menu principal."
        )

def setup_telegram_bot():
    """Configurer le bot Telegram"""
    global telegram_app
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN manquant !")
        return None
    
    # Créer l'application bot
    # Import des handlers depuis les modules séparés
    from handlers.leaderboard import leaderboard_handler
    
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Ajouter les handlers
    telegram_app.add_handler(CommandHandler("start", start_handler))
    telegram_app.add_handler(CommandHandler("payment", payment_handler))
    telegram_app.add_handler(CommandHandler("leaderboard", leaderboard_handler))
    telegram_app.add_handler(CommandHandler("profile", profile_handler))
    telegram_app.add_handler(CommandHandler("cancel_subscription", cancel_subscription_handler))
    telegram_app.add_handler(CommandHandler("help", help_handler))
    telegram_app.add_handler(CommandHandler("admin_distribute", admin_distribute_handler))
    telegram_app.add_handler(CommandHandler("payout_august", admin_payout_august_handler))
    telegram_app.add_handler(CommandHandler("reset_scores", admin_reset_scores_handler))
    telegram_app.add_handler(CallbackQueryHandler(payment_callback_handler))
    
    logger.info("✅ Commandes admin ajoutées: admin_distribute, payout_august, reset_scores")
    
    # Ajouter un handler pour les messages texte (synchronisation avec bot principal)
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    logger.info("✅ Bot Telegram configuré")
    return telegram_app

async def run_telegram_bot():
    """Exécuter le bot Telegram"""
    try:
        app = setup_telegram_bot()
        if app:
            await setup_bot_commands()
            
            # Démarrer la tâche de vérification automatique
            asyncio.create_task(monthly_prize_checker())
            
            logger.info("🤖 Démarrage du bot Telegram...")
            await app.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"❌ Erreur bot Telegram: {e}")

async def expire_monthly_access():
    """Expirer les accès mensuels (paiements uniques seulement) du mois précédent"""
    try:
        # Obtenir le mois précédent
        now = datetime.now()
        if now.month == 1:
            prev_month = 12
            prev_year = now.year - 1
        else:
            prev_month = now.month - 1
            prev_year = now.year
        
        prev_month_str = f"{prev_year}-{str(prev_month).zfill(2)}"
        
        # Marquer les paiements uniques du mois précédent comme expirés
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Obtenir les utilisateurs qui avaient un accès le mois précédent (paiement unique seulement)
            cursor.execute("""
                SELECT DISTINCT telegram_id FROM payments 
                WHERE month_year = %s AND status = 'completed'
                AND telegram_id NOT IN (
                    SELECT telegram_id FROM subscriptions WHERE status = 'active'
                )
            """ if db.is_postgres else """
                SELECT DISTINCT telegram_id FROM payments 
                WHERE month_year = ? AND status = 'completed'
                AND telegram_id NOT IN (
                    SELECT telegram_id FROM subscriptions WHERE status = 'active'
                )
            """, (prev_month_str,))
            
            expired_users = cursor.fetchall()
            
            # Marquer comme expirés
            cursor.execute("""
                UPDATE payments SET status = 'expired' 
                WHERE month_year = %s AND status = 'completed'
                AND telegram_id NOT IN (
                    SELECT telegram_id FROM subscriptions WHERE status = 'active'
                )
            """ if db.is_postgres else """
                UPDATE payments SET status = 'expired' 
                WHERE month_year = ? AND status = 'completed'
                AND telegram_id NOT IN (
                    SELECT telegram_id FROM subscriptions WHERE status = 'active'
                )
            """, (prev_month_str,))
            
            conn.commit()
        
        # Notifier les utilisateurs que leur accès a expiré (sauf abonnés)
        for user_row in expired_users:
            telegram_id = user_row[0] if db.is_postgres else user_row["telegram_id"]
            try:
                message = "⏰ ACCÈS EXPIRÉ\n\n"
                message += f"Votre accès au Dino Challenge du mois précédent a expiré.\n\n"
                message += f"💰 Pour continuer à jouer ce mois, utilisez /payment\n"
                message += f"🔄 Pour un accès permanent, choisissez l'abonnement mensuel !"
                
                await telegram_app.bot.send_message(
                    chat_id=telegram_id,
                    text=message
                )
            except Exception as e:
                logger.error(f"❌ Erreur notification expiration pour {telegram_id}: {e}")
        
        logger.info(f"🔒 {len(expired_users)} accès expirés pour {prev_month_str}")
        
    except Exception as e:
        logger.error(f"❌ Erreur expire_monthly_access: {e}")

async def monthly_prize_checker():
    """Vérificateur quotidien pour la distribution automatique"""
    last_distribution_month = None
    
    while True:
        try:
            now = datetime.now()
            
            # Vérifier si on est le 1er du mois et après 00:01
            if (now.day == 1 and now.hour >= 0 and now.minute >= 1 and 
                last_distribution_month != now.month):
                
                logger.info("🏆 DÉCLENCHEMENT - Distribution automatique des prix")
                await distribute_monthly_prizes()
                last_distribution_month = now.month
            
            # Attendre 1 heure avant la prochaine vérification
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"❌ Erreur monthly_prize_checker: {e}")
            await asyncio.sleep(3600)  # Attendre 1 heure en cas d'erreur

def run_flask_app():
    """Exécuter l'API Flask"""
    try:
        logger.info(f"🌐 Démarrage de l'API Flask sur le port {PORT}...")
        flask_app.run(host='0.0.0.0', port=PORT, debug=False)
    except Exception as e:
        logger.error(f"❌ Erreur API Flask: {e}")

# =============================================================================
# MAIN - POINT D'ENTRÉE
# =============================================================================

def main():
    """Point d'entrée principal"""
    logger.info("🦕 Démarrage du Dino Challenge Bot + API v2.1")
    
    # Vérifier les variables d'environnement
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN manquant dans .env")
        return
    
    logger.info(f"📊 Base de données: {DATABASE_URL}")
    logger.info(f"🎮 Jeu: {GAME_URL}")
    logger.info(f"👤 Admin: {ORGANIZER_CHAT_ID}")
    logger.info(f"💰 PayPal Mode: {PAYPAL_MODE}")
    
    try:
        # Démarrer Flask dans un thread séparé
        flask_thread = threading.Thread(target=run_flask_app, daemon=True)
        flask_thread.start()
        logger.info("✅ API Flask démarrée en arrière-plan")
        
        # Démarrer le bot Telegram (bloquant)
        asyncio.run(run_telegram_bot())
        
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")

if __name__ == '__main__':
    main()
# Force refresh
