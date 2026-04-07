from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import require_registration
from services.game_manager import GameManager
from utils.time_utils import get_current_month, days_until_month_end

@require_registration
async def leaderboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour afficher le classement"""
    user_id = update.effective_user.id
    game_manager = GameManager()
    
    # Récupérer les informations du classement
    leaderboard_info = game_manager.get_leaderboard_info()
    leaderboard = leaderboard_info['leaderboard']
    prize_pool = leaderboard_info['prize_pool']
    prizes = leaderboard_info['prizes']
    
    # Informations du mois actuel
    month, year = get_current_month()
    month_names = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]
    
    days_left = days_until_month_end()
    
    message = f"🏆 Classement {month_names[month]} {year}\n"
    message += f"\n💰 Cagnotte totale : {prize_pool:.2f} CHF"
    message += f"\n⏰ Fin du concours : Dans {days_left} jour(s)"
    message += f"\n\n🏅 Récompenses :"
    message += f"\n🥇 1er place : {prizes[1]:.2f} CHF (40%)"
    message += f"\n🥈 2e place : {prizes[2]:.2f} CHF (15%)"
    message += f"\n🥉 3e place : {prizes[3]:.2f} CHF (5%)"
    message += f"\n\n📊 Top 10 :"

    if not leaderboard:
        message += "\n❌ Aucun joueur classé ce mois-ci."
    else:
        for i, player in enumerate(leaderboard[:10]):
            marker = " ← VOUS" if player['user_id'] == user_id else ""
            message += f"\n{i+1}. {player['username']} - {player['score']} pts{marker}"

    # Rang et score de l'utilisateur
    score_manager = game_manager.score_manager
    user_rank = score_manager.get_user_rank(user_id)
    user_best = score_manager.get_user_best_score(user_id)
    if user_rank > 0:
        message += f"\n\n👤 Votre position : #{user_rank}"
        message += f"\n🏅 Votre meilleur score : {user_best} pts"
    elif user_rank == 0:
        message += f"\n\n👤 Votre position : Non classé"
        message += f"\n💡 Jouez une partie pour apparaître dans le classement !"

    # Statistiques supplémentaires - compter les vrais participants payants
    try:
        import os
        import psycopg2
        from datetime import datetime
        
        current_month = datetime.now().strftime('%Y-%m')
        DATABASE_URL = os.getenv('DATABASE_URL')
        
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT telegram_id) FROM payments 
                WHERE month_year = %s AND status = 'completed'
            """, (current_month,))
            result = cursor.fetchone()
            total_players = result[0] if result and result[0] is not None else len(leaderboard)
            conn.close()
        else:
            total_players = len(leaderboard)
    except Exception as e:
        total_players = len(leaderboard)  # Fallback
        
    message += f"\n\n📈 Statistiques :"
    message += f"\n• Joueurs participants : {total_players}"
    message += f"\n• Votre rang : #{user_rank if user_rank > 0 else 'N/A'}"

    await update.message.reply_text(message)

@require_registration
async def top_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game_manager = GameManager()
    
    leaderboard_info = game_manager.get_leaderboard_info()
    leaderboard = leaderboard_info['leaderboard']
    prizes = leaderboard_info['prizes']
    
    message = "🏆 **TOP 3 du mois**\n\n"
    
    if len(leaderboard) >= 1:
        message += f"🥇 **{leaderboard[0]['username']}** - {leaderboard[0]['score']} pts\n"
        message += f"💰 Récompense : {prizes[1]:.2f} CHF\n\n"
    
    if len(leaderboard) >= 2:
        message += f"🥈 **{leaderboard[1]['username']}** - {leaderboard[1]['score']} pts\n"
        message += f"💰 Récompense : {prizes[2]:.2f} CHF\n\n"
    
    if len(leaderboard) >= 3:
        message += f"🥉 **{leaderboard[2]['username']}** - {leaderboard[2]['score']} pts\n"
        message += f"💰 Récompense : {prizes[3]:.2f} CHF\n\n"
    
    if len(leaderboard) < 3:
        message += "🔓 Places encore disponibles !\n"
    
    # Position de l'utilisateur
    from services.score_manager import ScoreManager
    score_manager = ScoreManager()
    user_rank = score_manager.get_user_rank(user_id)
    
    if user_rank > 0:
        message += f"👤 Votre position : #{user_rank}"
    else:
        message += f"👤 Vous n'êtes pas encore classé"
    
    await update.message.reply_text(message, parse_mode='Markdown')
