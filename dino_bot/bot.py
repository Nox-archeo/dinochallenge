#!/usr/bin/env python3
"""
Dino Challenge Bot - Bot Telegram pour concours mensuel Chrome Dino Runner

Fonctionnalités :
- Abonnement payant 10 CHF/mois via PayPal
- 5 tentatives de jeu par jour
- Classement mensuel avec récompenses
- Gestion automatique des paiements de prix
"""

import os
import logging
import asyncio
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv
from threading import Thread

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes
)

# Imports des handlers
from handlers.start import start_handler, menu_handler
from handlers.play import play_handler, score_handler
from handlers.profile import (
    profile_handler, profile_callback_handler, 
    setpaypal_handler
)
from handlers.leaderboard import leaderboard_handler, top_handler
from handlers.help import help_handler, rules_handler, contact_handler
from handlers.payment import (
    payment_success_handler, payment_cancel_handler,
    check_payment_handler, payment_history_handler
)

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Chargement des variables d'environnement
load_dotenv()

# Configuration
ORGANIZER_CHAT_ID = int(os.getenv('ORGANIZER_CHAT_ID', '123456789'))  # Remplacez par votre ID Telegram

class DinoBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN non trouvé dans les variables d'environnement")
        
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
        self._setup_scheduler()
    
    async def _setup_bot_commands(self):
        """Configure le menu hamburger (bouton avec 3 traits) avec les commandes disponibles"""
        commands = [
            BotCommand("start", "🏠 Menu principal"),
            BotCommand("play", "🎮 Jouer au Dino Challenge"),
            BotCommand("profile", "👤 Mon profil et paiements"),
            BotCommand("leaderboard", "🏆 Classement mensuel"),
            BotCommand("top", "🥇 Voir le top 3"),
            BotCommand("help", "❓ Aide et règles du jeu"),
            BotCommand("setpaypal", "📧 Configurer email PayPal"),
            BotCommand("checkpayment", "💳 Vérifier mes paiements"),
            BotCommand("admin_prizes", "🎁 [ADMIN] Test distribution prix"),
        ]
        
        await self.application.bot.set_my_commands(commands)
        logger.info("Menu hamburger configuré avec succès")
    
    def _setup_handlers(self):
        """Configure tous les handlers du bot"""
        app = self.application
        
        # Handlers de commandes
        app.add_handler(CommandHandler("start", start_handler))
        app.add_handler(CommandHandler("play", play_handler))
        app.add_handler(CommandHandler("score", score_handler))
        app.add_handler(CommandHandler("profile", profile_handler))
        app.add_handler(CommandHandler("leaderboard", leaderboard_handler))
        app.add_handler(CommandHandler("top", top_handler))
        app.add_handler(CommandHandler("help", help_handler))
        app.add_handler(CommandHandler("rules", rules_handler))
        app.add_handler(CommandHandler("contact", contact_handler))
        app.add_handler(CommandHandler("setpaypal", setpaypal_handler))
        app.add_handler(CommandHandler("checkpayment", check_payment_handler))
        app.add_handler(CommandHandler("payments", payment_history_handler))
        app.add_handler(CommandHandler("admin_prizes", self._admin_prizes_handler))  # Commande admin
        
        # Handlers de callbacks (boutons inline)
        app.add_handler(CallbackQueryHandler(profile_callback_handler))
        
        # Handler pour les messages du menu (boutons du clavier)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            menu_handler
        ))
        
        # Handler d'erreur
        app.add_error_handler(self._error_handler)
        
        logger.info("Handlers configurés avec succès")
    
    def _setup_scheduler(self):
        """Configure les tâches programmées"""
        # Tâche mensuelle pour distribuer les prix (le 1er de chaque mois)
        schedule.every().day.at("00:01").do(self._check_monthly_prizes)
        
        # Tâche quotidienne pour nettoyer les données
        schedule.every().day.at("03:00").do(self._daily_cleanup)
        
        logger.info("Scheduler configuré avec succès")
    
    async def _error_handler(self, update: Update, context):
        """Gère les erreurs du bot"""
        logger.error(f"Exception lors de la mise à jour {update}:", exc_info=context.error)
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Une erreur s'est produite. Veuillez réessayer plus tard.\n"
                "Si le problème persiste, contactez le support."
            )
    
    def _check_monthly_prizes(self):
        """Vérifie s'il faut distribuer les prix mensuels"""
        now = datetime.now()
        # Ne distribuer les prix que le 1er du mois
        if now.day == 1:
            self._monthly_prizes_distribution()
    
    def _monthly_prizes_distribution(self):
        """Génère la liste des gagnants et envoie à l'organisateur"""
        try:
            from services.game_manager import GameManager
            from utils.time_utils import get_current_month
            
            game_manager = GameManager()
            
            # Récupérer le classement du mois précédent
            current_month, current_year = get_current_month()
            prev_month = current_month - 1 if current_month > 1 else 12
            prev_year = current_year if current_month > 1 else current_year - 1
            
            leaderboard_info = game_manager.get_leaderboard_info()
            leaderboard = leaderboard_info['leaderboard']
            prize_pool = leaderboard_info['prize_pool']
            
            if len(leaderboard) >= 1:
                # Préparer le message pour l'organisateur
                message = f"""🏆 **DISTRIBUTION DES GAINS - {prev_month:02d}/{prev_year}**

💰 **Cagnotte totale :** {prize_pool} CHF
👥 **Participants :** {len(leaderboard)} joueurs

🎯 **GAGNANTS À PAYER :**
"""
                
                # Calculer les montants
                amounts = {
                    1: int(prize_pool * 0.40),  # 40% pour le 1er
                    2: int(prize_pool * 0.15),  # 15% pour le 2e  
                    3: int(prize_pool * 0.05)   # 5% pour le 3e
                }
                
                # Ajouter les gagnants au message
                for i, player in enumerate(leaderboard[:3], 1):
                    rank_emoji = ["🥇", "🥈", "🥉"][i-1]
                    amount = amounts.get(i, 0)
                    email = player.get('paypal_email', '❌ EMAIL MANQUANT')
                    
                    message += f"\n{rank_emoji} **#{i} - {player['name']}**"
                    message += f"\n   📧 Email: `{email}`"
                    message += f"\n   💰 Montant: **{amount} CHF**"
                    message += f"\n   🎮 Score: {player['score']} pts\n"
                
                message += f"""
📋 **INSTRUCTIONS :**
1. Connectez-vous à PayPal
2. Allez dans "Envoyer de l'argent"
3. Copiez-collez les emails ci-dessus
4. Envoyez les montants correspondants
5. Le bot notifiera automatiquement les gagnants

⚠️ **Emails manquants :** Contactez les joueurs sans email PayPal configuré.
"""
                
                # Envoyer le message à l'organisateur (vous)
                # Remplacez par votre ID Telegram
                ORGANIZER_CHAT_ID = "VOTRE_ID_TELEGRAM"  # À remplacer par votre vraie ID
                
                # Pour le moment, on log le message
                logger.info(f"Message pour l'organisateur:\n{message}")
                
                # TODO: Décommenter et mettre votre ID Telegram
                # import asyncio
                # asyncio.create_task(
                #     self.application.bot.send_message(
                #         chat_id=ORGANIZER_CHAT_ID,
                #         text=message,
                #         parse_mode='Markdown'
                #     )
                # )
                
                # Notifier automatiquement les gagnants
                self._notify_winners(leaderboard[:3], amounts)
                
                logger.info(f"Distribution des prix préparée: {len(leaderboard[:3])} gagnants")
                
            else:
                logger.info("Aucun joueur à récompenser ce mois")
                
        except Exception as e:
            logger.error(f"Erreur lors de la préparation des prix: {e}")
    
    async def _admin_prizes_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande admin pour tester la génération des prix"""
        if update.effective_user.id != ORGANIZER_CHAT_ID:  # Remplacez par votre ID Telegram
            await update.message.reply_text("❌ Commande réservée à l'organisateur")
            return
            
        # Test avec des données fictives
        await self._test_monthly_prizes_distribution(context)
        await update.message.reply_text("✅ Test de distribution des prix terminé - vérifiez les logs pour voir le message qui serait envoyé")
        
    async def _test_monthly_prizes_distribution(self, context):
        """Version test de la distribution des prix avec données fictives"""
        try:
            import json
            
            # Charger les données de test
            try:
                with open('data/users_test.json', 'r') as f:
                    test_users = json.load(f)
                with open('data/scores_test.json', 'r') as f:
                    test_scores = json.load(f)
            except FileNotFoundError:
                logger.error("Fichiers de test non trouvés. Création de données fictives...")
                # Créer des données fictives si les fichiers n'existent pas
                test_users = {
                    "user_1": {"telegram_id": 1001, "first_name": "Alice", "paypal_email": "alice@example.com", "has_paid_current_month": True},
                    "user_2": {"telegram_id": 1002, "first_name": "Bob", "paypal_email": "bob@example.com", "has_paid_current_month": True},
                    "user_3": {"telegram_id": 1003, "first_name": "Charlie", "paypal_email": "charlie@example.com", "has_paid_current_month": True}
                }
                test_scores = {
                    "2024-12": {
                        "1001": [2500, 3200, 2800],
                        "1002": [1800, 2200, 1950], 
                        "1003": [5200, 4800, 5500]
                    }
                }
            
            current_month = "2024-12"
            
            # Calculer le classement des utilisateurs payants
            leaderboard = []
            for user_key, user_data in test_users.items():
                if user_data.get('has_paid_current_month', False):
                    user_id = str(user_data['telegram_id'])
                    if current_month in test_scores and user_id in test_scores[current_month]:
                        scores = test_scores[current_month][user_id]
                        best_score = max(scores) if scores else 0
                        leaderboard.append({
                            'user_id': user_id,
                            'name': user_data['first_name'],
                            'paypal_email': user_data['paypal_email'],
                            'best_score': best_score
                        })
            
            # Trier par meilleur score (décroissant)
            leaderboard.sort(key=lambda x: x['best_score'], reverse=True)
            
            if leaderboard:
                # Calcul des montants
                total_participants = len(leaderboard)
                total_prize_pool = total_participants * 10  # 10 CHF par participant
                
                amounts = [
                    total_prize_pool * 0.5,  # 50% pour le 1er
                    total_prize_pool * 0.3,  # 30% pour le 2e  
                    total_prize_pool * 0.2   # 20% pour le 3e
                ]
                
                # Générer le message pour l'organisateur
                organizer_message = f"🎉 **DISTRIBUTION DES PRIX - MOIS {current_month}**\n\n"
                organizer_message += f"💰 **Participants payants:** {total_participants}\n"
                organizer_message += f"💵 **Cagnotte totale:** {total_prize_pool} CHF\n\n"
                organizer_message += "🏆 **GAGNANTS À RÉCOMPENSER:**\n\n"
                
                prizes = ["🥇 1er place", "🥈 2e place", "🥉 3e place"]
                
                for i, winner in enumerate(leaderboard[:3]):
                    if i < len(amounts):
                        organizer_message += f"{prizes[i]}: **{winner['name']}**\n"
                        organizer_message += f"📧 Email PayPal: `{winner['paypal_email']}`\n"
                        organizer_message += f"📊 Meilleur score: {winner['best_score']}\n"
                        organizer_message += f"💰 Montant à envoyer: **{amounts[i]:.2f} CHF**\n\n"
                
                organizer_message += "⚠️ **Action requise:** Envoyez manuellement les paiements PayPal aux emails ci-dessus.\n"
                organizer_message += "Après envoi, les gagnants seront automatiquement notifiés."
                
                print("🔥 MESSAGE TEST ORGANISATEUR 🔥")
                print("=" * 50)
                print(organizer_message)
                print("=" * 50)
                
                logger.info(f"Test: Distribution des prix préparée pour {len(leaderboard[:3])} gagnants")
                
            else:
                print("❌ Aucun joueur payant trouvé dans les données de test")
                logger.info("Test: Aucun joueur à récompenser")
                
        except Exception as e:
            logger.error(f"Erreur lors du test de distribution des prix: {e}")
            print(f"❌ Erreur: {e}")
    
    def _notify_winners(self, winners, amounts):
        """Notifie automatiquement les gagnants"""
        try:
            import asyncio
            
            for i, player in enumerate(winners, 1):
                rank_emoji = ["🥇", "🥈", "🥉"][i-1]
                amount = amounts.get(i, 0)
                
                message = f"""🎉 **FÉLICITATIONS !** 🎉

{rank_emoji} Vous avez terminé **#{i}** du Dino Challenge !

💰 **Votre gain :** {amount} CHF
🎮 **Votre score :** {player['score']} points

💳 **Paiement :**
Vos gains seront envoyés dans les 24h sur votre compte PayPal.
Email configuré : `{player.get('paypal_email', 'Non configuré')}`

🔔 Vous recevrez une notification PayPal dès réception.

🦕 Merci d'avoir participé au Dino Challenge !
"""
                
                # Envoyer le message au gagnant
                user_id = player.get('user_id')
                if user_id:
                    # TODO: Implémenter l'envoi du message
                    logger.info(f"Notification gagnant #{i}: {player['name']} ({user_id})")
                    # asyncio.create_task(
                    #     self.application.bot.send_message(
                    #         chat_id=user_id,
                    #         text=message,
                    #         parse_mode='Markdown'
                    #     )
                    # )
                
        except Exception as e:
            logger.error(f"Erreur lors de la notification des gagnants: {e}")
    
    def _daily_cleanup(self):
        """Nettoyage quotidien des données"""
        try:
            from services.score_manager import ScoreManager
            
            score_manager = ScoreManager()
            # Garder seulement 12 mois de données
            score_manager.clear_old_scores(months_to_keep=12)
            
            logger.info("Nettoyage quotidien effectué")
            
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage: {e}")
    
    def _run_scheduler(self):
        """Exécute les tâches programmées en arrière-plan"""
        while True:
            schedule.run_pending()
            time.sleep(60)  # Vérifier toutes les minutes
    
    def run(self):
        """Lance le bot (méthode synchrone)"""
        try:
            logger.info("🦕 Démarrage du Dino Challenge Bot...")
            
            # Démarrer le scheduler en arrière-plan
            scheduler_thread = Thread(target=self._run_scheduler, daemon=True)
            scheduler_thread.start()
            
            # Pour Render : démarrer un serveur HTTP simple en arrière-plan
            self._start_health_server()
            
            # Démarrer le bot directement avec run_polling (synchrone)
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 Arrêt du bot demandé par l'utilisateur")
        except Exception as e:
            logger.error(f"❌ Erreur fatale: {e}")

    def _start_health_server(self):
        """Démarre un serveur HTTP simple pour Render (health check)"""
        try:
            from http.server import HTTPServer, SimpleHTTPRequestHandler
            import threading
            
            class HealthHandler(SimpleHTTPRequestHandler):
                def do_GET(self):
                    if self.path == '/health':
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"status": "ok", "bot": "running"}')
                    else:
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b'<h1>Dino Challenge Bot is running!</h1><p>Bot status: Active</p>')
                        
                def log_message(self, format, *args):
                    return  # Supprimer les logs HTTP
            
            port = int(os.getenv('PORT', 10000))  # Render utilise PORT
            server = HTTPServer(('0.0.0.0', port), HealthHandler)
            
            def run_server():
                logger.info(f"🌐 Serveur HTTP démarré sur le port {port}")
                server.serve_forever()
            
            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            
        except Exception as e:
            logger.warning(f"⚠️ Impossible de démarrer le serveur HTTP: {e}")
            logger.info("🤖 Le bot fonctionnera sans serveur HTTP")

def main():
    """Point d'entrée principal"""
    print("🦕 Dino Challenge Bot - v1.0")
    print("=" * 40)
    
    try:
        bot = DinoBot()
        bot.run()
    except ValueError as e:
        print(f"❌ Erreur de configuration: {e}")
        print("Vérifiez votre fichier .env")
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")

if __name__ == '__main__':
    main()
