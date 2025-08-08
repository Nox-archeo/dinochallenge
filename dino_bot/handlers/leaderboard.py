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
    
    message = f"""
🏆 **Classement {month_names[month]} {year}**

💰 **Cagnotte totale :** {prize_pool:.2f} CHF
⏰ **Fin du concours :** Dans {days_left} jour(s)

🏅 **Récompenses :**
🥇 1er place : {prizes[1]:.2f} CHF (40%)
🥈 2e place : {prizes[2]:.2f} CHF (15%)
🥉 3e place : {prizes[3]:.2f} CHF (5%)

📊 **Top 10 :**
"""
    
    if not leaderboard:
        message += "\n❌ Aucun joueur classé ce mois-ci."
    else:
        for i, player in enumerate(leaderboard[:10]):
            rank = i + 1
            emoji = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
            
            # Marquer l'utilisateur actuel
            marker = " ← **VOUS**" if player['user_id'] == user_id else ""
            
            message += f"\n{emoji} {player['username']} - {player['score']} pts{marker}"
    
    # Position de l'utilisateur s'il n'est pas dans le top 10
    from services.score_manager import ScoreManager
    score_manager = ScoreManager()
    user_rank = score_manager.get_user_rank(user_id)
    user_best = score_manager.get_user_best_score(user_id)
    
    if user_rank > 10:
        message += f"\n\n👤 **Votre position :** #{user_rank}"
        message += f"\n🎯 **Votre meilleur score :** {user_best} pts"
    elif user_rank == 0:
        message += f"\n\n👤 **Votre position :** Non classé"
        message += f"\n💡 Jouez une partie pour apparaître dans le classement !"
    
    # Statistiques supplémentaires
    total_players = len(leaderboard)
    message += f"\n\n📈 **Statistiques :**"
    message += f"\n• Joueurs participants : {total_players}"
    message += f"\n• Votre rang : #{user_rank if user_rank > 0 else 'N/A'}"
    
    if total_players > 0:
        avg_score = sum(p['score'] for p in leaderboard) / len(leaderboard)
        message += f"\n• Score moyen : {avg_score:.1f} pts"
    
    await update.message.reply_text(message, parse_mode='Markdown')

@require_registration
async def top_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour afficher seulement le top 3"""
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
