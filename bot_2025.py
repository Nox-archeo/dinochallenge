#!/usr/bin/env python3
"""
Bot Telegram Dino Challenge 2025 - Version 100% compatible
Architecture moderne python-telegram-bot 20.6
"""
import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import json
import psycopg3
import paypalrestsdk
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Gestionnaire de base de données PostgreSQL"""
    
    def __init__(self):
        self.db_url = os.environ.get('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL manquante")
    
    def get_connection(self):
        """Créer une connexion à la base de données"""
        return psycopg3.connect(self.db_url)
    
    def init_database(self):
        """Initialiser les tables de la base de données"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Table users
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS users (
                            id BIGINT PRIMARY KEY,
                            username VARCHAR(255),
                            first_name VARCHAR(255),
                            last_name VARCHAR(255),
                            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            subscription_active BOOLEAN DEFAULT FALSE,
                            subscription_expires TIMESTAMP,
                            daily_attempts INTEGER DEFAULT 0,
                            last_play_date DATE,
                            total_games INTEGER DEFAULT 0,
                            best_score INTEGER DEFAULT 0,
                            total_score INTEGER DEFAULT 0
                        )
                    ''')
                    
                    # Table leaderboard
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS leaderboard (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT REFERENCES users(id),
                            month INTEGER,
                            year INTEGER,
                            total_score INTEGER DEFAULT 0,
                            games_played INTEGER DEFAULT 0,
                            average_score DECIMAL(10,2) DEFAULT 0,
                            rank_position INTEGER DEFAULT 0,
                            UNIQUE(user_id, month, year)
                        )
                    ''')
                    
                    # Table payments
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS payments (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT REFERENCES users(id),
                            paypal_payment_id VARCHAR(255),
                            amount DECIMAL(10,2),
                            currency VARCHAR(3) DEFAULT 'CHF',
                            status VARCHAR(50),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            subscription_start TIMESTAMP,
                            subscription_end TIMESTAMP
                        )
                    ''')
                    
                    conn.commit()
                    logger.info("✅ Base de données initialisée")
        except Exception as e:
            logger.error(f"❌ Erreur init BDD: {e}")
            raise

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Récupérer un utilisateur"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    if row:
                        return {
                            'id': row[0], 'username': row[1], 'first_name': row[2],
                            'last_name': row[3], 'joined_at': row[4],
                            'subscription_active': row[5], 'subscription_expires': row[6],
                            'daily_attempts': row[7], 'last_play_date': row[8],
                            'total_games': row[9], 'best_score': row[10], 'total_score': row[11]
                        }
                    return None
        except Exception as e:
            logger.error(f"❌ Erreur get_user: {e}")
            return None

    def create_or_update_user(self, user_data: Dict) -> bool:
        """Créer ou mettre à jour un utilisateur"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO users (id, username, first_name, last_name, joined_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            username = EXCLUDED.username,
                            first_name = EXCLUDED.first_name,
                            last_name = EXCLUDED.last_name
                    ''', (
                        user_data['id'], user_data.get('username'),
                        user_data.get('first_name'), user_data.get('last_name'),
                        datetime.now()
                    ))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"❌ Erreur create_user: {e}")
            return False

    def update_score(self, user_id: int, score: int) -> bool:
        """Mettre à jour le score d'un utilisateur"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Mettre à jour les stats utilisateur
                    cur.execute('''
                        UPDATE users SET 
                            total_games = total_games + 1,
                            total_score = total_score + %s,
                            best_score = GREATEST(best_score, %s),
                            last_play_date = CURRENT_DATE
                        WHERE id = %s
                    ''', (score, score, user_id))
                    
                    # Mettre à jour le leaderboard mensuel
                    now = datetime.now()
                    cur.execute('''
                        INSERT INTO leaderboard (user_id, month, year, total_score, games_played)
                        VALUES (%s, %s, %s, %s, 1)
                        ON CONFLICT (user_id, month, year) DO UPDATE SET
                            total_score = leaderboard.total_score + %s,
                            games_played = leaderboard.games_played + 1,
                            average_score = (leaderboard.total_score + %s) / (leaderboard.games_played + 1)
                    ''', (user_id, now.month, now.year, score, score, score))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"❌ Erreur update_score: {e}")
            return False

    def get_monthly_leaderboard(self, month: int = None, year: int = None) -> list:
        """Récupérer le classement mensuel"""
        if not month or not year:
            now = datetime.now()
            month, year = now.month, now.year
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        SELECT u.first_name, u.username, l.total_score, l.games_played, l.average_score
                        FROM leaderboard l
                        JOIN users u ON l.user_id = u.id
                        WHERE l.month = %s AND l.year = %s
                        ORDER BY l.total_score DESC
                        LIMIT 10
                    ''', (month, year))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"❌ Erreur leaderboard: {e}")
            return []

class PayPalManager:
    """Gestionnaire des paiements PayPal"""
    
    def __init__(self):
        self.client_id = os.environ.get('PAYPAL_CLIENT_ID')
        self.client_secret = os.environ.get('PAYPAL_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            logger.warning("⚠️ PayPal non configuré")
            return
        
        # Configuration PayPal
        paypalrestsdk.configure({
            "mode": "live",  # ou "sandbox" pour les tests
            "client_id": self.client_id,
            "client_secret": self.client_secret
        })
        logger.info("✅ PayPal configuré")

    def create_subscription_payment(self, user_id: int) -> Optional[str]:
        """Créer un paiement d'abonnement"""
        if not hasattr(self, 'client_id'):
            return None
        
        try:
            payment = paypalrestsdk.Payment({
                "intent": "sale",
                "payer": {"payment_method": "paypal"},
                "redirect_urls": {
                    "return_url": f"https://t.me/dino_challenge_bot?start=payment_success_{user_id}",
                    "cancel_url": f"https://t.me/dino_challenge_bot?start=payment_cancel_{user_id}"
                },
                "transactions": [{
                    "item_list": {
                        "items": [{
                            "name": "Dino Challenge - Abonnement Mensuel",
                            "sku": "dino_monthly",
                            "price": "11.00",
                            "currency": "CHF",
                            "quantity": 1
                        }]
                    },
                    "amount": {
                        "total": "11.00",
                        "currency": "CHF"
                    },
                    "description": "Abonnement mensuel Dino Challenge"
                }]
            })
            
            if payment.create():
                for link in payment.links:
                    if link.rel == "approval_url":
                        return link.href
            else:
                logger.error(f"❌ Erreur PayPal: {payment.error}")
                return None
        except Exception as e:
            logger.error(f"❌ Erreur création paiement: {e}")
            return None

class DinoChallengeBot:
    """Bot Telegram Dino Challenge 2025"""
    
    def __init__(self):
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN manquant")
        
        self.db = DatabaseManager()
        self.paypal = PayPalManager()
        
        # Créer l'application
        self.application = Application.builder().token(self.token).build()
        
        # Ajouter les handlers
        self.setup_handlers()
        
        logger.info("✅ Bot Dino Challenge initialisé")

    def setup_handlers(self):
        """Configurer les handlers de commandes"""
        # Commandes
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("profile", self.profile_command))
        self.application.add_handler(CommandHandler("leaderboard", self.leaderboard_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        
        # Callbacks
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /start"""
        user = update.effective_user
        
        # Créer ou mettre à jour l'utilisateur
        user_data = {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
        self.db.create_or_update_user(user_data)
        
        # Menu principal
        keyboard = [
            [InlineKeyboardButton("🎮 Jouer au Dino", url="https://nox-archeo.github.io/dinochallenge/")],
            [InlineKeyboardButton("👤 Mon Profil", callback_data="profile")],
            [InlineKeyboardButton("🏆 Classement", callback_data="leaderboard")],
            [InlineKeyboardButton("💳 S'abonner (11 CHF/mois)", callback_data="subscribe")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = f"""
🦕 **Bienvenue dans Dino Challenge !**

Salut {user.first_name} ! 👋

🎯 **Règles du jeu :**
• 5 tentatives gratuites par jour
• Abonnement premium : tentatives illimitées
• Classement mensuel avec prix

🏆 **Prix mensuels :**
• 1er place : 50 CHF
• 2ème place : 30 CHF  
• 3ème place : 20 CHF

Clique sur "🎮 Jouer au Dino" pour commencer !
        """
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /profile"""
        await self.show_profile(update)

    async def show_profile(self, update: Update):
        """Afficher le profil utilisateur"""
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text("❌ Profil non trouvé. Utilisez /start")
            return
        
        # Calculer les tentatives restantes
        today = datetime.now().date()
        daily_attempts = user_data.get('daily_attempts', 0)
        last_play = user_data.get('last_play_date')
        
        if last_play != today:
            daily_attempts = 0  # Reset quotidien
        
        attempts_left = 5 - daily_attempts if not user_data.get('subscription_active') else "Illimitées"
        
        profile_text = f"""
👤 **Votre Profil**

📊 **Statistiques :**
• Parties jouées : {user_data.get('total_games', 0)}
• Meilleur score : {user_data.get('best_score', 0)}
• Score total : {user_data.get('total_score', 0)}
• Tentatives restantes : {attempts_left}

💳 **Abonnement :** {'✅ Actif' if user_data.get('subscription_active') else '❌ Inactif'}

🎮 Bonne chance pour vos prochaines parties !
        """
        
        keyboard = [
            [InlineKeyboardButton("🎮 Jouer", url="https://nox-archeo.github.io/dinochallenge/")],
            [InlineKeyboardButton("🏆 Classement", callback_data="leaderboard")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                profile_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                profile_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /leaderboard"""
        await self.show_leaderboard(update)

    async def show_leaderboard(self, update: Update):
        """Afficher le classement"""
        leaderboard = self.db.get_monthly_leaderboard()
        
        if not leaderboard:
            text = "🏆 Aucun score ce mois-ci. Soyez le premier !"
        else:
            text = "🏆 **Classement du mois**\n\n"
            
            for i, (first_name, username, total_score, games_played, avg_score) in enumerate(leaderboard, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                name = first_name or username or "Joueur anonyme"
                text += f"{medal} {name}\n"
                text += f"   📊 {total_score} pts • {games_played} parties • {avg_score:.1f} moy.\n\n"
        
        keyboard = [
            [InlineKeyboardButton("👤 Mon Profil", callback_data="profile")],
            [InlineKeyboardButton("🎮 Jouer", url="https://nox-archeo.github.io/dinochallenge/")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /subscribe"""
        await self.show_subscription(update)

    async def show_subscription(self, update: Update):
        """Afficher les options d'abonnement"""
        text = """
💳 **Abonnement Premium**

🌟 **Avantages :**
• Tentatives illimitées
• Accès prioritaire aux nouveautés
• Support premium

💰 **Prix :** 11 CHF/mois

🏆 **Prix mensuels :**
• 1er : 50 CHF
• 2ème : 30 CHF
• 3ème : 20 CHF

Cliquez sur "Payer avec PayPal" pour vous abonner !
        """
        
        keyboard = [
            [InlineKeyboardButton("💳 Payer avec PayPal", callback_data="paypal_payment")],
            [InlineKeyboardButton("👤 Mon Profil", callback_data="profile")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gérer les callbacks des boutons"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "profile":
            await self.show_profile(update)
        elif query.data == "leaderboard":
            await self.show_leaderboard(update)
        elif query.data == "subscribe":
            await self.show_subscription(update)
        elif query.data == "paypal_payment":
            await self.handle_paypal_payment(update)
        elif query.data == "menu":
            await self.show_main_menu(update)

    async def handle_paypal_payment(self, update: Update):
        """Gérer le paiement PayPal"""
        user_id = update.effective_user.id
        
        payment_url = self.paypal.create_subscription_payment(user_id)
        
        if payment_url:
            keyboard = [
                [InlineKeyboardButton("💳 Payer maintenant", url=payment_url)],
                [InlineKeyboardButton("🔙 Retour", callback_data="subscribe")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                "💳 **Paiement PayPal**\n\nCliquez sur le bouton ci-dessous pour procéder au paiement sécurisé.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.callback_query.edit_message_text(
                "❌ Erreur lors de la création du paiement. Veuillez réessayer plus tard.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="subscribe")
                ]])
            )

    async def show_main_menu(self, update: Update):
        """Afficher le menu principal"""
        keyboard = [
            [InlineKeyboardButton("🎮 Jouer au Dino", url="https://nox-archeo.github.io/dinochallenge/")],
            [InlineKeyboardButton("👤 Mon Profil", callback_data="profile")],
            [InlineKeyboardButton("🏆 Classement", callback_data="leaderboard")],
            [InlineKeyboardButton("💳 S'abonner (11 CHF/mois)", callback_data="subscribe")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "🦕 **Menu Principal Dino Challenge**\n\nQue souhaitez-vous faire ?"
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def run(self):
        """Démarrer le bot"""
        try:
            # Initialiser la base de données
            self.db.init_database()
            
            # Démarrer le bot
            logger.info("🚀 Démarrage du bot...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("✅ Bot démarré avec succès!")
            
            # Garder le bot en vie
            await self.application.updater.idle()
            
        except Exception as e:
            logger.error(f"❌ Erreur démarrage bot: {e}")
            raise
        finally:
            await self.application.stop()

async def main():
    """Point d'entrée principal"""
    try:
        bot = DinoChallengeBot()
        await bot.run()
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
