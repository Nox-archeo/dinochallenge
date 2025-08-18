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
import re
import sqlite3
import traceback
import fcntl  # Pour le verrouillage de fichier
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
import json

# Imports pour le bot Telegram
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Imports pour l'API web
from flask import Flask, request, jsonify, render_template_string, redirect
from flask_cors import CORS
import threading
import time
import base64

# Imports pour PayPal
import paypalrestsdk
import hmac
import hashlib
import requests
from decimal import Decimal

# Imports pour la base de données
try:
    # Essayer psycopg3 en premier (plus récent)
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_VERSION = 3
except ImportError:
    try:
        # Fallback vers psycopg2
        import psycopg2 as psycopg
        from psycopg2.extras import RealDictCursor
        PSYCOPG_VERSION = 2
    except ImportError:
        raise ImportError("Installer psycopg ou psycopg2-binary")

import sqlite3
from urllib.parse import urlparse

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Log de la version psycopg utilisée
if PSYCOPG_VERSION == 3:
    logger.info("🔹 Utilisation de psycopg3")
else:
    logger.info("🔹 Utilisation de psycopg2")

# Configuration depuis les variables d'environnement
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///dino_challenge.db')
ORGANIZER_CHAT_ID = int(os.getenv('ORGANIZER_CHAT_ID', '123456789'))
PORT = int(os.getenv('PORT', 5000))
GAME_URL = os.getenv('GAME_URL', 'https://nox-archeo.github.io/dinochallenge/')

# Configuration PayPal - MODE PRODUCTION
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_SECRET_KEY = os.getenv('PAYPAL_SECRET_KEY')
PAYPAL_MODE = os.getenv('PAYPAL_MODE', 'live')  # 'live' par défaut = PRODUCTION
PAYPAL_WEBHOOK_URL = 'https://dinochallenge-bot.onrender.com/paypal-webhook'

# URLs PayPal API v2 - PRODUCTION
PAYPAL_BASE_URL = 'https://api-m.paypal.com' if PAYPAL_MODE == 'live' else 'https://api-m.sandbox.paypal.com'

# Prix en CHF (taxes incluses) - MODE PRODUCTION
MONTHLY_PRICE_CHF = Decimal('11.00')  # Prix final en production

# État des utilisateurs pour les conversations (édition profil)
user_states = {}

# Configuration PayPal SDK (pour la compatibilité) - MODE PRODUCTION
if PAYPAL_CLIENT_ID and PAYPAL_SECRET_KEY:
    paypalrestsdk.configure({
        "mode": PAYPAL_MODE,  # Utilise 'live' par défaut
        "client_id": PAYPAL_CLIENT_ID,
        "client_secret": PAYPAL_SECRET_KEY
    })
    logger.info(f"🏭 PayPal configuré en mode: {PAYPAL_MODE.upper()}")
    logger.info(f"🔗 Base URL PayPal: {PAYPAL_BASE_URL}")

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
            if PSYCOPG_VERSION == 3:
                # psycopg3 syntax
                return psycopg.connect(self.database_url, row_factory=dict_row)
            else:
                # psycopg2 syntax (fallback)
                return psycopg.connect(self.database_url, cursor_factory=RealDictCursor)
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
                            display_name VARCHAR(255),
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
                            display_name TEXT,
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
                
                # Migration : ajouter display_name si elle n'existe pas
                try:
                    if self.is_postgres:
                        cursor.execute("""
                            ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(255)
                        """)
                    else:
                        # Pour SQLite, vérifier si la colonne existe
                        cursor.execute("PRAGMA table_info(users)")
                        columns = [column[1] for column in cursor.fetchall()]
                        if 'display_name' not in columns:
                            cursor.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
                    
                    conn.commit()
                    logger.info("✅ Migration display_name terminée")
                except Exception as migration_error:
                    logger.info(f"Migration display_name ignorée: {migration_error}")

                # Migration : ajouter les colonnes manquantes dans la table payments
                try:
                    if self.is_postgres:
                        # Ajouter payment_type si elle n'existe pas
                        cursor.execute("""
                            ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_type VARCHAR(20) DEFAULT 'one_time'
                        """)
                        # Ajouter paypal_payment_id si elle n'existe pas
                        cursor.execute("""
                            ALTER TABLE payments ADD COLUMN IF NOT EXISTS paypal_payment_id VARCHAR(255)
                        """)
                        # Ajouter paypal_subscription_id si elle n'existe pas
                        cursor.execute("""
                            ALTER TABLE payments ADD COLUMN IF NOT EXISTS paypal_subscription_id VARCHAR(255)
                        """)
                    else:
                        # Pour SQLite, vérifier les colonnes de payments
                        cursor.execute("PRAGMA table_info(payments)")
                        columns = [column[1] for column in cursor.fetchall()]
                        
                        if 'payment_type' not in columns:
                            cursor.execute("ALTER TABLE payments ADD COLUMN payment_type TEXT DEFAULT 'one_time'")
                        if 'paypal_payment_id' not in columns:
                            cursor.execute("ALTER TABLE payments ADD COLUMN paypal_payment_id TEXT")
                        if 'paypal_subscription_id' not in columns:
                            cursor.execute("ALTER TABLE payments ADD COLUMN paypal_subscription_id TEXT")
                    
                    conn.commit()
                    logger.info("✅ Migration table payments terminée")
                except Exception as migration_error:
                    logger.info(f"Migration payments ignorée: {migration_error}")
                
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
    
    def add_score(self, telegram_id: int, score: int) -> Dict:
        """Ajouter un score pour un utilisateur avec vérifications"""
        try:
            # S'assurer que l'utilisateur existe
            user = self.create_or_get_user(telegram_id)
            if not user:
                return {'success': False, 'error': 'Utilisateur non trouvé'}
            
            # Vérifier l'accès premium
            has_access = self.check_user_access(telegram_id)
            if not has_access:
                return {'success': False, 'error': 'Accès premium requis'}

            # VÉRIFIER LA LIMITE AVANT d'ajouter le score
            # Utiliser l'heure française (UTC+2 en été, UTC+1 en hiver)
            from datetime import timezone, timedelta
            
            # Approximation : UTC+2 pour l'été français (à ajuster selon la saison)
            france_tz = timezone(timedelta(hours=2))
            today_france = datetime.now(france_tz).date()
            
            print(f"🕐 Heure serveur UTC: {datetime.now()}")
            print(f"🇫🇷 Date française: {today_france}")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Compter les parties d'aujourd'hui en France AVANT d'ajouter le nouveau score
                cursor.execute("""
                    SELECT COUNT(*) FROM scores 
                    WHERE telegram_id = %s AND DATE(created_at AT TIME ZONE 'Europe/Paris') = %s
                """ if self.is_postgres else """
                    SELECT COUNT(*) FROM scores 
                    WHERE telegram_id = ? AND DATE(created_at, '+2 hours') = ?
                """, (telegram_id, today_france))
                
                result = cursor.fetchone()
                if result:
                    if isinstance(result, dict):
                        daily_games = result['count'] or 0
                    else:
                        daily_games = result[0] if result[0] is not None else 0
                else:
                    daily_games = 0
                
                # Bloquer si déjà 5 parties jouées
                if daily_games >= 5:
                    return {
                        'success': False,
                        'daily_games': daily_games,
                        'remaining_games': 0,
                        'limit_reached': True,
                        'error': 'Limite quotidienne atteinte ! Vous avez déjà joué 5 parties aujourd\'hui. Revenez demain.',
                        'message': 'Limite quotidienne atteinte ! Revenez demain pour 5 nouvelles parties.'
                    }
                
                # Ajouter le score seulement si moins de 5 parties
                current_month = datetime.now().strftime('%Y-%m')
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
                
                daily_games += 1  # Maintenant on a une partie de plus
                conn.commit()
                logger.info(f"✅ Score ajouté: {telegram_id} = {score} (partie {daily_games}/5)")
                
                # Informer si c'était la 5ème partie
                if daily_games >= 5:
                    return {
                        'success': True, 
                        'daily_games': daily_games,
                        'remaining_games': 0,
                        'limit_reached': True,
                        'message': 'Limite quotidienne atteinte ! Revenez demain pour 5 nouvelles parties.'
                    }
                else:
                    return {
                        'success': True, 
                        'daily_games': daily_games,
                        'remaining_games': 5 - daily_games,
                        'limit_reached': False
                    }
                
        except Exception as e:
            logger.error(f"❌ Erreur ajout score: {e}")
            return False
    
    def get_leaderboard(self, month_year: str = None, limit: int = 10) -> List[Dict]:
        """Récupérer le classement"""
        if not month_year:
            month_year = datetime.now().strftime('%Y-%m')
        
        logger.info(f"🏆 Récupération classement pour {month_year}, limite: {limit}")
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # D'abord, vérifier quels scores existent
                cursor.execute("""
                    SELECT telegram_id, score, created_at FROM scores 
                    WHERE month_year = ? ORDER BY telegram_id, score DESC
                """ if not self.is_postgres else """
                    SELECT telegram_id, score, created_at FROM scores 
                    WHERE month_year = %s ORDER BY telegram_id, score DESC
                """, (month_year,))
                
                all_scores = cursor.fetchall()
                logger.info(f"📊 Scores trouvés pour {month_year}: {len(all_scores)}")
                for score in all_scores[:10]:  # Log les 10 premiers
                    if self.is_postgres:
                        logger.info(f"  Score: {score['telegram_id']} = {score['score']} ({score['created_at']})")
                    else:
                        logger.info(f"  Score: {score[0]} = {score[1]} ({score[2]})")
                
                if self.is_postgres:
                    cursor.execute("""
                        SELECT 
                            u.telegram_id,
                            COALESCE(u.display_name, u.first_name, u.username, 'Anonyme') as display_name,
                            u.username,
                            MAX(s.score) as best_score,
                            COUNT(s.id) as total_games,
                            u.has_paid_current_month
                        FROM users u
                        JOIN scores s ON u.telegram_id = s.telegram_id
                        WHERE s.month_year = %s 
                          AND (u.has_paid_current_month = TRUE 
                               OR EXISTS (
                                   SELECT 1 FROM payments p 
                                   WHERE p.telegram_id = u.telegram_id 
                                     AND p.month_year = %s 
                                     AND p.status = 'completed'
                               )
                               OR EXISTS (
                                   SELECT 1 FROM subscriptions sub 
                                   WHERE sub.telegram_id = u.telegram_id 
                                     AND sub.status = 'active'
                               ))
                        GROUP BY u.telegram_id, u.display_name, u.first_name, u.username, u.has_paid_current_month
                        ORDER BY best_score DESC
                        LIMIT %s
                    """, (month_year, month_year, limit))
                else:
                    # Requête SQLite avec même filtre d'accès que PostgreSQL
                    cursor.execute("""
                        SELECT 
                            s.telegram_id,
                            COALESCE(u.display_name, u.first_name, u.username, 'Joueur ' || s.telegram_id) as display_name,
                            u.username,
                            MAX(s.score) as best_score,
                            COUNT(s.id) as total_games,
                            COALESCE(u.has_paid_current_month, 0) as has_paid_current_month
                        FROM scores s
                        LEFT JOIN users u ON s.telegram_id = u.telegram_id
                        WHERE s.month_year = ?
                          AND (u.has_paid_current_month = 1 
                               OR EXISTS (
                                   SELECT 1 FROM payments p 
                                   WHERE p.telegram_id = s.telegram_id 
                                     AND p.month_year = ? 
                                     AND p.status = 'completed'
                               )
                               OR EXISTS (
                                   SELECT 1 FROM subscriptions sub 
                                   WHERE sub.telegram_id = s.telegram_id 
                                     AND sub.status = 'active'
                               ))
                        GROUP BY s.telegram_id, u.display_name, u.first_name, u.username, u.has_paid_current_month
                        ORDER BY best_score DESC
                        LIMIT ?
                    """, (month_year, month_year, limit))
                
                results = cursor.fetchall()
                
                logger.info(f"🏆 Résultats classement: {len(results)} joueurs")
                leaderboard_data = []
                for i, row in enumerate(results):
                    if self.is_postgres:
                        player_data = dict(row)
                    else:
                        # Pour SQLite, créer le dict manuellement
                        player_data = {
                            'telegram_id': row[0],
                            'display_name': row[1],
                            'username': row[2],
                            'best_score': row[3],
                            'total_games': row[4],
                            'has_paid_current_month': row[5]
                        }
                    
                    logger.info(f"  #{i+1}: {player_data['display_name']} = {player_data['best_score']} pts ({player_data['total_games']} parties)")
                    leaderboard_data.append(player_data)
                
                return leaderboard_data
                
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
                
                # D'abord vérifier le champ has_paid_current_month
                cursor.execute("""
                    SELECT has_paid_current_month FROM users 
                    WHERE telegram_id = %s
                """ if self.is_postgres else """
                    SELECT has_paid_current_month FROM users 
                    WHERE telegram_id = ?
                """, (telegram_id,))
                
                result = cursor.fetchone()
                if result:
                    if isinstance(result, dict):
                        has_paid = bool(result['has_paid_current_month'])
                    else:
                        has_paid = bool(result[0])
                    
                    if has_paid:
                        logger.info(f"✅ Accès accordé via has_paid_current_month: {telegram_id}")
                        return True
                
                # Vérifier les paiements uniques pour ce mois
                cursor.execute("""
                    SELECT COUNT(*) FROM payments 
                    WHERE telegram_id = %s AND month_year = %s AND status = 'completed'
                """ if self.is_postgres else """
                    SELECT COUNT(*) FROM payments 
                    WHERE telegram_id = ? AND month_year = ? AND status = 'completed'
                """, (telegram_id, current_month))
                
                result = cursor.fetchone()
                payment_count = 0
                if result:
                    try:
                        # Gérer les dictionnaires (PostgreSQL) et les tuples (SQLite)
                        if isinstance(result, dict):
                            # PostgreSQL avec dict_row
                            payment_count = int(result['count'] or 0)
                        else:
                            # SQLite ou tuple
                            payment_count = int(result[0]) if result[0] is not None else 0
                    except (IndexError, TypeError, ValueError, KeyError) as conv_error:
                        logger.warning(f"⚠️ Erreur conversion payment_count: {conv_error}, result: {result}")
                        payment_count = 0
                
                if payment_count > 0:
                    logger.info(f"✅ Accès accordé via paiement: {telegram_id} ({payment_count} paiements)")
                    return True
                
                # Vérifier les abonnements actifs
                cursor.execute("""
                    SELECT COUNT(*) FROM subscriptions 
                    WHERE telegram_id = %s AND status = 'active'
                """ if self.is_postgres else """
                    SELECT COUNT(*) FROM subscriptions 
                    WHERE telegram_id = ? AND status = 'active'
                """, (telegram_id,))
                
                result = cursor.fetchone()
                subscription_count = 0
                if result:
                    try:
                        # Gérer les dictionnaires (PostgreSQL) et les tuples (SQLite)
                        if isinstance(result, dict):
                            # PostgreSQL avec dict_row
                            subscription_count = int(result['count'] or 0)
                        else:
                            # SQLite ou tuple
                            subscription_count = int(result[0]) if result[0] is not None else 0
                    except (IndexError, TypeError, ValueError, KeyError) as conv_error:
                        logger.warning(f"⚠️ Erreur conversion subscription_count: {conv_error}, result: {result}")
                        subscription_count = 0
                
                access_granted = subscription_count > 0
                if access_granted:
                    logger.info(f"✅ Accès accordé via abonnement: {telegram_id} ({subscription_count} abonnements)")
                else:
                    logger.info(f"❌ Aucun accès: {telegram_id} (paiements: {payment_count}, abonnements: {subscription_count})")
                
                return access_granted
                
        except Exception as e:
            logger.error(f"❌ Erreur vérification accès: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            logger.error(f"❌ Telegram ID: {telegram_id}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    def has_valid_payment(self, telegram_id: int) -> bool:
        """Vérifier si un utilisateur a un paiement valide pour le mois en cours"""
        try:
            current_month = datetime.now().strftime('%Y-%m')
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Vérifier s'il y a un paiement pour ce mois
                if self.is_postgres:
                    cursor.execute("""
                        SELECT COUNT(*) FROM payments 
                        WHERE telegram_id = %s 
                        AND month_year = %s
                        AND amount > 0
                    """, (telegram_id, current_month))
                else:
                    cursor.execute("""
                        SELECT COUNT(*) FROM payments 
                        WHERE telegram_id = ? 
                        AND month_year = ?
                        AND amount > 0
                    """, (telegram_id, current_month))
                
                result = cursor.fetchone()
                if result:
                    if isinstance(result, dict):
                        count = int(result['count'] or 0)
                    else:
                        count = int(result[0]) if result[0] is not None else 0
                    
                    has_payment = count > 0
                    logger.info(f"💰 Paiement valide pour {telegram_id} en {current_month}: {has_payment} ({count} paiements)")
                    return has_payment
                
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur vérification paiement: {e}")
            return False

    def get_daily_games_count(self, telegram_id: int, date_str: str = None) -> int:
        """Compter le nombre de parties jouées aujourd'hui par un utilisateur"""
        try:
            if date_str is None:
                # Utiliser l'heure française (UTC+2 en été, UTC+1 en hiver)
                # Approximation: ajouter 2 heures à UTC pour l'été
                from datetime import timedelta
                now_utc = datetime.utcnow()
                now_paris = now_utc + timedelta(hours=2)  # Heure d'été française
                date_str = now_paris.strftime('%Y-%m-%d')
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Compter les scores enregistrés aujourd'hui
                if self.is_postgres:
                    cursor.execute("""
                        SELECT COUNT(*) FROM scores 
                        WHERE telegram_id = %s 
                        AND DATE(created_at + INTERVAL '2 hours') = %s
                    """, (telegram_id, date_str))
                else:
                    # Pour SQLite, approximation avec UTC (peut être ajustée)
                    cursor.execute("""
                        SELECT COUNT(*) FROM scores 
                        WHERE telegram_id = ? 
                        AND DATE(created_at) = ?
                    """, (telegram_id, date_str))
                
                result = cursor.fetchone()
                if result:
                    if isinstance(result, dict):
                        return int(result['count'] or 0)
                    else:
                        return int(result[0]) if result[0] is not None else 0
                
                return 0
                
        except Exception as e:
            logger.error(f"❌ Erreur comptage parties quotidiennes: {e}")
            return 0

    def update_display_name(self, telegram_id: int, display_name: str) -> bool:
        """Mettre à jour le nom d'affichage de l'utilisateur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        UPDATE users SET display_name = %s WHERE telegram_id = %s
                    """, (display_name, telegram_id))
                else:
                    cursor.execute("""
                        UPDATE users SET display_name = ? WHERE telegram_id = ?
                    """, (display_name, telegram_id))
                
                conn.commit()
                logger.info(f"✅ Nom d'affichage mis à jour: {telegram_id} = {display_name}")
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"❌ Erreur mise à jour nom d'affichage: {e}")
            return False

    def get_user_profile(self, telegram_id: int) -> Dict:
        """Récupérer le profil complet d'un utilisateur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM users WHERE telegram_id = %s
                """ if self.is_postgres else """
                    SELECT * FROM users WHERE telegram_id = ?
                """, (telegram_id,))
                
                user = cursor.fetchone()
                return dict(user) if user else {}
                
        except Exception as e:
            logger.error(f"❌ Erreur récupération profil: {e}")
            return {}

    def get_user_scores(self, telegram_id: int) -> list:
        """Récupérer les scores d'un utilisateur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT score, created_at FROM scores 
                    WHERE telegram_id = %s 
                    ORDER BY score DESC
                """ if self.is_postgres else """
                    SELECT score, created_at FROM scores 
                    WHERE telegram_id = ? 
                    ORDER BY score DESC
                """, (telegram_id,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"❌ Erreur récupération scores: {e}")
            return []

    def update_user_profile(self, telegram_id: int, display_name: str = None, paypal_email: str = None) -> bool:
        """Mettre à jour le profil d'un utilisateur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                updates = []
                values = []
                
                if display_name is not None:
                    updates.append("display_name = %s" if self.is_postgres else "display_name = ?")
                    values.append(display_name)
                
                if paypal_email is not None:
                    if paypal_email.lower() == 'supprimer':
                        updates.append("paypal_email = NULL")
                    else:
                        updates.append("paypal_email = %s" if self.is_postgres else "paypal_email = ?")
                        values.append(paypal_email)
                
                if not updates:
                    return True  # Rien à mettre à jour
                
                values.append(telegram_id)
                
                query = f"""
                    UPDATE users 
                    SET {', '.join(updates)}
                    WHERE telegram_id = {'%s' if self.is_postgres else '?'}
                """
                
                cursor.execute(query, values)
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"❌ Erreur mise à jour profil: {e}")
            return False

    def delete_user_profile(self, telegram_id: int) -> bool:
        """Supprimer complètement le profil d'un utilisateur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Supprimer dans l'ordre pour respecter les contraintes de clés étrangères
                tables = ['payments', 'scores', 'users']
                
                for table in tables:
                    cursor.execute(f"""
                        DELETE FROM {table} WHERE telegram_id = {'%s' if self.is_postgres else '?'}
                    """, (telegram_id,))
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Erreur suppression profil: {e}")
            return False

    def calculate_monthly_prizes(self, month_year: str = None) -> Dict:
        """Calculer les prix du mois basés sur les paiements"""
        if not month_year:
            month_year = datetime.now().strftime('%Y-%m')
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Calculer le total des paiements pour le mois (SEULEMENT les vrais paiements)
                cursor.execute("""
                    SELECT SUM(amount) as total_amount, COUNT(*) as total_players
                    FROM payments 
                    WHERE month_year = %s AND status = 'completed' 
                    AND payment_type NOT IN ('admin_restore', 'test')
                """ if self.is_postgres else """
                    SELECT SUM(amount) as total_amount, COUNT(*) as total_players
                    FROM payments 
                    WHERE month_year = ? AND status = 'completed'
                    AND payment_type NOT IN ('admin_restore', 'test')
                """, (month_year,))
                
                result = cursor.fetchone()
                if not result:
                    total_amount = Decimal('0')
                    total_players = 0
                elif isinstance(result, dict):
                    total_amount = Decimal(str(result['total_amount'] or 0))
                    total_players = result['total_players'] or 0
                else:
                    # Si result est un tuple/liste
                    total_amount = Decimal(str(result[0] or 0))
                    total_players = result[1] or 0
                
                # Calculer les prix selon les pourcentages
                first_prize = total_amount * Decimal('0.40')  # 40%
                second_prize = total_amount * Decimal('0.15')  # 15%
                third_prize = total_amount * Decimal('0.05')   # 5%
                organization_fees = total_amount * Decimal('0.40')  # 40%
                
                return {
                    'month_year': month_year,
                    'total_amount': float(total_amount),
                    'total_players': total_players,
                    'prizes': {
                        'first': float(first_prize),
                        'second': float(second_prize),
                        'third': float(third_prize),
                        'organization_fees': float(organization_fees)
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ Erreur calcul prix mensuels: {e}")
            return {
                'month_year': month_year,
                'total_amount': 0,
                'total_players': 0,
                'prizes': {'first': 0, 'second': 0, 'third': 0, 'organization_fees': 0}
            }
    
    def clean_test_payments(self):
        """Nettoyer tous les paiements de test et admin_restore"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Supprimer tous les paiements de test
                cursor.execute("""
                    DELETE FROM payments 
                    WHERE payment_type IN ('admin_restore', 'test')
                    OR paypal_order_id LIKE '%test%'
                    OR paypal_order_id LIKE '%admin%'
                """ if self.is_postgres else """
                    DELETE FROM payments 
                    WHERE payment_type IN ('admin_restore', 'test')
                    OR paypal_order_id LIKE '%test%'
                    OR paypal_order_id LIKE '%admin%'
                """)
                
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"🧹 Nettoyage: {deleted_count} paiements de test supprimés")
                return deleted_count
                
        except Exception as e:
            logger.error(f"❌ Erreur nettoyage paiements: {e}")
            return 0

    def get_user_position_and_prize(self, telegram_id: int, month_year: str = None) -> Dict:
        """Obtenir la position actuelle d'un utilisateur et son gain potentiel"""
        if not month_year:
            month_year = datetime.now().strftime('%Y-%m')
        
        try:
            # Obtenir le classement complet
            leaderboard = self.get_leaderboard(month_year, 100)  # Top 100 pour être sûr
            
            # Calculer les prix du mois
            prize_info = self.calculate_monthly_prizes(month_year)
            
            # Trouver la position de l'utilisateur
            user_position = None
            user_score = 0
            user_prize = 0
            
            for i, player in enumerate(leaderboard):
                if player['telegram_id'] == telegram_id:
                    user_position = i + 1
                    user_score = player['best_score']
                    
                    # Calculer le gain selon la position
                    if user_position == 1:
                        user_prize = prize_info['prizes']['first']
                    elif user_position == 2:
                        user_prize = prize_info['prizes']['second']
                    elif user_position == 3:
                        user_prize = prize_info['prizes']['third']
                    else:
                        user_prize = 0
                    break
            
            return {
                'position': user_position,
                'score': user_score,
                'prize': user_prize,
                'total_players': len(leaderboard),
                'prize_info': prize_info
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur position et prix utilisateur: {e}")
            return {
                'position': None,
                'score': 0,
                'prize': 0,
                'total_players': 0,
                'prize_info': self.calculate_monthly_prizes(month_year)
            }

    def get_monthly_winners(self, month_year: str = None) -> List[Dict]:
        """Obtenir les 3 gagnants du mois"""
        if not month_year:
            # Mois précédent (pour les notifications en fin de mois)
            last_month = datetime.now().replace(day=1) - timedelta(days=1)
            month_year = last_month.strftime('%Y-%m')
        
        try:
            leaderboard = self.get_leaderboard(month_year, 3)  # Top 3
            prize_info = self.calculate_monthly_prizes(month_year)
            
            winners = []
            for i, player in enumerate(leaderboard):
                position = i + 1
                if position == 1:
                    prize = prize_info['prizes']['first']
                elif position == 2:
                    prize = prize_info['prizes']['second']  
                elif position == 3:
                    prize = prize_info['prizes']['third']
                else:
                    continue
                    
                winners.append({
                    'telegram_id': player['telegram_id'],
                    'display_name': player['display_name'],
                    'position': position,
                    'score': player['best_score'],
                    'prize': prize,
                    'month_year': month_year
                })
            
            return winners
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération gagnants: {e}")
            return []

    def reset_monthly_leaderboard(self) -> bool:
        """Reset du classement mensuel (appelé le 1er de chaque mois)"""
        try:
            current_month = datetime.now().strftime('%Y-%m')
            logger.info(f"🔄 Reset du classement mensuel pour {current_month}")
            
            # Pas besoin de supprimer les scores, ils sont filtrés par month_year
            # Le nouveau mois commence automatiquement
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur reset mensuel: {e}")
            return False

    def get_user_profile_with_paypal(self, telegram_id: int) -> Dict:
        """Récupérer le profil avec info PayPal pour les paiements"""
        try:
            profile = self.get_user_profile(telegram_id)
            if profile and profile.get('paypal_email'):
                return profile
            return None
            
        except Exception as e:
            logger.error(f"❌ Erreur profil PayPal: {e}")
            return None

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
        
        logger.info(f"📥 Réception score: {data}")
        
        if not data:
            logger.error("❌ Aucune donnée reçue")
            return jsonify({'error': 'Aucune donnée reçue'}), 400
        
        telegram_id = data.get('telegram_id') or data.get('user_id')
        score = data.get('score')
        username = data.get('username')
        first_name = data.get('first_name')
        
        logger.info(f"📊 Données parsées: telegram_id={telegram_id}, score={score}, username={username}")
        
        if not telegram_id or score is None:
            logger.error(f"❌ Données manquantes: telegram_id={telegram_id}, score={score}")
            return jsonify({'error': 'telegram_id et score requis'}), 400
        
        # Convertir en entiers
        telegram_id = int(telegram_id)
        score = int(score)
        
        logger.info(f"🎯 Soumission score: {telegram_id} = {score} pts")
        
        # Validation du score
        if score < 0:
            logger.error(f"❌ Score invalide: {score}")
            return jsonify({'error': 'Score invalide'}), 400
        
        # Sauvegarder le score
        result = db.add_score(telegram_id, score)
        logger.info(f"💾 Résultat sauvegarde: {result}")
        
        if result['success']:
            # Notifier le bot Telegram si possible (compatible Flask)
            if telegram_app:
                def run_score_notification():
                    try:
                        asyncio.run(notify_new_score(telegram_id, score))
                    except Exception as notif_error:
                        logger.error(f"❌ Erreur notification score: {notif_error}")
                
                notification_thread = threading.Thread(target=run_score_notification)
                notification_thread.daemon = True
                notification_thread.start()
            
            return jsonify({
                'success': True,
                'message': 'Score enregistré avec succès',
                'score': score,
                'telegram_id': telegram_id,
                'daily_games': result.get('daily_games', 1),
                'remaining_games': result.get('remaining_games', 4)
            })
        else:
            return jsonify({'error': result.get('error', 'Erreur lors de l\'enregistrement')}), 400
            
    except Exception as e:
        logger.error(f"❌ Erreur soumission score: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/reset-leaderboard', methods=['DELETE'])
def reset_leaderboard():
    """Reset complet du classement - ATTENTION: efface tous les scores"""
    try:
        data = request.get_json()
        if not data or data.get('confirm') != True:
            return jsonify({'error': 'Confirmation requise: {"confirm": true}'}), 400
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Supprimer tous les scores
            cursor.execute("DELETE FROM scores")
            
            if db.is_postgres:
                # Reset de la séquence PostgreSQL
                cursor.execute("ALTER SEQUENCE scores_id_seq RESTART WITH 1")
            
            conn.commit()
            
        logger.info("🗑️ RESET CLASSEMENT: Tous les scores supprimés")
        return jsonify({
            'success': True,
            'message': 'Classement remis à zéro - tous les scores supprimés'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur reset classement: {e}")
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

@flask_app.route('/api/check_access', methods=['GET'])
def check_game_access():
    """Vérifier l'accès au jeu pour un utilisateur"""
    try:
        telegram_id = request.args.get('telegram_id')
        mode = request.args.get('mode', 'demo')
        
        logger.info(f"🎮 Vérification accès - telegram_id: {telegram_id}, mode: {mode}")
        
        # Validation des paramètres
        if not telegram_id:
            logger.warning("⚠️ telegram_id manquant, mode démo activé")
            return jsonify({
                'can_play': True,
                'mode': 'demo',
                'unlimited': True,
                'message': 'Mode démo - accès illimité'
            })
        
        try:
            telegram_id = int(telegram_id)
        except ValueError:
            logger.warning(f"⚠️ telegram_id invalide: {telegram_id}, mode démo activé")
            return jsonify({
                'can_play': True,
                'mode': 'demo',
                'unlimited': True,
                'message': 'Mode démo - accès illimité'
            })
        
        # En mode démo, tout le monde peut jouer
        if mode == 'demo':
            logger.info(f"✅ Mode démo autorisé pour {telegram_id}")
            return jsonify({
                'can_play': True,
                'mode': 'demo',
                'unlimited': True,
                'message': 'Mode démo - accès illimité'
            })
        
        # En mode compétition, vérifier l'accès
        try:
            # Vérifier si l'utilisateur a un paiement valide dans la base de données
            has_access = db.has_valid_payment(telegram_id)
            logger.info(f"💰 Statut paiement pour {telegram_id}: {has_access}")
            
            if not has_access:
                return jsonify({
                    'can_play': False,
                    'mode': mode,
                    'error': 'Accès refusé',
                    'message': 'Effectuez un paiement pour jouer'
                }), 402
            
            # Vérifier la limite quotidienne de 5 parties en mode compétition
            daily_games = db.get_daily_games_count(telegram_id)
            max_daily_games = 5  # Limite de 5 parties par jour
            
            remaining_games = max_daily_games - daily_games
            limit_reached = remaining_games <= 0
            
            logger.info(f"📊 Parties quotidiennes pour {telegram_id}: {daily_games}/5 (restantes: {remaining_games})")
            
            if limit_reached:
                return jsonify({
                    'can_play': False,
                    'mode': mode,
                    'unlimited': False,
                    'daily_games': daily_games,
                    'remaining_games': 0,
                    'limit_reached': True,
                    'error': 'Limite quotidienne atteinte',
                    'message': 'Vous avez atteint votre limite de 5 parties par jour. Revenez demain !'
                }), 429
            
            # Utilisateur payant avec parties restantes
            return jsonify({
                'can_play': True,
                'mode': mode,
                'unlimited': False,
                'daily_games': daily_games,
                'remaining_games': remaining_games,
                'limit_reached': False,
                'message': f'Parties restantes aujourd\'hui: {remaining_games}/5'
            })
            
        except Exception as access_error:
            logger.error(f"❌ Erreur vérification accès: {access_error}")
            # En cas d'erreur, basculer en mode démo
            return jsonify({
                'can_play': True,
                'mode': 'demo',
                'unlimited': True,
                'error': 'Erreur serveur, mode démo activé'
            })
        
    except Exception as e:
        logger.error(f"❌ Erreur critique vérification accès: {e}")
        # En cas d'erreur critique, autoriser le mode démo
        return jsonify({
            'can_play': True,
            'mode': 'demo',
            'unlimited': True,
            'error': 'Erreur serveur, mode démo activé'
        })

# FONCTIONS PAYPAL API V2
# =============================================================================

def get_paypal_access_token():
    """Obtenir un token d'accès PayPal"""
    try:
        logger.info(f"🔍 Demande token PayPal - Mode: {PAYPAL_MODE}")
        logger.info(f"🔍 URL: {PAYPAL_BASE_URL}/v1/oauth2/token")
        logger.info(f"🔍 Client ID présent: {'Oui' if PAYPAL_CLIENT_ID else 'Non'}")
        logger.info(f"🔍 Secret présent: {'Oui' if PAYPAL_SECRET_KEY else 'Non'}")
        
        url = f"{PAYPAL_BASE_URL}/v1/oauth2/token"
        
        headers = {
            'Accept': 'application/json',
            'Accept-Language': 'en_US',
        }
        
        auth = (PAYPAL_CLIENT_ID, PAYPAL_SECRET_KEY)
        data = {'grant_type': 'client_credentials'}
        
        logger.info(f"🔄 Envoi requête token PayPal...")
        response = requests.post(url, headers=headers, data=data, auth=auth)
        
        logger.info(f"📥 Réponse token - Status: {response.status_code}")
        logger.info(f"📥 Réponse token - Content: {response.text}")
        
        if response.status_code == 200:
            token = response.json().get('access_token')
            logger.info(f"✅ Token PayPal obtenu avec succès")
            return token
        else:
            logger.error(f"❌ Erreur token PayPal: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Erreur get_paypal_access_token: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return None

def create_paypal_order(telegram_id: int, amount: Decimal, currency: str = 'CHF'):
    """Créer une commande PayPal v2 (supporte cartes bancaires)"""
    try:
        logger.info(f"🔍 Début création commande PayPal - telegram_id: {telegram_id}, amount: {amount}")
        
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("❌ Token PayPal manquant")
            return None
        
        logger.info(f"✅ Token PayPal obtenu: {access_token[:20]}...")
        
        url = f"{PAYPAL_BASE_URL}/v2/checkout/orders"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'PayPal-Request-Id': f'dino_{telegram_id}_{int(time.time())}'
        }
        
        # Données de la commande avec structure PayPal v2 correcte
        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": f"dino_monthly_{telegram_id}",
                "amount": {
                    "currency_code": currency,
                    "value": str(amount)
                },
                "description": f"Dino Challenge - Accès mensuel pour {datetime.now().strftime('%B %Y')}"
            }],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "payment_method_preference": "UNRESTRICTED",
                        "user_action": "PAY_NOW"
                    }
                }
            },
            "application_context": {
                "brand_name": "Dino Challenge",
                "locale": "fr-CH",
                "landing_page": "BILLING",  # Force l'affichage des options de paiement
                "shipping_preference": "NO_SHIPPING",
                "payment_method_preference": "UNRESTRICTED",  # Permet tous types de paiements
                "return_url": f"https://dinochallenge-bot.onrender.com/payment-success?telegram_id={telegram_id}",
                "cancel_url": f"{GAME_URL}?payment=cancelled"
            }
        }
        
        logger.info(f"🔄 Envoi requête PayPal vers: {url}")
        logger.info(f"🔄 Headers: {headers}")
        logger.info(f"🔄 Data: {json.dumps(order_data, indent=2)}")
        
        response = requests.post(url, headers=headers, json=order_data)
        
        logger.info(f"📥 Réponse PayPal - Status: {response.status_code}")
        logger.info(f"📥 Réponse PayPal - Headers: {dict(response.headers)}")
        logger.info(f"📥 Réponse PayPal - Content: {response.text}")
        
        # PayPal peut renvoyer 200 ou 201 pour une commande créée avec succès
        if response.status_code in [200, 201]:
            order = response.json()
            order_id = order.get('id')
            order_status = order.get('status')
            
            logger.info(f"✅ Commande PayPal créée: {order_id} - Status: {order_status}")
            
            # Vérifier que les liens utilisent l'environnement PRODUCTION
            for link in order.get('links', []):
                rel = link.get('rel')
                if rel in ['approve', 'payer-action']:
                    approve_url = link.get('href', '')
                    if PAYPAL_MODE == 'live' and 'paypal.com' in approve_url and 'sandbox' not in approve_url:
                        logger.info(f"✅ URL d'approbation PRODUCTION ({rel}): {approve_url}")
                    elif PAYPAL_MODE == 'sandbox' and 'sandbox.paypal.com' in approve_url:
                        logger.info(f"✅ URL d'approbation SANDBOX ({rel}): {approve_url}")
                    else:
                        logger.warning(f"⚠️ URL d'approbation inattendue ({rel}): {approve_url}")
            return order
        else:
            logger.error(f"❌ Erreur création commande PayPal ({response.status_code}): {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Erreur create_paypal_order: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return None

# =============================================================================
# ENDPOINTS PAYPAL
# =============================================================================

@flask_app.route('/create-payment', methods=['GET', 'POST'])
def create_payment():
    """Créer un paiement unique PayPal avec support carte bancaire"""
    try:
        # Gérer les requêtes GET (depuis les liens Telegram)
        if request.method == 'GET':
            telegram_id = request.args.get('telegram_id')
            if not telegram_id:
                return jsonify({'error': 'telegram_id requis'}), 400
            # Traiter comme une requête POST avec les données de l'URL
            data = {'telegram_id': telegram_id}
        else:
            # Requête POST normale
            data = request.get_json()
            telegram_id = data.get('telegram_id')
            
            if not telegram_id:
                return jsonify({'error': 'telegram_id requis'}), 400
        
        # Créer la commande PayPal v2 (supporte cartes bancaires)
        order = create_paypal_order(int(telegram_id), MONTHLY_PRICE_CHF)
        
        if order:
            # Trouver l'URL d'approbation (peut être 'approve' ou 'payer-action')
            approval_url = None
            for link in order.get('links', []):
                rel = link.get('rel')
                if rel == 'approve' or rel == 'payer-action':
                    approval_url = link.get('href')
                    break
            
            if approval_url:
                # Si c'est une requête GET, rediriger directement vers PayPal
                if request.method == 'GET':
                    return redirect(approval_url)
                
                # Si c'est une requête POST, retourner le JSON
                return jsonify({
                    'order_id': order['id'],
                    'approval_url': approval_url,
                    'telegram_id': telegram_id,
                    'status': order['status']
                })
            else:
                return jsonify({'error': 'URL d\'approbation non trouvée'}), 500
        else:
            return jsonify({'error': 'Erreur création commande PayPal'}), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur endpoint create-payment: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/capture-payment', methods=['POST'])
def capture_payment():
    """Capturer un paiement PayPal après approbation"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        telegram_id_from_request = data.get('telegram_id')  # ID reçu depuis le frontend
        
        if not order_id:
            return jsonify({'error': 'order_id requis'}), 400
        
        logger.info(f"🔍 Capture paiement - order_id: {order_id}, telegram_id_request: {telegram_id_from_request}")
        
        # Capturer le paiement
        access_token = get_paypal_access_token()
        if not access_token:
            return jsonify({'error': 'Erreur authentification PayPal'}), 500
        
        url = f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        
        response = requests.post(url, headers=headers, json={})
        
        if response.status_code == 201:
            capture_data = response.json()
            logger.info(f"✅ Paiement capturé: {order_id}")
            
            # Extraire les informations du paiement
            purchase_unit = capture_data.get('purchase_units', [{}])[0]
            capture = purchase_unit.get('payments', {}).get('captures', [{}])[0]
            amount = Decimal(capture.get('amount', {}).get('value', '0'))
            
            # Prioriser le telegram_id reçu depuis le frontend, sinon extraire du reference_id
            telegram_id = None
            if telegram_id_from_request:
                try:
                    telegram_id = int(telegram_id_from_request)
                    logger.info(f"✅ Utilisation telegram_id depuis requête: {telegram_id}")
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ telegram_id invalide depuis requête: {telegram_id_from_request}")
            
            # Fallback: extraire depuis reference_id si pas fourni en requête
            if not telegram_id:
                reference_id = purchase_unit.get('reference_id', '')
                if reference_id.startswith('dino_monthly_'):
                    try:
                        telegram_id = int(reference_id.replace('dino_monthly_', ''))
                        logger.info(f"✅ Utilisation telegram_id depuis reference_id: {telegram_id}")
                    except ValueError:
                        logger.error(f"❌ reference_id invalide: {reference_id}")
            
            if telegram_id and amount >= MONTHLY_PRICE_CHF:
                logger.info(f"🔄 Enregistrement paiement: {telegram_id} = {amount} CHF")
                # Enregistrer le paiement
                success = db.record_payment(
                    telegram_id=telegram_id,
                    amount=amount,
                    payment_type='one_time',
                    paypal_payment_id=order_id
                )
                
                if success:
                    # Notifier l'utilisateur en arrière-plan (compatible Flask)
                    if telegram_app:
                        # Utiliser threading pour exécuter la notification async dans Flask
                        import threading
                        def run_notification():
                            try:
                                asyncio.run(notify_payment_success(telegram_id, amount, 'paiement'))
                            except Exception as notif_error:
                                logger.error(f"❌ Erreur notification paiement: {notif_error}")
                        
                        notification_thread = threading.Thread(target=run_notification)
                        notification_thread.daemon = True
                        notification_thread.start()
                    
                    return jsonify({
                        'success': True,
                        'order_id': order_id,
                        'amount': str(amount),
                        'telegram_id': telegram_id
                    })
                else:
                    return jsonify({'error': 'Erreur enregistrement paiement'}), 500
            else:
                return jsonify({'error': 'Données de paiement invalides'}), 400
        else:
            logger.error(f"❌ Erreur capture PayPal: {response.text}")
            return jsonify({'error': 'Erreur capture paiement'}), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur endpoint capture-payment: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/payment-success', methods=['GET'])
def payment_success():
    """Page de confirmation de paiement avec capture automatique"""
    telegram_id = request.args.get('telegram_id')
    token = request.args.get('token')  # PayPal order ID
    
    if not telegram_id or not token:
        return "❌ Paramètres manquants", 400
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🦕 Paiement Dino Challenge</title>
        <meta charset="utf-8">
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                max-width: 600px; 
                margin: 0 auto; 
                padding: 20px;
                text-align: center;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            .container {{
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
            }}
            .loading {{
                animation: spin 2s linear infinite;
                font-size: 3em;
                margin: 20px 0;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            .success {{
                color: #4CAF50;
                font-size: 4em;
                margin: 20px 0;
            }}
            .error {{
                color: #f44336;
                font-size: 3em;
                margin: 20px 0;
            }}
            .btn {{
                background: #4CAF50;
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 25px;
                font-size: 16px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin: 10px;
            }}
            .btn:hover {{
                background: #45a049;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🦕 Dino Challenge</h1>
            <div id="loading">
                <div class="loading">⟳</div>
                <h2>Finalisation de votre paiement...</h2>
                <p>Veuillez patienter, nous confirmons votre paiement.</p>
            </div>
            
            <div id="success" style="display: none;">
                <div class="success">✅</div>
                <h2>Paiement confirmé !</h2>
                <p>Votre accès au Dino Challenge est maintenant activé !</p>
                <a href="{GAME_URL}?telegram_id={telegram_id}&mode=competition" class="btn">🎮 Jouer maintenant en mode classé</a>
                <p><small>Vous pouvez fermer cette page</small></p>
            </div>
            
            <div id="error" style="display: none;">
                <div class="error">❌</div>
                <h2>Erreur de paiement</h2>
                <p id="error-message">Une erreur est survenue lors de la confirmation.</p>
                <a href="javascript:location.reload()" class="btn">🔄 Réessayer</a>
            </div>
        </div>
        
        <script>
            async function capturePayment() {{
                try {{
                    const response = await fetch('/capture-payment', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            order_id: '{token}',
                            telegram_id: '{telegram_id}'
                        }})
                    }});
                    
                    const data = await response.json();
                    
                    if (data.success) {{
                        document.getElementById('loading').style.display = 'none';
                        document.getElementById('success').style.display = 'block';
                        
                        // Rediriger vers le jeu après 3 secondes
                        setTimeout(() => {{
                            window.location.href = '{GAME_URL}?telegram_id={telegram_id}&mode=competition&payment=success';
                        }}, 3000);
                    }} else {{
                        throw new Error(data.error || 'Erreur inconnue');
                    }}
                }} catch (error) {{
                    console.error('Erreur:', error);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('error').style.display = 'block';
                    document.getElementById('error-message').textContent = error.message;
                }}
            }}
            
            // Capturer le paiement automatiquement au chargement
            window.onload = function() {{
                setTimeout(capturePayment, 1000);
            }};
        </script>
    </body>
    </html>
    """
    
    return html

@flask_app.route('/create-subscription', methods=['GET', 'POST'])
def create_subscription():
    """Créer un abonnement mensuel PayPal v2"""
    try:
        # Gérer les requêtes GET (depuis les liens Telegram)
        if request.method == 'GET':
            telegram_id = request.args.get('telegram_id')
            if not telegram_id:
                return jsonify({'error': 'telegram_id requis'}), 400
        else:
            # Requête POST normale
            data = request.get_json()
            telegram_id = data.get('telegram_id')
            
            if not telegram_id:
                return jsonify({'error': 'telegram_id requis'}), 400
        
        logger.info(f"🔄 Création abonnement PayPal v2 pour {telegram_id}")
        
        # Créer le plan d'abonnement (si pas déjà créé)
        plan_id = create_subscription_plan()
        if not plan_id:
            return jsonify({'error': 'Erreur création plan abonnement'}), 500
        
        # Créer l'abonnement
        subscription_data = create_paypal_subscription(telegram_id, plan_id)
        if not subscription_data:
            return jsonify({'error': 'Erreur création abonnement'}), 500
        
        # Si c'est une requête GET, rediriger directement vers PayPal
        if request.method == 'GET':
            return redirect(subscription_data['approval_url'])
        
        # Si c'est une requête POST, retourner le JSON
        return jsonify(subscription_data)
            
    except Exception as e:
        logger.error(f"❌ Erreur endpoint create-subscription: {e}")
        return jsonify({'error': str(e)}), 500

def create_subscription_plan():
    """Créer un plan d'abonnement PayPal v2"""
    try:
        logger.info(f"🔍 Création plan abonnement PayPal v2")
        
        # D'abord créer le produit si nécessaire
        product_id = create_paypal_product()
        if not product_id:
            logger.error("❌ Impossible de créer le produit PayPal")
            return None
        
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("❌ Token PayPal manquant pour plan")
            return None
        
        url = f"{PAYPAL_BASE_URL}/v1/billing/plans"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'PayPal-Request-Id': f'plan_dino_{int(time.time())}'
        }
        
        plan_data = {
            "product_id": product_id,
            "name": "Dino Challenge - Abonnement Mensuel",
            "description": "Accès mensuel au jeu Dino Challenge avec classement",
            "status": "ACTIVE",
            "billing_cycles": [
                {
                    "frequency": {
                        "interval_unit": "MONTH",
                        "interval_count": 1
                    },
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,  # 0 = infini
                    "pricing_scheme": {
                        "fixed_price": {
                            "value": str(MONTHLY_PRICE_CHF),
                            "currency_code": "CHF"
                        }
                    }
                }
            ],
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "setup_fee": {
                    "value": "0",
                    "currency_code": "CHF"
                },
                "setup_fee_failure_action": "CONTINUE",
                "payment_failure_threshold": 3
            }
        }
        
        response = requests.post(url, headers=headers, json=plan_data)
        
        if response.status_code == 201:
            plan = response.json()
            plan_id = plan['id']
            logger.info(f"✅ Plan abonnement créé: {plan_id}")
            return plan_id
        else:
            logger.error(f"❌ Erreur création plan: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Erreur create_subscription_plan: {e}")
        return None

def create_paypal_product():
    """Créer un produit PayPal v2 pour l'abonnement"""
    try:
        logger.info(f"🔍 Création produit PayPal v2")
        
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("❌ Token PayPal manquant pour produit")
            return None
        
        url = f"{PAYPAL_BASE_URL}/v1/catalogs/products"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'PayPal-Request-Id': f'product_dino_{int(time.time())}'
        }
        
        product_data = {
            "id": "DINO_CHALLENGE_PRODUCT",
            "name": "Dino Challenge - Jeu Premium",
            "description": "Accès premium au jeu Dino Challenge avec classements mensuels et prix",
            "type": "SERVICE",
            "category": "SOFTWARE",
            "image_url": "https://dinochallenge-bot.onrender.com/assets/offline-sprite-1x.png",
            "home_url": GAME_URL
        }
        
        response = requests.post(url, headers=headers, json=product_data)
        
        if response.status_code == 201:
            product = response.json()
            product_id = product['id']
            logger.info(f"✅ Produit PayPal créé: {product_id}")
            return product_id
        elif response.status_code == 409:
            # Produit existe déjà
            logger.info(f"✅ Produit PayPal existe déjà: DINO_CHALLENGE_PRODUCT")
            return "DINO_CHALLENGE_PRODUCT"
        else:
            logger.error(f"❌ Erreur création produit: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Erreur create_paypal_product: {e}")
        return None

def create_paypal_subscription(telegram_id: int, plan_id: str):
    """Créer un abonnement PayPal v2"""
    try:
        logger.info(f"🔍 Création abonnement PayPal v2 - telegram_id: {telegram_id}, plan: {plan_id}")
        
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("❌ Token PayPal manquant pour abonnement")
            return None
        
        url = f"{PAYPAL_BASE_URL}/v1/billing/subscriptions"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'PayPal-Request-Id': f'sub_dino_{telegram_id}_{int(time.time())}'
        }
        
        subscription_data = {
            "plan_id": plan_id,
            "start_time": (datetime.utcnow() + timedelta(minutes=1)).isoformat() + "Z",
            "custom_id": f"dino_user_{telegram_id}",
            "application_context": {
                "brand_name": "Dino Challenge",
                "locale": "fr-CH",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "SUBSCRIBE_NOW",
                "return_url": f"{GAME_URL}?telegram_id={telegram_id}&subscription=success",
                "cancel_url": f"{GAME_URL}?telegram_id={telegram_id}&subscription=cancelled"
            }
        }
        
        response = requests.post(url, headers=headers, json=subscription_data)
        
        if response.status_code == 201:
            subscription = response.json()
            subscription_id = subscription['id']
            
            # Trouver l'URL d'approbation
            approval_url = None
            for link in subscription.get('links', []):
                if link['rel'] == 'approve':
                    approval_url = link['href']
                    break
            
            logger.info(f"✅ Abonnement créé: {subscription_id}")
            
            return {
                'subscription_id': subscription_id,
                'approval_url': approval_url,
                'telegram_id': telegram_id,
                'plan_id': plan_id
            }
        else:
            logger.error(f"❌ Erreur création abonnement: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Erreur create_paypal_subscription: {e}")
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
                # Notifier l'utilisateur (compatible Flask)
                def run_payment_notification():
                    try:
                        asyncio.run(notify_payment_success(telegram_id, amount, 'paiement'))
                    except Exception as notif_error:
                        logger.error(f"❌ Erreur notification paiement webhook: {notif_error}")
                
                notification_thread = threading.Thread(target=run_payment_notification)
                notification_thread.daemon = True
                notification_thread.start()
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
                
                # Notifier l'utilisateur (compatible Flask)
                def run_subscription_notification():
                    try:
                        asyncio.run(notify_payment_success(telegram_id, MONTHLY_PRICE_CHF, 'abonnement'))
                    except Exception as notif_error:
                        logger.error(f"❌ Erreur notification abonnement: {notif_error}")
                
                notification_thread = threading.Thread(target=run_subscription_notification)
                notification_thread.daemon = True
                notification_thread.start()
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
                # Notifier le renouvellement (compatible Flask)
                def run_renewal_notification():
                    try:
                        asyncio.run(notify_subscription_renewal(telegram_id, amount))
                    except Exception as notif_error:
                        logger.error(f"❌ Erreur notification renouvellement: {notif_error}")
                
                notification_thread = threading.Thread(target=run_renewal_notification)
                notification_thread.daemon = True
                notification_thread.start()
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
            if result:
                # Gérer les dictionnaires (PostgreSQL) et les tuples (SQLite)
                if isinstance(result, dict):
                    return result['telegram_id']
                else:
                    return result[0]
            return None
            
    except Exception as e:
        logger.error(f"❌ Erreur get_telegram_id_from_subscription: {e}")
        return None

# =============================================================================
# BOT TELEGRAM
# =============================================================================

async def notify_payment_success(telegram_id: int, amount: Decimal, payment_type: str):
    """Notifier le succès d'un paiement et recalculer les gains"""
    try:
        if payment_type == 'abonnement':
            message = f"✅ **Abonnement Activé !**\n\n"
            message += f"💰 **Montant :** {amount} CHF/mois\n"
            message += f"🔄 **Type :** Abonnement mensuel automatique\n"
            message += f"📅 **Prochain prélèvement :** {(datetime.now() + timedelta(days=30)).strftime('%d/%m/%Y')}\n\n"
            message += f"🎮 **Accès activé pour le jeu !**\n"
            message += f"🔗 Jouez ici : {GAME_URL}\n\n"
            message += f"ℹ️ Vous pouvez annuler votre abonnement à tout moment via /cancel_subscription"
        else:
            message = f"✅ **Paiement Confirmé !**\n\n"
            message += f"💰 **Montant :** {amount} CHF\n"
            message += f"📅 **Valable jusqu'au :** {datetime.now().replace(day=1).replace(month=datetime.now().month+1 if datetime.now().month < 12 else 1, year=datetime.now().year+1 if datetime.now().month == 12 else datetime.now().year).strftime('%d/%m/%Y')}\n\n"
            message += f"🎮 **Accès activé pour ce mois !**\n"
            message += f"🔗 Jouez ici : {GAME_URL}\n\n"
            message += f"💡 Pour un accès permanent, choisissez l'abonnement mensuel avec /payment"
        
        # Calculer et afficher les nouveaux gains
        current_month = datetime.now().strftime('%Y-%m')
        prize_info = db.calculate_monthly_prizes(current_month)
        
        message += f"\n\n🏆 **CAGNOTTE MISE À JOUR !**\n"
        message += f"💰 **Total : {prize_info['total_amount']:.2f} CHF** ({prize_info['total_players']} joueurs)\n"
        message += f"🥇 1er : {prize_info['prizes']['first']:.2f} CHF\n"
        message += f"🥈 2e : {prize_info['prizes']['second']:.2f} CHF\n"
        message += f"🥉 3e : {prize_info['prizes']['third']:.2f} CHF\n\n"
        message += f"🎯 **Jouez maintenant pour remporter ces prix !**"
        
        if telegram_app:
            await telegram_app.send_message(
                chat_id=telegram_id,
                text=message,
                
            )
        
    except Exception as e:
        logger.error(f"❌ Erreur notification paiement: {e}")

async def notify_subscription_renewal(telegram_id: int, amount: Decimal):
    """Notifier le renouvellement d'abonnement"""
    try:
        message = f"🔄 **Abonnement Renouvelé !**\n\n"
        message += f"💰 **Montant :** {amount} CHF\n"
        message += f"📅 **Période :** {datetime.now().strftime('%B %Y')}\n"
        message += f"📅 **Prochain prélèvement :** {(datetime.now() + timedelta(days=30)).strftime('%d/%m/%Y')}\n\n"
        message += f"🎮 **Votre accès continue !**\n"
        message += f"🔗 Jouez ici : {GAME_URL}"
        
        if telegram_app:
            await telegram_app.send_message(
                chat_id=telegram_id,
                text=message,
                
            )
        
    except Exception as e:
        logger.error(f"❌ Erreur notification renouvellement: {e}")

async def notify_new_score(telegram_id: int, score: int):
    """Notifier un nouveau score avec calcul automatique des gains"""
    try:
        # Obtenir la position et les gains de l'utilisateur
        position_info = db.get_user_position_and_prize(telegram_id)
        prize_info = position_info['prize_info']
        
        message = f"🎮 **Nouveau Score Enregistré !**\n\n"
        message += f"🎯 **Score :** {score:,} points\n"
        
        if position_info['position']:
            message += f"🏆 **Position :** {position_info['position']}/{position_info['total_players']}\n\n"
            
            # Afficher les gains potentiels
            if position_info['prize'] > 0:
                if position_info['position'] == 1:
                    message += f"🥇 **FÉLICITATIONS ! Vous êtes 1er !**\n"
                    message += f"💰 **Gain actuel :** {position_info['prize']:.2f} CHF\n"
                elif position_info['position'] == 2:
                    message += f"🥈 **Excellent ! Vous êtes 2e !**\n"
                    message += f"💰 **Gain actuel :** {position_info['prize']:.2f} CHF\n"
                elif position_info['position'] == 3:
                    message += f"🥉 **Bravo ! Vous êtes 3e !**\n"
                    message += f"💰 **Gain actuel :** {position_info['prize']:.2f} CHF\n"
                
                message += f"\n📊 **Cagnotte actuelle :**\n"
                message += f"• 🥇 1er : {prize_info['prizes']['first']:.2f} CHF\n"
                message += f"• 🥈 2e : {prize_info['prizes']['second']:.2f} CHF\n"
                message += f"• 🥉 3e : {prize_info['prizes']['third']:.2f} CHF\n"
                message += f"• 👥 {prize_info['total_players']} joueurs ({prize_info['total_amount']:.2f} CHF collectés)\n"
            else:
                message += f"💡 **Top 3 pour gagner !**\n"
                message += f"🎯 Battez le score du 3e pour gagner {prize_info['prizes']['third']:.2f} CHF !\n\n"
                message += f"📊 **Cagnotte actuelle :**\n"
                message += f"• 🥇 1er : {prize_info['prizes']['first']:.2f} CHF\n"
                message += f"• 🥈 2e : {prize_info['prizes']['second']:.2f} CHF\n"
                message += f"• 🥉 3e : {prize_info['prizes']['third']:.2f} CHF\n"
        else:
            message += f"❌ **Non classé** (paiement requis)\n"
            message += f"💡 Payez votre participation avec /payment pour être classé !\n"
        
        message += f"\n🎮 Continuez à jouer : {GAME_URL}"
        message += f"\n🏆 Classement : /leaderboard"
        
        if telegram_app:
            await telegram_app.send_message(
                chat_id=telegram_id,
                text=message,
                
            )
        
    except Exception as e:
        logger.error(f"❌ Erreur notification nouveau score: {e}")

async def notify_new_score(telegram_id: int, score: int):
    """Notifier l'utilisateur de son nouveau score"""
    try:
        # Vérifier si l'utilisateur a accès
        has_access = db.check_user_access(telegram_id)
        
        if not has_access:
            message = f"🎮 **Score enregistré !**\n\n"
            message += f"📊 **Score :** {score:,} points\n\n"
            message += f"⚠️ **Accès limité** - Pour participer au concours mensuel :\n"
            message += f"💰 Payez {MONTHLY_PRICE_CHF} CHF avec /payment\n"
            message += f"🏆 Tentez de gagner les prix mensuels !"
        else:
            message = f"🎮 **Nouveau score enregistré !**\n\n"
            message += f"📊 **Score :** {score:,} points\n"
            message += f"🕒 **Enregistré le :** {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n\n"
            message += f"🏆 Tapez /leaderboard pour voir le classement !"
        
        if telegram_app:
            await telegram_app.send_message(
                chat_id=telegram_id,
                text=message,
                
            )
    except Exception as e:
        logger.error(f"❌ Erreur notification score: {e}")

# Ancien handlers supprimés - remplacés par les fonctions manuelles

def setup_telegram_bot():
    """Configurer le bot Telegram avec approche minimaliste"""
    global telegram_app
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN manquant !")
        return None
    
    # Approche minimaliste - créer seulement le Bot, pas d'Application
    from telegram import Bot
    telegram_app = Bot(token=TELEGRAM_BOT_TOKEN)
    
    logger.info("✅ Bot Telegram configuré (mode minimal)")
    return telegram_app

async def process_update_manually(bot, update):
    """Traiter manuellement les mises à jour"""
    try:
        if update.message:
            # Messages texte
            text = update.message.text
            user = update.message.from_user
            
            # Vérifier si l'utilisateur est en cours de configuration
            if user.id in user_states:
                state = user_states[user.id]
                
                if state == "waiting_for_name":
                    # Valider le nom
                    if text and len(text.strip()) >= 2 and len(text.strip()) <= 30:
                        # Sauvegarder le nom temporairement
                        display_name = text.strip()
                        
                        # Demander l'email PayPal
                        await bot.send_message(
                            chat_id=update.message.chat_id,
                            text="✅ **Nom enregistré !**\n\n" +
                                 "**Étape 2/2 : Email PayPal (optionnel)**\n\n" +
                                 "📧 Renseignez votre email PayPal pour recevoir vos gains en cas de victoire.\n\n" +
                                 "💡 Vous pouvez taper 'passer' si vous préférez le renseigner plus tard.\n\n" +
                                 "📝 Envoyez votre email PayPal :",
                            
                        )
                        user_states[user.id] = f"waiting_for_email:{display_name}"
                    else:
                        await bot.send_message(
                            chat_id=update.message.chat_id,
                            text="❌ **Nom invalide**\n\n" +
                                 "Le nom doit contenir entre 2 et 30 caractères.\n" +
                                 "📝 Envoyez-moi un nouveau nom :"
                        )
                    return
                
                elif state.startswith("waiting_for_email:"):
                    # Récupérer le nom depuis l'état
                    display_name = state.split(":", 1)[1]
                    
                    # Valider l'email ou permettre de passer
                    paypal_email = None
                    text_lower = text.lower().strip()
                    if text_lower not in ['passer', 'skip', 'non', 'no', 'pass', 'rien', 'vide']:
                        # Validation simple de l'email
                        if '@' in text and '.' in text.split('@')[1] and len(text.strip()) > 5:
                            paypal_email = text.strip()
                        else:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text="❌ **Email invalide**\n\n" +
                                     "Veuillez entrer un email valide ou tapez 'passer' pour ignorer.\n" +
                                     "📝 Email PayPal :"
                            )
                            return
                    
                    # Créer/mettre à jour l'utilisateur avec les nouvelles informations
                    logger.info(f"🔄 Tentative sauvegarde profil: user={user.id}, nom='{display_name}', email='{paypal_email}'")
                    
                    # S'assurer que l'utilisateur existe en base
                    db_user = db.create_or_get_user(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name
                    )
                    
                    # Mettre à jour le profil
                    success = db.update_user_profile(
                        telegram_id=user.id,
                        display_name=display_name,
                        paypal_email=paypal_email
                    )
                    
                    logger.info(f"📊 Résultat sauvegarde: success={success}")
                    if success:
                        # Nettoyer l'état
                        del user_states[user.id]
                        logger.info(f"✅ État utilisateur nettoyé pour {user.id}")
                        
                        # Message de confirmation et redirection vers le profil
                        text_response = "✅ **Profil configuré !**\n\n"
                        text_response += f"🏷️ **Nom:** {display_name}\n"
                        if paypal_email:
                            text_response += f"📧 **Email PayPal:** {paypal_email}\n"
                        else:
                            text_response += f"📧 **Email PayPal:** Non renseigné\n"
                        text_response += f"\n🎮 **Votre profil est maintenant prêt !**\n"
                        text_response += f"💰 Utilisez /payment pour participer au concours."
                        
                        await bot.send_message(
                            chat_id=update.message.chat_id,
                            text=text_response,
                            
                        )
                        
                        # Afficher le profil complet
                        await handle_profile_command(bot, update.message)
                    else:
                        await bot.send_message(
                            chat_id=update.message.chat_id,
                            text="❌ Erreur lors de la sauvegarde. Réessayez avec /profile"
                        )
                    return
                
                elif state == "edit_name":
                    # Modification du nom
                    if text and len(text.strip()) >= 2 and len(text.strip()) <= 30:
                        success = db.update_user_profile(user.id, display_name=text.strip())
                        del user_states[user.id]
                        
                        if success:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text=f"✅ **Nom modifié !**\n\nVotre nouveau nom : {text.strip()}"
                            )
                            # Revenir au profil
                            await handle_profile_command(bot, update.message)
                        else:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text="❌ Erreur lors de la modification."
                            )
                    else:
                        await bot.send_message(
                            chat_id=update.message.chat_id,
                            text="❌ **Nom invalide**\n\nLe nom doit contenir entre 2 et 30 caractères.\n📝 Nouveau nom :"
                        )
                    return
                
                elif state == "edit_email":
                    # Modification de l'email
                    paypal_email = None
                    if text.lower().strip() not in ['supprimer', 'delete', 'remove']:
                        if '@' in text and '.' in text.split('@')[1]:
                            paypal_email = text.strip()
                        else:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text="❌ **Email invalide**\n\nVeuillez entrer un email valide ou tapez 'supprimer' pour l'effacer.\n📧 Email PayPal :"
                            )
                            return
                    
                    success = db.update_user_profile(user.id, paypal_email=paypal_email)
                    del user_states[user.id]
                    
                    if success:
                        if paypal_email:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text=f"✅ **Email modifié !**\n\nNouveau email : {paypal_email}"
                            )
                        else:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text="✅ **Email supprimé !**"
                            )
                        # Revenir au profil
                        await handle_profile_command(bot, update.message)
                    else:
                        await bot.send_message(
                            chat_id=update.message.chat_id,
                            text="❌ Erreur lors de la modification."
                        )
                    return
            
            # Commandes normales
            if text == '/start':
                await handle_start_command(bot, update.message)
            elif text == '/restore_admin' and user.id == ORGANIZER_CHAT_ID:
                # Commande d'urgence pour restaurer l'admin
                if user.id in user_states:
                    del user_states[user.id]
                
                db.update_user_profile(
                    telegram_id=user.id,
                    display_name="Nox (Admin)",
                    paypal_email="admin@dinochallenge.com"
                )
                
                db.record_payment(
                    telegram_id=user.id,
                    amount=Decimal('11.00'),
                    payment_type='admin_restore'
                )
                
                await bot.send_message(
                    chat_id=update.message.chat_id,
                    text="🚨 **PROFIL ADMIN RESTAURÉ !**\n\n✅ Accès rétabli\n✅ Profil configuré\n✅ État nettoyé"
                )
                return
            elif text == '/payment':
                await handle_payment_command(bot, update.message)
            elif text == '/leaderboard':
                await handle_leaderboard_command(bot, update.message)
            elif text == '/profile':
                await handle_profile_command(bot, update.message)
            elif text == '/setup':
                await force_user_setup(bot, update.message)
            elif text == '/cancel_subscription':
                await handle_cancel_subscription_command(bot, update.message)
            elif text == '/help':
                await handle_help_command(bot, update.message)
            elif text == '/support':
                await handle_support_command(bot, update.message)
            elif text == '/demo':
                await handle_demo_command(bot, update.message)
            elif text == '/restore_admin':
                # COMMANDE ADMIN URGENCE - Restaurer le profil admin
                if user.id == ORGANIZER_CHAT_ID:
                    await handle_restore_admin_command(bot, update.message)
                else:
                    await bot.send_message(
                        chat_id=update.message.chat_id,
                        text="❌ Commande réservée à l'administrateur."
                    )
            elif text == '/clean_payments':
                # COMMANDE ADMIN - Nettoyer les paiements de test
                if user.id == ORGANIZER_CHAT_ID:
                    deleted_count = db.clean_test_payments()
                    await bot.send_message(
                        chat_id=update.message.chat_id,
                        text=f"🧹 **Nettoyage effectué !**\n\n✅ {deleted_count} paiements de test supprimés\n💰 Les prix sont maintenant corrects"
                    )
                else:
                    await bot.send_message(
                        chat_id=update.message.chat_id,
                        text="❌ Commande réservée à l'administrateur."
                    )
            # Gestion des boutons persistants (texte sans /)
            elif text in ["🎮 Jouer", "Jouer", "JOUER"]:
                # Fonction de jeu spécifique (pas /start)
                await handle_play_game(bot, update.message)
            elif text in ["📊 Classement", "🏆 Classement", "Classement", "CLASSEMENT"]:
                await handle_leaderboard_command(bot, update.message)
            elif text in ["👤 Profil", "Profil", "PROFIL"]:
                await handle_profile_command(bot, update.message)
            elif text in ["❓ Aide et règles", "aide/règle", "Aide", "AIDE", "Règles", "REGLES"]:
                await handle_help_command(bot, update.message)
            else:
                # Message non reconnu
                await bot.send_message(
                    chat_id=update.message.chat_id,
                    text="🤖 Commande non reconnue. Utilisez /start pour voir le menu."
                )
                
        elif update.callback_query:
            # Callbacks des boutons
            await handle_callback_query(bot, update.callback_query)
            
    except Exception as e:
        logger.error(f"❌ Erreur traitement update: {e}")

async def start_user_setup(bot, message):
    """Commencer la configuration d'un nouvel utilisateur"""
    user = message.from_user
    user_states[user.id] = "waiting_for_name"
    
    text = f"👋 **Bienvenue {user.first_name} !**\n\n"
    text += f"🏷️ **Configuration de votre profil**\n\n"
    text += f"Pour participer au Dino Challenge, nous avons besoin de quelques informations :\n\n"
    text += f"**Étape 1/2 : Nom d'affichage**\n"
    text += f"Ce nom apparaîtra dans le classement.\n\n"
    text += f"📝 Envoyez-moi le nom que vous voulez utiliser :"
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text
    )

async def force_user_setup(bot, message):
    """Forcer la reconfiguration d'un utilisateur (commande /setup)"""
    user = message.from_user
    user_states[user.id] = "waiting_for_name"
    
    text = f"🔧 **Reconfiguration de votre profil**\n\n"
    text += f"👋 Salut {user.first_name} !\n\n"
    text += f"Vous allez pouvoir modifier vos informations :\n\n"
    text += f"**Étape 1/2 : Nom d'affichage**\n"
    text += f"Ce nom apparaîtra dans le classement.\n\n"
    text += f"📝 Envoyez-moi le nouveau nom que vous voulez utiliser :"
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text
    )

async def handle_callback_query(bot, callback_query):
    """Gérer les callbacks des boutons"""
    try:
        await callback_query.answer()
        
        data = callback_query.data
        user = callback_query.from_user
        chat_id = callback_query.message.chat_id
        
        if data == "cancel_payment":
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=callback_query.message.message_id,
                text="❌ **Paiement annulé.**",
                
            )
            return
        
        elif data.startswith("pay_once_"):
            telegram_id = int(data.replace("pay_once_", ""))
            payment_url = f"https://dinochallenge-bot.onrender.com/create-payment"
            
            text = f"💳 **Paiement Unique - {MONTHLY_PRICE_CHF} CHF**\n\n"
            text += f"🔗 **Cliquez ici pour payer :**\n"
            text += f"[💰 Payer avec PayPal]({payment_url}?telegram_id={telegram_id})\n\n"
            text += f"📱 Vous serez redirigé vers PayPal pour finaliser le paiement.\n"
            text += f"✅ Une fois payé, votre accès sera activé automatiquement !"
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=callback_query.message.message_id,
                text=text,
                
            )
        
        elif data.startswith("pay_subscription_"):
            telegram_id = int(data.replace("pay_subscription_", ""))
            subscription_url = f"https://dinochallenge-bot.onrender.com/create-subscription"
            
            text = f"🔄 **Abonnement Mensuel - {MONTHLY_PRICE_CHF} CHF/mois**\n\n"
            text += f"🔗 **Cliquez ici pour vous abonner :**\n"
            text += f"[🔄 S'abonner avec PayPal]({subscription_url}?telegram_id={telegram_id})\n\n"
            text += f"📱 Vous serez redirigé vers PayPal pour configurer l'abonnement.\n"
            text += f"✅ Accès permanent avec renouvellement automatique !\n"
            text += f"❌ Annulable à tout moment avec /cancel_subscription"
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=callback_query.message.message_id,
                text=text
            )

        elif data == "profile":
            # Rediriger vers la fonction handle_profile_command
            await handle_profile_command(bot, callback_query.message)

        elif data == "leaderboard":
            # Afficher le classement avec gains en temps réel
            current_month = datetime.now().strftime('%Y-%m')
            leaderboard = db.get_leaderboard(current_month, 10)
            
            if not leaderboard:
                text = "🏆 Aucun score enregistré ce mois-ci."
            else:
                # Calculer les prix du mois
                prize_info = db.calculate_monthly_prizes(current_month)
                
                text = f"🏆 **CLASSEMENT - {datetime.now().strftime('%B %Y')}**\n\n"
                text += f"💰 **Cagnotte : {prize_info['total_amount']:.2f} CHF** ({prize_info['total_players']} joueurs)\n"
                text += f"🥇 1er : {prize_info['prizes']['first']:.2f} CHF\n"
                text += f"🥈 2e : {prize_info['prizes']['second']:.2f} CHF\n"
                text += f"🥉 3e : {prize_info['prizes']['third']:.2f} CHF\n\n"
                
                medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
                
                for i, player in enumerate(leaderboard):
                    medal = medals[i] if i < len(medals) else '🏅'
                    display_name = player['display_name']
                    score = player['best_score']
                    games = player['total_games']
                    
                    # Calculer le gain pour cette position
                    if i == 0:
                        prize = prize_info['prizes']['first']
                    elif i == 1:
                        prize = prize_info['prizes']['second']
                    elif i == 2:
                        prize = prize_info['prizes']['third']
                    else:
                        prize = 0
                    
                    text += f"{medal} **#{i+1} - {display_name}**\n"
                    text += f"   📊 {score:,} pts ({games} parties)"
                    
                    if prize > 0:
                        text += f" 💰 {prize:.2f} CHF"
                    
                    text += f"\n\n"
                
                text += f"🎮 Jouez ici : {GAME_URL}\n"
                text += f"💡 Les gains sont automatiquement recalculés à chaque nouveau paiement !"
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=callback_query.message.message_id,
                text=text,
                
            )

        elif data == "payment":
            await handle_payment_command(bot, callback_query.message)
        
        elif data == "help":
            # Afficher l'aide complète
            await handle_help_command(bot, callback_query.message)
        
        elif data == "support":
            # Afficher le support technique
            await handle_support_command(bot, callback_query.message)
        
        elif data == "setup_profile":
            # Démarrer la configuration pour un nouvel utilisateur
            await start_user_setup(bot, callback_query.message)
        
        elif data == "change_name" or data == "edit_name":
            user_states[user.id] = "edit_name"
            await bot.send_message(
                chat_id=chat_id,
                text="✏️ **Modifier votre nom d'affichage**\n\n" +
                     "📝 Envoyez-moi votre nouveau nom :",
                
            )
        
        elif data == "edit_email":
            user_states[user.id] = "edit_email"
            await bot.send_message(
                chat_id=chat_id,
                text="📧 **Modifier votre email PayPal**\n\n" +
                     "📝 Envoyez votre nouvel email PayPal ou tapez 'supprimer' pour l'effacer :",
                
            )
        
        elif data == "delete_profile":
            # Demander confirmation
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [InlineKeyboardButton("🗑️ Confirmer la suppression", callback_data="confirm_delete")],
                [InlineKeyboardButton("❌ Annuler", callback_data="cancel_delete")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=callback_query.message.message_id,
                text="⚠️ **Suppression du profil**\n\n" +
                     "Êtes-vous sûr de vouloir supprimer votre profil ?\n" +
                     "Cette action est irréversible et supprimera :\n\n" +
                     "• Votre nom d'affichage\n" +
                     "• Votre email PayPal\n" +
                     "• Tous vos scores\n" +
                     "• Vos paiements\n\n" +
                     "⚠️ **Cette action ne peut pas être annulée !**",
                reply_markup=reply_markup
            )
        
        elif data == "confirm_delete":
            # Supprimer le profil
            success = db.delete_user_profile(user.id)
            if success:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=callback_query.message.message_id,
                    text="✅ **Profil supprimé**\n\n" +
                         "Votre profil a été entièrement supprimé.\n" +
                         "Utilisez /start pour créer un nouveau profil.",
                    
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=callback_query.message.message_id,
                    text="❌ **Erreur**\n\nImpossible de supprimer le profil. Contactez l'support.",
                    
                )
        
        elif data == "cancel_delete":
            # Retourner au profil
            await handle_profile_command(bot, callback_query.message)
            
    except Exception as e:
        logger.error(f"❌ Erreur callback query: {e}")
        await callback_query.answer("❌ Erreur lors du traitement")

async def handle_play_game(bot, message):
    """Gérer le bouton Jouer (mode jeu spécifique)"""
    user = message.from_user
    
    # Créer ou récupérer l'utilisateur
    db_user = db.create_or_get_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Vérifier l'accès premium
    has_access = db.check_user_access(user.id)
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    if has_access:
        # Utilisateur premium - accès direct au jeu
        text = f"""🎮 **DINO CHALLENGE - MODE COMPÉTITION**

👋 Salut {user.first_name} !

✅ **Statut :** Premium activé
🏆 **Mode :** Compétition (scores comptabilisés)

🎯 **Votre mission :**
• Évitez les obstacles en sautant
• Réalisez le meilleur score possible
• Montez dans le classement mensuel
• Gagnez des prix en CHF !

🚀 Cliquez sur le bouton ci-dessous pour jouer :"""

        keyboard = [
            [InlineKeyboardButton("🎮 JOUER MAINTENANT", url=f"{GAME_URL}?telegram_id={user.id}&mode=competition")],
            [
                InlineKeyboardButton("🏆 Voir le classement", callback_data="leaderboard"),
                InlineKeyboardButton("👤 Mon profil", callback_data="profile")
            ]
        ]
    else:
        # Utilisateur non-premium - proposition de paiement
        text = f"""🎮 **DINO CHALLENGE**

👋 Salut {user.first_name} !

⚠️ **Accès requis pour le mode compétition**

💰 **Deux options de participation :**
• 💳 **Paiement unique** : {MONTHLY_PRICE_CHF} CHF pour le mois en cours
• 🔄 **Abonnement mensuel** : {MONTHLY_PRICE_CHF} CHF/mois automatique

✅ **Avantages :**
• Scores comptabilisés dans le classement
• Éligibilité aux prix mensuels
• Accès illimité tout le mois

🆓 **En attendant :** Vous pouvez essayer le mode démo

"""

        keyboard = [
            [InlineKeyboardButton("🏆 JOUER EN MODE CLASSÉ", url=f"{GAME_URL}?telegram_id={message.from_user.id}&mode=competition")],
            [InlineKeyboardButton("🆓 Mode démo (gratuit)", url=f"{GAME_URL}?mode=demo")],
            [
                InlineKeyboardButton("🏆 Voir le classement", callback_data="leaderboard"),
                InlineKeyboardButton("❓ En savoir plus", callback_data="help")
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )

async def handle_play_command(bot, message):
    """Gérer la commande de jeu (bouton Jouer)"""
    user = message.from_user
    
    # Créer ou récupérer l'utilisateur
    db_user = db.create_or_get_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Vérifier l'accès
    has_access = db.check_user_access(user.id)
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    if has_access:
        text = f"""🎮 **Prêt à jouer au Dino Challenge !**

👋 Salut {user.first_name} !

✅ Vous avez accès au mode compétition ce mois.

🏆 **Objectif :** Faites le meilleur score possible !
🎯 **Règles :** Évitez les obstacles, gagnez des points
💰 **Prix :** Top 3 du mois remportent la cagnotte

🚀 Cliquez sur le bouton ci-dessous pour jouer :"""

        keyboard = [
            [InlineKeyboardButton("🎮 JOUER EN MODE COMPÉTITION", url=f"{GAME_URL}?telegram_id={user.id}&mode=competition")],
            [
                InlineKeyboardButton("🏆 Voir le classement", callback_data="leaderboard"),
                InlineKeyboardButton("👤 Mon profil", callback_data="profile")
            ]
        ]
    else:
        text = f"""🎮 **Rejoignez le Dino Challenge !**

👋 Salut {user.first_name} !

⚠️ Pour jouer en mode compétition et gagner des prix, vous devez d'abord participer au concours ({MONTHLY_PRICE_CHF} CHF).

🆓 **En attendant :** Vous pouvez essayer le jeu en mode démo
💰 **Pour concourir :** Payez votre participation mensuelle

"""

        keyboard = [
            [InlineKeyboardButton(f"💰 PARTICIPER ({MONTHLY_PRICE_CHF} CHF)", callback_data="payment")],
            [InlineKeyboardButton("🆓 Essayer en mode démo", url=f"{GAME_URL}?mode=demo")],
            [
                InlineKeyboardButton("🏆 Voir le classement", callback_data="leaderboard"),
                InlineKeyboardButton("❓ Aide et règles", callback_data="help")
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )

async def handle_start_command(bot, message):
    """Gérer la commande /start"""
    user = message.from_user
    
    # Créer ou récupérer l'utilisateur
    db_user = db.create_or_get_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Vérifier si l'utilisateur a besoin de configurer son profil
    # PROTECTION: Ne pas forcer la reconfiguration si l'utilisateur a déjà payé ou a des scores
    if not db_user.get('display_name'):
        # Vérifier si c'est vraiment un nouvel utilisateur
        has_access = db.check_user_access(user.id)
        user_scores = db.get_user_scores(user.id)
        
        # Si l'utilisateur a déjà payé ou a des scores, réparer le profil au lieu de forcer la reconfiguration
        if has_access or (user_scores and len(user_scores) > 0):
            # RÉPARATION AUTOMATIQUE du profil existant
            logger.warning(f"🔧 Réparation profil utilisateur existant {user.id}")
            fallback_name = user.first_name or user.username or f"Joueur_{user.id}"
            db.update_user_profile(user.id, display_name=fallback_name)
            logger.info(f"✅ Profil réparé pour {user.id}: nom='{fallback_name}'")
        else:
            # Nouvel utilisateur réel - démarrer la configuration
            await start_user_setup(bot, message)
            return
    
    # Vérifier l'accès
    has_access = db.check_user_access(user.id)
    
    text = f"""🦕 **Bienvenue dans le Dino Challenge !**

👋 Salut {user.first_name} !

🎮 **Le jeu Chrome Dino avec des vrais prix !**
🏆 Concours mensuel avec redistribution des gains

💰 **Participation : {MONTHLY_PRICE_CHF} CHF**
• Paiement unique pour le mois en cours
• OU abonnement mensuel automatique

🥇 **Prix mensuels distribués au top 3 :**
• 1er place : 40% de la cagnotte
• 2e place : 15% de la cagnotte  
• 3e place : 5% de la cagnotte
(40% restants pour les frais d'organisation)

📋 **Commandes principales :**
/payment - 💰 Participer au concours
/leaderboard - 🏆 Voir le classement
/profile - 👤 Mon profil
/setup - 🔧 Reconfigurer mon profil
/help - ❓ Aide complète

"""
    
    # Créer les boutons
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    if has_access:
        text += f"✅ **Vous avez accès ce mois !**\n"
        keyboard = [
            [
                InlineKeyboardButton("🎮 JOUER (Mode Compétition)", url=f"{GAME_URL}?telegram_id={user.id}&mode=competition"),
                InlineKeyboardButton("🆓 Démo Gratuite", url=f"{GAME_URL}?mode=demo")
            ],
            [
                InlineKeyboardButton("👤 Mon Profil", callback_data="profile"),
                InlineKeyboardButton("🏆 Classement", callback_data="leaderboard")
            ]
        ]
    else:
        text += f"⚠️ **Configurez votre profil puis payez pour participer**\n"
        keyboard = [
            [
                InlineKeyboardButton("👤 Mon Profil", callback_data="profile"),
                InlineKeyboardButton("💰 Participer ({MONTHLY_PRICE_CHF} CHF)", callback_data="payment")
            ],
            [
                InlineKeyboardButton("� Démo Gratuite", url=f"{GAME_URL}?mode=demo"),
                InlineKeyboardButton("🏆 Classement", callback_data="leaderboard")
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Ajouter les boutons keyboard persistants (sous la barre d'écriture)
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    
    persistent_keyboard = [
        [KeyboardButton("🎮 Jouer"), KeyboardButton("📊 Classement")],
        [KeyboardButton("👤 Profil"), KeyboardButton("❓ Aide et règles")]
    ]
    
    persistent_reply_markup = ReplyKeyboardMarkup(
        persistent_keyboard, 
        resize_keyboard=True, 
        one_time_keyboard=False
    )
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )
    
    # Envoyer un message séparé avec les boutons persistants
    await bot.send_message(
        chat_id=message.chat_id,
        text="🎯 **Menu rapide :**",
        reply_markup=persistent_reply_markup
    )

async def handle_payment_command(bot, message):
    """Gérer la commande /payment"""
    user = message.from_user
    
    # Vérifier si l'utilisateur a déjà payé ce mois
    has_access = db.check_user_access(user.id)
    
    if has_access:
        text = f"✅ **Vous avez déjà accès ce mois !**\n\n"
        text += f"🎮 Jouez ici : {GAME_URL}\n"
        text += f"🏆 Consultez le classement avec /leaderboard"
        
        await bot.send_message(
            chat_id=message.chat_id,
            text=text,
            
        )
        return
    
    # Proposer les options de paiement
    text = f"💰 **PARTICIPER AU DINO CHALLENGE**\n\n"
    text += f"🎯 **Choisissez votre option de paiement :**\n\n"
    text += f"**💳 Paiement Unique ({MONTHLY_PRICE_CHF} CHF)**\n"
    text += f"• Accès pour le mois en cours uniquement\n"
    text += f"• À renouveler chaque mois manuellement\n\n"
    text += f"**🔄 Abonnement Mensuel ({MONTHLY_PRICE_CHF} CHF/mois)**\n"
    text += f"• Accès permanent avec renouvellement automatique\n"
    text += f"• Annulable à tout moment\n"
    text += f"• Plus pratique, jamais d'interruption !\n\n"
    text += f"🏆 **Prix mensuels distribués au top 3 !**"
    
    # Créer les boutons inline manuellement
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [
        [InlineKeyboardButton(f"💳 Paiement Unique - {MONTHLY_PRICE_CHF} CHF", callback_data=f"pay_once_{user.id}")],
        [InlineKeyboardButton(f"🔄 Abonnement Mensuel - {MONTHLY_PRICE_CHF} CHF/mois", callback_data=f"pay_subscription_{user.id}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_payment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )

async def handle_leaderboard_command(bot, message):
    """Gérer la commande /leaderboard avec calcul des gains en temps réel"""
    try:
        current_month = datetime.now().strftime('%Y-%m')
        leaderboard = db.get_leaderboard(current_month, 10)
        
        if not leaderboard:
            await bot.send_message(
                chat_id=message.chat_id,
                text="🏆 Aucun score enregistré ce mois-ci."
            )
            return
        
        # Calculer les prix du mois avec la vraie logique
        prize_info = db.calculate_monthly_prizes(current_month)
        
        text = f"🏆 Classement {datetime.now().strftime('%B %Y')}\n\n"
        text += f"💰 Cagnotte totale : {prize_info['total_amount']:.2f} CHF\n"
        text += f"⏰ Fin du concours : Dans {31 - datetime.now().day} jour(s)\n\n"
        text += f"🏅 Récompenses :\n"
        text += f"🥇 1er place : {prize_info['prizes']['first']:.2f} CHF (40%)\n"
        text += f"🥈 2e place : {prize_info['prizes']['second']:.2f} CHF (15%)\n"
        text += f"🥉 3e place : {prize_info['prizes']['third']:.2f} CHF (5%)\n\n"
        text += f"📊 Top 10 :\n"
        
        for i, player in enumerate(leaderboard):
            display_name = player['display_name']
            score = player['best_score']
            
            text += f"{i+1}. {display_name} - {score} pts"
            
            # Marquer l'utilisateur actuel
            if player.get('telegram_id') == message.from_user.id:
                text += " ← VOUS"
            
            text += f"\n"
        
        # Position de l'utilisateur
        user_rank = None
        for i, player in enumerate(leaderboard):
            if player.get('telegram_id') == message.from_user.id:
                user_rank = i + 1
                break
        
        if user_rank:
            text += f"\n👤 Votre position : #{user_rank}\n"
            user_score = next((p['best_score'] for p in leaderboard if p.get('telegram_id') == message.from_user.id), 0)
            text += f"🏅 Votre meilleur score : {user_score} pts\n"
        else:
            text += f"\n👤 Votre position : Non classé\n"
            text += f"💡 Jouez une partie pour apparaître dans le classement !\n"
        
        # Statistiques supplémentaires  
        total_players = len(leaderboard)
        text += f"\n📈 Statistiques :\n"
        text += f"• Joueurs participants : {total_players}\n"
        text += f"• Votre rang : #{user_rank if user_rank else 'N/A'}\n"
        
        if total_players > 0:
            avg_score = sum(p['best_score'] for p in leaderboard) / len(leaderboard)
            text += f"• Score moyen : {avg_score:.1f} pts"
        
        await bot.send_message(
            chat_id=message.chat_id,
            text=text
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur affichage classement: {e}")
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ Erreur lors de la récupération du classement."
        )
async def handle_profile_command(bot, message):
    """Gérer la commande /profile avec toutes les fonctionnalités"""
    user = message.from_user
    db_user = db.get_user_profile(user.id)
    
    if not db_user:
        # Nouvel utilisateur - commencer la configuration
        await start_user_setup(bot, message)
        return
    
    # Vérifier si le profil est complet
    # PROTECTION: Ne pas forcer la reconfiguration si l'utilisateur a déjà payé ou a des scores
    if not db_user.get('display_name'):
        # Vérifier si c'est vraiment un nouvel utilisateur
        has_access = db.check_user_access(user.id)
        user_scores = db.get_user_scores(user.id)
        
        # Si l'utilisateur a déjà payé ou a des scores, réparer le profil au lieu de forcer la reconfiguration
        if has_access or (user_scores and len(user_scores) > 0):
            # RÉPARATION AUTOMATIQUE du profil existant
            logger.warning(f"🔧 Réparation profil utilisateur existant dans /profile {user.id}")
            fallback_name = user.first_name or user.username or f"Joueur_{user.id}"
            db.update_user_profile(user.id, display_name=fallback_name)
            logger.info(f"✅ Profil réparé dans /profile pour {user.id}: nom='{fallback_name}'")
            # Continuer avec le profil réparé
            db_user = db.get_user_profile(user.id)  # Recharger les données
        else:
            # Nouvel utilisateur réel - commencer la configuration
            await start_user_setup(bot, message)
            return
    
    # Récupérer les informations du profil
    has_access = db.check_user_access(user.id)
    position_info = db.get_user_position_and_prize(user.id)
    
    display_name = db_user.get('display_name') or user.first_name or 'Anonyme'
    paypal_email = db_user.get('paypal_email') or 'Non renseigné'
    
    # Gérer la date d'inscription (peut être datetime ou string)
    registration_date = db_user.get('registration_date')
    if registration_date:
        if hasattr(registration_date, 'strftime'):
            # Si c'est un objet datetime
            registration_str = registration_date.strftime('%Y-%m-%d')
        else:
            # Si c'est déjà une string
            registration_str = str(registration_date)[:10]
    else:
        registration_str = 'Inconnue'
    
    text = f"👤 **PROFIL - {display_name}**\n\n"
    text += f"🏷️ **Nom d'affichage:** {display_name}\n"
    text += f"📧 **Email PayPal:** {paypal_email}\n"
    text += f"🆔 **ID Telegram:** {user.id}\n"
    text += f"📅 **Inscription:** {registration_str}\n\n"
    
    if has_access:
        text += f"✅ **Statut:** Accès actif ce mois\n\n"
        
        if position_info['position']:
            text += f"🏆 **Position:** #{position_info['position']}/{position_info['total_players']}\n"
            if position_info['prize'] > 0:
                text += f"💰 **Gain potentiel:** {position_info['prize']:.2f} CHF\n"
        else:
            text += f"🎮 **Jouez pour être classé !**\n"
    else:
        text += f"❌ **Statut:** Pas d'accès ce mois\n"
        text += f"💡 Payez votre participation pour concourir\n"
    
    # Créer les boutons du profil
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = []
    
    # Bouton jouer ou payer
    if has_access:
        keyboard.append([InlineKeyboardButton("🎮 Jouer au Dino Challenge", url=f"{GAME_URL}?telegram_id={user.id}&mode=competition")])
    else:
        keyboard.append([InlineKeyboardButton(f"💰 Payer ma participation ({MONTHLY_PRICE_CHF} CHF)", callback_data="payment")])
    
    # Boutons de gestion du profil
    keyboard.append([
        InlineKeyboardButton("✏️ Modifier mon nom", callback_data="edit_name"),
        InlineKeyboardButton("📧 Modifier email PayPal", callback_data="edit_email")
    ])
    
    keyboard.append([InlineKeyboardButton("🗑️ Supprimer mon profil", callback_data="delete_profile")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )

async def handle_cancel_subscription_command(bot, message):
    """Gérer la commande /cancel_subscription"""
    text = f"🔄 **Gestion de l'abonnement**\n\n"
    text += f"Pour annuler votre abonnement PayPal :\n\n"
    text += f"1. Connectez-vous à votre compte PayPal\n"
    text += f"2. Allez dans 'Paiements' → 'Abonnements'\n"
    text += f"3. Trouvez 'Dino Challenge'\n"
    text += f"4. Cliquez sur 'Annuler l'abonnement'\n\n"
    text += f"📞 **Besoin d'aide ?** Contactez l'organisateur.\n"
    text += f"⚠️ L'accès reste valide jusqu'à la fin de la période payée."
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        
    )

async def handle_help_command(bot, message):
    """Gérer la commande /help"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    text = f"""❓ **AIDE & RÈGLES - DINO CHALLENGE**

🦕 **Bienvenue dans le Dino Challenge !**
Le concours mensuel du célèbre jeu Chrome Dino Runner !

🎮 **Comment jouer :**
1. Payez {MONTHLY_PRICE_CHF} CHF avec /payment pour participer
2. Recevez le lien du jeu sécurisé
3. Utilisez ESPACE ou FLÈCHE HAUT pour sauter
4. Évitez les obstacles le plus longtemps possible
5. Vos scores sont automatiquement enregistrés depuis le jeu

🚫 **NOUVEAU : Scores automatiques uniquement !**
• Plus de soumission manuelle (anti-triche)
• Maximum 5 parties par jour par joueur
• Scores validés automatiquement depuis le jeu

💰 **Options de participation :**
• **Paiement unique :** {MONTHLY_PRICE_CHF} CHF - Accès pour le mois en cours
• **Abonnement :** {MONTHLY_PRICE_CHF} CHF/mois - Accès permanent automatique

🏆 **Prix du concours mensuel :**
Les gains sont calculés sur la cagnotte totale :
• 🥇 **1ère place :** 40% de la cagnotte
• 🥈 **2e place :** 15% de la cagnotte  
• 🥉 **3e place :** 5% de la cagnotte
• ⚙️ Organisation : 40% (frais techniques et gestion)

💸 **Paiement des gains :**
• Versement automatique chaque 1er du mois
• Transfert direct sur votre compte PayPal
• Notification personnalisée aux gagnants

📋 **Commandes disponibles :**
/start - Menu principal avec boutons
/payment - Participer au concours
/leaderboard - Classement temps réel
/profile - Gérer mon profil et PayPal
/support - Support technique direct
/cancel_subscription - Annuler l'abonnement
/help - Cette aide complète

🔒 **Sécurité & Fair-Play :**
• Système anti-triche intégré
• Validation des scores automatique
• Limite de 5 parties/jour/joueur
• Accès premium vérifié pour chaque partie

📅 **Calendrier mensuel :**
• Concours du 1er au dernier jour du mois
• Notification des gagnants le 1er du mois suivant
• Reset automatique du classement
• Nouveau concours commence immédiatement

🆘 **Support technique :**
👤 **@Lilith66store** (Organisateur officiel)
📧 Disponible 7j/7 pour toute question

⚡ **Système automatisé :**
• Tout est géré automatiquement
• Pas d'intervention manuelle nécessaire
• Transparence totale des résultats
• Paiements rapides et sécurisés

🎯 **Astuce :** Configurez votre email PayPal dans /profile pour recevoir vos gains automatiquement !"""

    # Vérifier l'accès utilisateur pour choisir le bon bouton de jeu
    has_access = db.check_user_access(message.from_user.id)
    
    # Ajouter des boutons pour actions rapides
    if has_access:
        # Utilisateur avec accès premium - bouton vers mode compétition
        keyboard = [
            [
                InlineKeyboardButton("🎮 JOUER MAINTENANT (Mode Compétition)", url=f"{GAME_URL}?telegram_id={message.from_user.id}&mode=competition"),
                InlineKeyboardButton("🆓 Mode Démo", url=f"{GAME_URL}?mode=demo")
            ],
            [
                InlineKeyboardButton("💰 Participer", callback_data="payment"),
                InlineKeyboardButton("🏆 Classement", callback_data="leaderboard")
            ],
            [
                InlineKeyboardButton("👤 Mon profil", callback_data="profile"),
                InlineKeyboardButton("🆘 Support", callback_data="support")
            ],
            [
                InlineKeyboardButton("� Retour au menu", callback_data="start")
            ]
        ]
    else:
        # Utilisateur sans accès - bouton vers démo + incitation à payer
        keyboard = [
            [
                InlineKeyboardButton("🆓 Essayer en Mode Démo", url=f"{GAME_URL}?mode=demo"),
                InlineKeyboardButton("💰 Débloquer Mode Compétition", callback_data="payment")
            ],
            [
                InlineKeyboardButton("🏆 Classement", callback_data="leaderboard"),
                InlineKeyboardButton("👤 Mon profil", callback_data="profile")
            ],
            [
                InlineKeyboardButton("🆘 Support", callback_data="support")
            ],
            [
                InlineKeyboardButton("🏠 Retour au menu", callback_data="start")
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )

async def handle_demo_command(bot, message):
    """Gérer la commande /demo"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    text = """🎮 **MODE DÉMO - DINO CHALLENGE**

🆓 **Jouez gratuitement au Chrome Dino Runner !**

🎯 **Mode Démo :**
• Accès gratuit et illimité
• Entraînez-vous autant que vous voulez
• Familiarisez-vous avec les commandes
• Aucun score n'est comptabilisé dans le concours

🏆 **Pour participer au concours :**
• Utilisez /payment pour débloquer le mode compétition
• Vos scores seront alors comptabilisés automatiquement
• Maximum 5 parties par jour en mode compétition
• Prix mensuels garantis !

🎮 **Commandes du jeu :**
• **ESPACE** ou **FLÈCHE HAUT** : Sauter
• **FLÈCHE BAS** : S'accroupir (éviter les oiseaux)

🚀 **Prêt à jouer en démo ?**
Cliquez sur le bouton ci-dessous pour commencer !"""

    keyboard = [
        [
            InlineKeyboardButton("🎮 JOUER EN MODE DÉMO", url=f"{GAME_URL}?mode=demo")
        ],
        [
            InlineKeyboardButton("💰 Débloquer Mode Compétition", callback_data="payment"),
            InlineKeyboardButton("🏆 Voir le Classement", callback_data="leaderboard")
        ],
        [
            InlineKeyboardButton("❓ Aide & Règles", callback_data="help"),
            InlineKeyboardButton("🏠 Menu Principal", callback_data="start")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )

async def handle_support_command(bot, message):
    """Gérer la commande /support"""
    user = message.from_user
    
    text = f"""🆘 **SUPPORT TECHNIQUE - DINO CHALLENGE**

👋 Salut {user.first_name} !

❓ **Vous rencontrez un problème ?**

• Paiement non reconnu
• Erreur technique du jeu  
• Score non comptabilisé
• Question sur les règles
• Autre problème

📞 **Contact direct :**
👤 **@Lilith66store** (Support officiel)

📧 **Comment nous contacter :**
1. Cliquez sur le bouton ci-dessous
2. Décrivez votre problème en détail
3. Joignez des captures d'écran si nécessaire

⏰ **Délai de réponse :** 24-48h maximum
"""

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = [
        [InlineKeyboardButton("📞 Contacter le Support", url="https://t.me/Lilith66store")],
        [InlineKeyboardButton("🏠 Retour au menu", callback_data="start")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        reply_markup=reply_markup
    )

# Suppression de handle_score_command - plus utilisé (scores automatiques depuis le jeu)

async def notify_monthly_winners():
    """Notification automatique des gagnants en fin de mois"""
    try:
        # Obtenir les gagnants du mois précédent
        winners = db.get_monthly_winners()
        
        if not winners:
            logger.info("📊 Aucun gagnant trouvé pour le mois précédent")
            return
        
        bot = setup_telegram_bot()
        if not bot:
            logger.error("❌ Impossible de configurer le bot pour les notifications")
            return
        
        month_name = datetime.now().replace(day=1) - timedelta(days=1)
        month_formatted = month_name.strftime('%B %Y')
        
        logger.info(f"🏆 Notification des {len(winners)} gagnants de {month_formatted}")
        
        for winner in winners:
            try:
                # Obtenir le profil PayPal
                profile = db.get_user_profile_with_paypal(winner['telegram_id'])
                
                # Préparer le message de félicitations
                if winner['position'] == 1:
                    emoji = "🥇"
                    position_text = "1ère place"
                elif winner['position'] == 2:
                    emoji = "🥈" 
                    position_text = "2e place"
                else:
                    emoji = "🥉"
                    position_text = "3e place"
                
                text = f"{emoji} **FÉLICITATIONS !**\n\n"
                text += f"🎉 Vous avez remporté la **{position_text}** du concours Dino Challenge de **{month_formatted}** !\n\n"
                text += f"📊 **Votre score :** {winner['score']:,} points\n"
                text += f"💰 **Votre gain :** {winner['prize']:.2f} CHF\n\n"
                
                if profile and profile.get('paypal_email'):
                    text += f"💳 **Paiement PayPal**\n"
                    text += f"📧 Envoyé à : {profile['paypal_email']}\n"
                    text += f"⏰ Délai : 2-3 jours ouvrables\n\n"
                    text += f"✅ Votre gain sera automatiquement transféré sur votre compte PayPal.\n"
                else:
                    text += f"⚠️ **Action requise :**\n"
                    text += f"Veuillez configurer votre email PayPal avec /profile pour recevoir votre gain.\n"
                    text += f"📞 Ou contactez le support : @Lilith66store\n\n"
                
                text += f"🎊 Merci d'avoir participé au Dino Challenge !\n"
                text += f"🆕 Le nouveau concours a déjà commencé - bonne chance !"
                
                # Envoyer la notification
                await bot.send_message(
                    chat_id=winner['telegram_id'],
                    text=text,
                    
                )
                
                logger.info(f"✅ Notification envoyée à {winner['display_name']} ({winner['position']}e place)")
                
                # Petite pause entre les notifications
                await asyncio.sleep(1)
                
            except Exception as notification_error:
                logger.error(f"❌ Erreur notification {winner['display_name']}: {notification_error}")
        
        logger.info(f"🎉 Toutes les notifications de fin de mois envoyées !")
        
    except Exception as e:
        logger.error(f"❌ Erreur notification gagnants: {e}")

async def check_monthly_reset():
    """Vérifier si c'est le 1er du mois pour reset et notifier"""
    now = datetime.now()
    
    # Vérifier si c'est le 1er du mois
    if now.day == 1:
        # Vérifier si le reset n'a pas déjà été fait aujourd'hui
        reset_flag_file = f"/tmp/dino_reset_{now.strftime('%Y-%m')}.flag"
        
        if not os.path.exists(reset_flag_file):
            logger.info("🔄 Début du processus de fin de mois...")
            
            # Notifier les gagnants du mois précédent
            await notify_monthly_winners()
            
            # Reset du classement (automatique via month_year)
            db.reset_monthly_leaderboard()
            
            # Créer le fichier flag pour éviter les doublons
            with open(reset_flag_file, 'w') as f:
                f.write(f"Reset effectué le {now.isoformat()}")
            
            logger.info("✅ Processus de fin de mois terminé")

async def notify_new_score(telegram_id: int, score: int):
    """Notifier l'utilisateur de son nouveau score"""
    try:
        bot = setup_telegram_bot()
        if not bot:
            return
        
        # Obtenir les informations du joueur
        position_info = db.get_user_position_and_prize(telegram_id)
        
        text = f"🎯 **Nouveau score enregistré !**\n\n"
        text += f"📊 **Score :** {score:,} points\n"
        
        if position_info['position']:
            text += f"🏆 **Position :** {position_info['position']}/{position_info['total_players']}\n"
            if position_info['prize'] > 0:
                text += f"💰 **Gain potentiel :** {position_info['prize']:.2f} CHF\n"
        
        text += f"\n🎮 Continuez à jouer pour améliorer votre score !"
        
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur notification score: {e}")

async def handle_message(bot, message):
    """Gérer les messages texte (pour la configuration du profil)"""
    user = message.from_user
    text = message.text
    
    # Gérer les états de configuration utilisateur
    if hasattr(message.from_user, 'id') and message.from_user.id in user_states:
        state = user_states[message.from_user.id]
        
        if state == "edit_name":
            # Mise à jour du nom d'affichage
            new_name = text.strip()[:50]  # Limiter à 50 caractères
            
            success = db.update_display_name(message.from_user.id, new_name)
            
            if success:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=f"✅ **Nom mis à jour !**\n\nVotre nouveau nom : **{new_name}**",
                    
                )
            else:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text="❌ Erreur lors de la mise à jour du nom.",
                    
                )
            
            # Supprimer l'état
            del user_states[message.from_user.id]
            
        elif state == "edit_paypal":
            # Mise à jour de l'email PayPal
            paypal_email = text.strip()
            
            # Validation basique de l'email
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, paypal_email):
                await bot.send_message(
                    chat_id=message.chat_id,
                    text="❌ **Email invalide**\n\nVeuillez entrer une adresse email valide.",
                    
                )
                return
            
            success = db.update_user_profile(message.from_user.id, paypal_email=paypal_email)
            
            if success:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=f"✅ **Email PayPal mis à jour !**\n\nEmail : **{paypal_email}**\n\nVous pourrez recevoir vos gains automatiquement.",
                    
                )
            else:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text="❌ Erreur lors de la mise à jour de l'email PayPal.",
                    
                )
            
            # Supprimer l'état
            del user_states[message.from_user.id]
    
    else:
        # Message générique pour les autres cas
        await bot.send_message(
            chat_id=message.chat_id,
            text="🤖 Utilisez /start pour voir le menu principal.",
            
        )

async def handle_restore_admin_command(bot, message):
    """Commande URGENCE pour restaurer le profil admin manuellement"""
    user = message.from_user
    
    # Double vérification sécurité - ADMIN SEULEMENT
    if user.id != ORGANIZER_CHAT_ID:
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ **Accès refusé** - Cette commande est réservée à l'administrateur.",
        )
        return
    
    try:
        # Nettoyer complètement l'état utilisateur
        if user.id in user_states:
            del user_states[user.id]
            logger.info(f"🧹 État admin nettoyé: {user.id}")
        
        # Forcer la recréation du profil admin
        db_user = db.create_or_get_user(
            telegram_id=user.id,
            username=user.username or "admin",
            first_name=user.first_name or "Admin"
        )
        
        # Restaurer le profil complet avec tous les accès
        success = db.update_user_profile(
            telegram_id=user.id,
            display_name="Nox (Admin)",
            paypal_email="admin@dinochallenge.com"
        )
        
        # Garantir l'accès permanent
        payment_success = db.record_payment(
            telegram_id=user.id,
            amount=Decimal('11.00'),
            payment_type='admin_emergency_restore'
        )
        
        if success and payment_success:
            # Confirmer la restauration complète
            await bot.send_message(
                chat_id=message.chat_id,
                text="🚨 **RESTAURATION ADMIN RÉUSSIE** 🚨\n\n" +
                     "✅ Profil admin restauré complètement\n" +
                     "✅ Accès permanent activé\n" +
                     "✅ État de configuration nettoyé\n\n" +
                     "🏷️ **Profil:** Nox (Admin)\n" +
                     "💳 **Statut:** Accès permanent\n" +
                     "📧 **Email:** admin@dinochallenge.com\n\n" +
                     "Vous pouvez maintenant utiliser toutes les fonctions du bot normalement."
            )
            logger.info(f"🚨 RESTAURATION ADMIN COMPLÈTE réussie pour {user.id}")
        else:
            await bot.send_message(
                chat_id=message.chat_id,
                text="❌ **ERREUR lors de la restauration admin**\n\n" +
                     "Contactez le support technique d'urgence."
            )
            logger.error(f"❌ ÉCHEC restauration admin pour {user.id}")
            
    except Exception as e:
        logger.error(f"❌ ERREUR CRITIQUE restauration admin: {e}")
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ **ERREUR CRITIQUE**\n\nÉchec de la restauration d'urgence."
        )

async def run_telegram_bot():
    """Exécuter le bot Telegram avec protection anti-conflit et verrouillage"""
    
    # PROTECTION ANTI-DOUBLON : Créer un fichier de verrouillage
    lock_file = None
    try:
        lock_file_path = os.path.join(tempfile.gettempdir(), 'dinochallenge_bot.lock')
        lock_file = open(lock_file_path, 'w')
        
        try:
            # Tentative de verrouillage exclusif (non-bloquant)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            logger.info("🔒 Verrou obtenu - Instance unique confirmée")
        except IOError:
            logger.error("🔥 ARRÊT : Une autre instance du bot tourne déjà !")
            logger.error("💡 Arrêtez l'autre instance avant de redémarrer")
            return
        
        bot = setup_telegram_bot()
        if bot:
            logger.info("🤖 Démarrage du bot Telegram...")
            
            # ÉTAPE 1: Nettoyer les anciennes mises à jour de TOUTES les instances
            try:
                logger.info("🧹 Nettoyage RADICAL des mises à jour...")
                
                # Étape 1: Supprimer les webhooks (au cas où)
                try:
                    await bot.delete_webhook(drop_pending_updates=True)
                    logger.info("✅ Webhooks supprimés")
                except Exception as webhook_error:
                    logger.warning(f"⚠️ Erreur suppression webhook: {webhook_error}")
                
                # Étape 2: Utiliser un offset très élevé pour ignorer toutes les anciennes mises à jour
                await bot.get_updates(offset=-1, timeout=1, limit=1)
                logger.info("✅ Toutes les anciennes mises à jour ignorées")
                
                # Étape 3: Attendre que toutes les autres connexions se ferment
                logger.info("⏳ Attente de fermeture des autres connexions...")
                await asyncio.sleep(15)  # Attendre plus longtemps pour être sûr
                
            except Exception as cleanup_error:
                logger.warning(f"⚠️ Erreur nettoyage (peut être normal): {cleanup_error}")
            
            # Configurer les commandes du bot (menu hamburger)
            from telegram import BotCommand
            commands = [
                BotCommand("start", "🏠 Menu principal"),
                BotCommand("payment", "💰 Participer au concours"),
                BotCommand("leaderboard", "🏆 Classement mensuel"),
                BotCommand("profile", "👤 Mon profil"),
                BotCommand("cancel_subscription", "❌ Annuler l'abonnement"),
                BotCommand("support", "🆘 Support technique"),
                BotCommand("help", "❓ Aide et règles"),
                BotCommand("demo", "🎮 Mode Démo"),
            ]
            
            await bot.set_my_commands(commands)
            logger.info("✅ Commandes du bot configurées")
            
            logger.info("🔄 Démarrage du polling avec verrouillage...")
            
            # Polling avec protection maximale contre les conflits
            offset = 0
            consecutive_409_errors = 0
            last_successful_update = datetime.now()
            
            while True:
                try:
                    # Vérifier que le verrou est toujours actif
                    if not lock_file or lock_file.closed:
                        logger.error("🔒 Verrou perdu - Arrêt du bot")
                        break
                    
                    # Récupérer les mises à jour avec timeout court
                    updates = await bot.get_updates(
                        offset=offset,
                        limit=100,
                        timeout=10  # Timeout plus court pour détecter les conflits rapidement
                    )
                    
                    # Reset du compteur d'erreurs 409 si succès
                    consecutive_409_errors = 0
                    last_successful_update = datetime.now()
                    
                    for update in updates:
                        offset = update.update_id + 1
                        # Traiter l'update manuellement
                        await process_update_manually(bot, update)
                    
                    # Vérification du reset mensuel (une fois par jour)
                    await check_monthly_reset()
                    
                    # Petite pause pour éviter la surcharge
                    if not updates:
                        await asyncio.sleep(2)
                        
                except Exception as poll_error:
                    error_message = str(poll_error)
                    
                    # Gestion spécifique des erreurs 409 (conflit)
                    if "409" in error_message or "Conflict" in error_message:
                        consecutive_409_errors += 1
                        logger.error(f"❌ Conflit 409 détecté (tentative {consecutive_409_errors}): {poll_error}")
                        
                        if consecutive_409_errors >= 2:  # Réduit à 2 tentatives
                            logger.error("🔥 ARRÊT IMMÉDIAT: Conflit persistant détecté!")
                            logger.error("💡 Autre instance toujours active - Arrêtez tout sur Render")
                            break
                        
                        # Attendre plus longtemps en cas de conflit
                        await asyncio.sleep(30)
                    else:
                        logger.error(f"❌ Erreur polling: {poll_error}")
                        await asyncio.sleep(5)
                    
                    # Vérifier si on est bloqué depuis trop longtemps
                    time_since_success = datetime.now() - last_successful_update
                    if time_since_success.total_seconds() > 300:  # 5 minutes
                        logger.error("🔥 ARRÊT: Aucune mise à jour réussie depuis 5 minutes")
                        break
                        
    except Exception as e:
        logger.error(f"❌ Erreur bot Telegram: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
    
    finally:
        # Libérer le verrou
        if lock_file and not lock_file.closed:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                logger.info("🔓 Verrou libéré")
            except:
                pass

def run_flask_app():
    """Exécuter l'API Flask"""
    try:
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"🌐 Démarrage de l'API Flask sur le port {port}...")
        
        # Démarrer Flask directement (Gunicorn gère cela via wsgi.py séparément)
        flask_app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
            
    except Exception as e:
        logger.error(f"❌ Erreur API Flask: {e}")

# =============================================================================
# MAIN - POINT D'ENTRÉE
# =============================================================================

def main():
    """Point d'entrée principal"""
    logger.info("🦕 Démarrage du Dino Challenge Bot + API")
    
    # Vérifier les variables d'environnement
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN manquant dans .env")
        return
    
    logger.info(f"📊 Base de données: {DATABASE_URL}")
    logger.info(f"🎮 Jeu: {GAME_URL}")
    logger.info(f"👤 Admin: {ORGANIZER_CHAT_ID}")
    
    # Vérifier si on est en mode production Render
    is_render_production = os.environ.get('RENDER') == 'true'
    
    try:
        if is_render_production:
            logger.info("🏭 Mode production Render détecté")
            
            # En production : démarrer les deux services
            # 1. Démarrer Flask dans un thread pour les paiements
            flask_thread = threading.Thread(target=run_flask_app, daemon=True)
            flask_thread.start()
            logger.info("✅ API Flask démarrée en arrière-plan pour les paiements")
            
            # 2. Démarrer le bot Telegram (bloquant)
            logger.info("🤖 Démarrage du bot Telegram en mode production")
            asyncio.run(run_telegram_bot())
            
        else:
            logger.info("🔧 Mode développement local")
            
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

# =============================================================================
# COMMANDES D'ADMINISTRATION
# =============================================================================

@flask_app.route('/admin/grant-access/<int:telegram_id>', methods=['GET'])
def admin_grant_access(telegram_id):
    """Donner accès manuellement à un utilisateur (pour les cas de paiement non détecté)"""
    try:
        # Vérifier l'autorisation (simple protection)
        auth_key = request.args.get('key')
        if auth_key != 'dino2025admin':  # Clé simple pour urgence
            return jsonify({'error': 'Non autorisé'}), 403
        
        # Enregistrer un paiement manuel
        success = db.record_payment(
            telegram_id=telegram_id,
            amount=MONTHLY_PRICE_CHF,
            payment_type='manual_admin',
            paypal_payment_id=f'ADMIN_{int(time.time())}'
        )
        
        if success:
            logger.info(f"🔧 ADMIN: Accès accordé manuellement à {telegram_id}")
            return jsonify({
                'success': True,
                'message': f'Accès accordé à l\'utilisateur {telegram_id}',
                'telegram_id': telegram_id
            })
        else:
            return jsonify({'error': 'Erreur lors de l\'enregistrement'}), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur admin grant access: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/admin/check-access/<int:telegram_id>', methods=['GET'])
def admin_check_access(telegram_id):
    """Vérifier l'accès d'un utilisateur"""
    try:
        has_access = db.check_user_access(telegram_id)
        user_profile = db.get_user_profile(telegram_id)
        
        # Récupérer les paiements de l'utilisateur
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payments WHERE telegram_id = %s ORDER BY payment_date DESC
            """ if db.is_postgres else """
                SELECT * FROM payments WHERE telegram_id = ? ORDER BY payment_date DESC
            """, (telegram_id,))
            payments = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'telegram_id': telegram_id,
            'has_access': has_access,
            'user_profile': user_profile,
            'payments': payments
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur admin check access: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/admin/recent-payments', methods=['GET'])
def admin_recent_payments():
    """Voir les paiements récents"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payments 
                ORDER BY payment_date DESC 
                LIMIT 20
            """)
            payments = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'recent_payments': payments,
            'count': len(payments)
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur admin recent payments: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/debug/user-status/<int:telegram_id>', methods=['GET'])
def debug_user_status(telegram_id):
    """Debug complet du statut utilisateur"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Récupérer utilisateur
            cursor.execute("""
                SELECT * FROM users WHERE telegram_id = %s
            """ if db.is_postgres else """
                SELECT * FROM users WHERE telegram_id = ?
            """, (telegram_id,))
            user = cursor.fetchone()
            
            # Récupérer scores
            cursor.execute("""
                SELECT score, created_at, month_year FROM scores 
                WHERE telegram_id = %s ORDER BY created_at DESC LIMIT 10
            """ if db.is_postgres else """
                SELECT score, created_at, month_year FROM scores 
                WHERE telegram_id = ? ORDER BY created_at DESC LIMIT 10
            """, (telegram_id,))
            scores = cursor.fetchall()
            
            # Récupérer paiements  
            cursor.execute("""
                SELECT amount, status, payment_date, month_year FROM payments 
                WHERE telegram_id = %s ORDER BY payment_date DESC LIMIT 10
            """ if db.is_postgres else """
                SELECT amount, status, payment_date, month_year FROM payments 
                WHERE telegram_id = ? ORDER BY payment_date DESC LIMIT 10
            """, (telegram_id,))
            payments = cursor.fetchall()
            
            # Vérifier accès
            has_access = db.check_user_access(telegram_id)
            
            return jsonify({
                'telegram_id': telegram_id,
                'user': dict(user) if user else None,
                'scores': [dict(s) for s in scores] if scores else [],
                'payments': [dict(p) for p in payments] if payments else [],
                'has_access': has_access,
                'current_month': datetime.now().strftime('%Y-%m')
            })
            
    except Exception as e:
        logger.error(f"❌ Erreur debug user status: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/admin/reset-test-data', methods=['POST'])
def reset_test_data():
    """Supprimer les données de test du classement"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Supprimer TOUS les scores pour test propre
            cursor.execute("DELETE FROM scores")
            
            conn.commit()
            
        logger.info("🧹 TOUS les scores supprimés pour test propre")
        return jsonify({
            'success': True,
            'message': 'TOUS les scores supprimés - classement remis à zéro'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur suppression scores: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/admin/reset-user-data', methods=['POST'])
def reset_user_data():
    """Supprimer les données d'un utilisateur spécifique pour test"""
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        
        if not telegram_id:
            return jsonify({'error': 'telegram_id requis'}), 400
            
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Supprimer les scores de l'utilisateur
            cursor.execute("""
                DELETE FROM scores WHERE telegram_id = %s
            """ if db.is_postgres else """
                DELETE FROM scores WHERE telegram_id = ?
            """, (telegram_id,))
            
            conn.commit()
            
        logger.info(f"🧹 Scores supprimés pour utilisateur {telegram_id}")
        return jsonify({
            'success': True,
            'message': f'Scores supprimés pour utilisateur {telegram_id}'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur suppression scores utilisateur: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    main()


