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

# Prix en CHF (taxes incluses)
MONTHLY_PRICE_CHF = Decimal('11.00')

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
                        WHERE s.month_year = ? 
                          AND (u.has_paid_current_month = 1 
                               OR EXISTS (
                                   SELECT 1 FROM payments p 
                                   WHERE p.telegram_id = u.telegram_id 
                                     AND p.month_year = ? 
                                     AND p.status = 'completed'
                               )
                               OR EXISTS (
                                   SELECT 1 FROM subscriptions sub 
                                   WHERE sub.telegram_id = u.telegram_id 
                                     AND sub.status = 'active'
                               ))
                        GROUP BY u.telegram_id, u.display_name, u.first_name, u.username, u.has_paid_current_month
                        ORDER BY best_score DESC
                        LIMIT ?
                    """, (month_year, month_year, limit))
                
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
                
                result = cursor.fetchone()
                payment_count = result[0] if result else 0
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
                
                result = cursor.fetchone()
                subscription_count = result[0] if result else 0
                return subscription_count > 0
                
        except Exception as e:
            logger.error(f"❌ Erreur vérification accès: {e}")
            return False

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
                
                # Calculer le total des paiements pour le mois
                cursor.execute("""
                    SELECT SUM(amount) as total_amount, COUNT(*) as total_players
                    FROM payments 
                    WHERE month_year = %s AND status = 'completed'
                """ if self.is_postgres else """
                    SELECT SUM(amount) as total_amount, COUNT(*) as total_players
                    FROM payments 
                    WHERE month_year = ? AND status = 'completed'
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
                        "brand_name": "Dino Challenge",
                        "locale": "fr-CH",
                        "landing_page": "NO_PREFERENCE",  # Laisse PayPal choisir automatiquement
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "PAY_NOW",
                        "payment_method_preference": "UNRESTRICTED",  # Permet tous types de paiements
                        "return_url": f"https://dinochallenge-bot.onrender.com/payment-success?telegram_id={telegram_id}",
                        "cancel_url": f"{GAME_URL}?payment=cancelled"
                    }
                }
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
        
        if not order_id:
            return jsonify({'error': 'order_id requis'}), 400
        
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
            
            # Extraire telegram_id depuis reference_id
            reference_id = purchase_unit.get('reference_id', '')
            telegram_id = None
            if reference_id.startswith('dino_monthly_'):
                telegram_id = int(reference_id.replace('dino_monthly_', ''))
            
            if telegram_id and amount >= MONTHLY_PRICE_CHF:
                # Enregistrer le paiement
                success = db.record_payment(
                    telegram_id=telegram_id,
                    amount=amount,
                    payment_type='one_time',
                    paypal_payment_id=order_id
                )
                
                if success:
                    # Notifier l'utilisateur
                    if telegram_app:
                        asyncio.create_task(notify_payment_success(telegram_id, amount, 'paiement'))
                    
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
                <a href="{GAME_URL}" class="btn">🎮 Jouer maintenant</a>
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
                            order_id: '{token}'
                        }})
                    }});
                    
                    const data = await response.json();
                    
                    if (data.success) {{
                        document.getElementById('loading').style.display = 'none';
                        document.getElementById('success').style.display = 'block';
                        
                        // Rediriger vers le jeu après 3 secondes
                        setTimeout(() => {{
                            window.location.href = '{GAME_URL}?telegram_id={telegram_id}&payment=success';
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
    """Créer un abonnement mensuel PayPal"""
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
            
            # Si c'est une requête GET, rediriger directement vers PayPal
            if request.method == 'GET':
                return redirect(approval_url)
            
            # Si c'est une requête POST, retourner le JSON
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
                parse_mode='Markdown'
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
                parse_mode='Markdown'
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
                parse_mode='Markdown'
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
            message += f"💰 Payez 11 CHF avec /payment\n"
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
                parse_mode='Markdown'
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
                            parse_mode='Markdown'
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
                    if text.lower().strip() not in ['passer', 'skip', 'non', 'no']:
                        # Validation simple de l'email
                        if '@' in text and '.' in text.split('@')[1]:
                            paypal_email = text.strip()
                        else:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text="❌ **Email invalide**\n\n" +
                                     "Veuillez entrer un email valide ou tapez 'passer'.\n" +
                                     "📝 Email PayPal :"
                            )
                            return
                    
                    # Créer/mettre à jour l'utilisateur avec les nouvelles informations
                    success = db.update_user_profile(
                        telegram_id=user.id,
                        display_name=display_name,
                        paypal_email=paypal_email
                    )
                    
                    if success:
                        # Nettoyer l'état
                        del user_states[user.id]
                        
                        # Message de confirmation et redirection vers le profil
                        text_response = "✅ **Profil configuré !**\n\n"
                        text_response += f"🏷️ **Nom:** {display_name}\n"
                        if paypal_email:
                            text_response += f"📧 **Email PayPal:** {paypal_email}\n"
                        text_response += f"\n🎮 **Votre profil est maintenant prêt !**\n"
                        text_response += f"💰 Utilisez /payment pour participer au concours."
                        
                        await bot.send_message(
                            chat_id=update.message.chat_id,
                            text=text_response,
                            parse_mode='Markdown'
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
            elif text == '/payment':
                await handle_payment_command(bot, update.message)
            elif text == '/leaderboard':
                await handle_leaderboard_command(bot, update.message)
            elif text == '/profile':
                await handle_profile_command(bot, update.message)
            elif text == '/cancel_subscription':
                await handle_cancel_subscription_command(bot, update.message)
            elif text == '/help':
                await handle_help_command(bot, update.message)
            elif text == '/score':
                # Commande /score sans paramètre - expliquer l'usage
                await bot.send_message(
                    chat_id=update.message.chat_id,
                    text="🎯 **Soumettre un score**\n\n" +
                         "Pour soumettre votre score, utilisez :\n" +
                         "`/score [votre_score]`\n\n" +
                         "**Exemple :** `/score 1250`\n\n" +
                         "💡 Vous devez avoir payé votre participation (11 CHF) pour soumettre des scores.",
                    parse_mode='Markdown'
                )
            elif text.startswith('/score '):
                await handle_score_command(bot, update.message)
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

# États pour la conversation de changement de nom
user_states = {}

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
        text=text,
        parse_mode='Markdown'
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
                parse_mode='Markdown'
            )
            return
        
        elif data.startswith("pay_once_"):
            telegram_id = int(data.replace("pay_once_", ""))
            payment_url = f"https://dinochallenge-bot.onrender.com/create-payment"
            
            text = f"💳 **Paiement Unique - 11 CHF**\n\n"
            text += f"🔗 **Cliquez ici pour payer :**\n"
            text += f"[💰 Payer avec PayPal]({payment_url}?telegram_id={telegram_id})\n\n"
            text += f"📱 Vous serez redirigé vers PayPal pour finaliser le paiement.\n"
            text += f"✅ Une fois payé, votre accès sera activé automatiquement !"
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=callback_query.message.message_id,
                text=text,
                parse_mode='Markdown'
            )
        
        elif data.startswith("pay_subscription_"):
            telegram_id = int(data.replace("pay_subscription_", ""))
            subscription_url = f"https://dinochallenge-bot.onrender.com/create-subscription"
            
            text = f"🔄 **Abonnement Mensuel - 11 CHF/mois**\n\n"
            text += f"🔗 **Cliquez ici pour vous abonner :**\n"
            text += f"[🔄 S'abonner avec PayPal]({subscription_url}?telegram_id={telegram_id})\n\n"
            text += f"📱 Vous serez redirigé vers PayPal pour configurer l'abonnement.\n"
            text += f"✅ Accès permanent avec renouvellement automatique !\n"
            text += f"❌ Annulable à tout moment avec /cancel_subscription"
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=callback_query.message.message_id,
                text=text,
                parse_mode='Markdown'
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
                parse_mode='Markdown'
            )

        elif data == "payment":
            await handle_payment_command(bot, callback_query.message)
        
        elif data == "setup_profile":
            # Démarrer la configuration pour un nouvel utilisateur
            await start_user_setup(bot, callback_query.message)
        
        elif data == "change_name" or data == "edit_name":
            user_states[user.id] = "edit_name"
            await bot.send_message(
                chat_id=chat_id,
                text="✏️ **Modifier votre nom d'affichage**\n\n" +
                     "📝 Envoyez-moi votre nouveau nom :",
                parse_mode='Markdown'
            )
        
        elif data == "edit_email":
            user_states[user.id] = "edit_email"
            await bot.send_message(
                chat_id=chat_id,
                text="📧 **Modifier votre email PayPal**\n\n" +
                     "📝 Envoyez votre nouvel email PayPal ou tapez 'supprimer' pour l'effacer :",
                parse_mode='Markdown'
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
                parse_mode='Markdown',
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
                    parse_mode='Markdown'
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=callback_query.message.message_id,
                    text="❌ **Erreur**\n\nImpossible de supprimer le profil. Contactez l'support.",
                    parse_mode='Markdown'
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

💰 **Participation mensuelle : 11 CHF**
• Scores comptabilisés dans le classement
• Éligibilité aux prix mensuels
• Accès illimité tout le mois

🆓 **En attendant :** Vous pouvez essayer le mode démo

"""

        keyboard = [
            [InlineKeyboardButton("💳 PARTICIPER (11 CHF)", callback_data="payment")],
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
        parse_mode='Markdown',
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

⚠️ Pour jouer en mode compétition et gagner des prix, vous devez d'abord participer au concours (11 CHF).

🆓 **En attendant :** Vous pouvez essayer le jeu en mode démo
💰 **Pour concourir :** Payez votre participation mensuelle

"""

        keyboard = [
            [InlineKeyboardButton("💰 PARTICIPER (11 CHF)", callback_data="payment")],
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
        parse_mode='Markdown',
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
    
    # Vérifier l'accès
    has_access = db.check_user_access(user.id)
    
    text = f"""🦕 **Bienvenue dans le Dino Challenge !**

👋 Salut {user.first_name} !

🎮 **Le jeu Chrome Dino avec des vrais prix !**
🏆 Concours mensuel avec redistribution des gains

💰 **Participation : 11 CHF**
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
                InlineKeyboardButton("💰 Participer (11 CHF)", callback_data="payment")
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
        parse_mode='Markdown',
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
            parse_mode='Markdown'
        )
        return
    
    # Proposer les options de paiement
    text = f"💰 **PARTICIPER AU DINO CHALLENGE**\n\n"
    text += f"🎯 **Choisissez votre option de paiement :**\n\n"
    text += f"**💳 Paiement Unique (11 CHF)**\n"
    text += f"• Accès pour le mois en cours uniquement\n"
    text += f"• À renouveler chaque mois manuellement\n\n"
    text += f"**🔄 Abonnement Mensuel (11 CHF/mois)**\n"
    text += f"• Accès permanent avec renouvellement automatique\n"
    text += f"• Annulable à tout moment\n"
    text += f"• Plus pratique, jamais d'interruption !\n\n"
    text += f"🏆 **Prix mensuels distribués au top 3 !**"
    
    # Créer les boutons inline manuellement
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [
        [InlineKeyboardButton("💳 Paiement Unique - 11 CHF", callback_data=f"pay_once_{user.id}")],
        [InlineKeyboardButton("🔄 Abonnement Mensuel - 11 CHF/mois", callback_data=f"pay_subscription_{user.id}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_payment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        parse_mode='Markdown',
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
        
        await bot.send_message(
            chat_id=message.chat_id,
            text=text,
            parse_mode='Markdown'
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
    if not db_user.get('display_name'):
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
        keyboard.append([InlineKeyboardButton("💰 Payer ma participation (11 CHF)", callback_data="payment")])
    
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
        parse_mode='Markdown',
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
        parse_mode='Markdown'
    )

async def handle_help_command(bot, message):
    """Gérer la commande /help"""
    text = """❓ **AIDE - DINO CHALLENGE**

🎮 **Comment jouer :**
1. Payez 11 CHF avec /payment pour participer
2. Cliquez sur le lien du jeu
3. Utilisez ESPACE ou FLÈCHE HAUT pour sauter
4. Évitez les obstacles le plus longtemps possible
5. Soumettez votre score avec `/score VOTRE_SCORE`

💰 **Options de paiement :**
• **Paiement unique :** Accès pour le mois en cours
• **Abonnement :** Accès permanent avec renouvellement automatique

🏆 **Concours mensuel :**
Prix distribués au top 3 de chaque mois :
• 🥇 1er : 40% de la cagnotte
• 🥈 2e : 15% de la cagnotte  
• 🥉 3e : 5% de la cagnotte
(40% restants pour les frais d'organisation)

📋 **Commandes :**
/start - Menu principal
/payment - Participer au concours
/leaderboard - Classement mensuel
/profile - Mon profil et statistiques
/score NOMBRE - Soumettre un score (ex: /score 1234)
/cancel_subscription - Annuler l'abonnement
/help - Cette aide

🎯 **Support :**
Contactez l'organisateur pour toute question.
"""
    
    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        parse_mode='Markdown'
    )

async def handle_score_command(bot, message):
    """Gérer la commande /score pour soumettre un score"""
    user = message.from_user
    text = message.text
    
    # Vérifier si l'utilisateur a accès
    has_access = db.check_user_access(user.id)
    if not has_access:
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ **Accès requis**\n\n" +
                 "Vous devez payer votre participation (11 CHF) pour soumettre des scores.\n\n" +
                 "Utilisez /payment pour participer au concours.",
            parse_mode='Markdown'
        )
        return
    
    # Extraire le score depuis la commande
    try:
        parts = text.split(' ', 1)
        if len(parts) != 2:
            raise ValueError("Format invalide")
        
        score = int(parts[1].strip())
        if score < 0:
            raise ValueError("Score négatif")
            
    except ValueError:
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ **Format invalide**\n\n" +
                 "Utilisez: `/score VOTRE_SCORE`\n" +
                 "Exemple: `/score 1234`\n\n" +
                 "Le score doit être un nombre positif.",
            parse_mode='Markdown'
        )
        return
    
    # Enregistrer le score
    success = db.add_score(user.id, score)
    
    if success:
        # Notifier avec calcul des gains
        await notify_new_score(user.id, score)
        
        # Message de confirmation
        position_info = db.get_user_position_and_prize(user.id)
        
        message_text = f"✅ **Score enregistré !**\n\n"
        message_text += f"🎯 **Score :** {score:,} points\n"
        
        if position_info['position']:
            message_text += f"🏆 **Position :** {position_info['position']}/{position_info['total_players']}\n"
            if position_info['prize'] > 0:
                message_text += f"💰 **Gain actuel :** {position_info['prize']:.2f} CHF\n"
        
        message_text += f"\n🎮 Continuez à jouer : {GAME_URL}\n"
        message_text += f"🏆 Voir le classement : /leaderboard"
        
        await bot.send_message(
            chat_id=message.chat_id,
            text=message_text,
            parse_mode='Markdown'
        )
    else:
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ **Erreur**\n\n" +
                 "Impossible d'enregistrer votre score. Réessayez plus tard.",
            parse_mode='Markdown'
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
                BotCommand("score", "🎯 Soumettre un score"),
                BotCommand("cancel_subscription", "❌ Annuler l'abonnement"),
                BotCommand("help", "❓ Aide et règles"),
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

if __name__ == '__main__':
    main()


