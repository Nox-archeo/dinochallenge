from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.decorators import require_registration, require_payment
from services.game_manager import GameManager

@require_registration
@require_payment
async def play_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour jouer au jeu"""
    user_id = update.effective_user.id
    game_manager = GameManager()
    
    # Vérifier si l'utilisateur peut jouer
    play_check = game_manager.can_user_play(user_id)
    
    if not play_check['can_play']:
        await update.message.reply_text(f"❌ {play_check['message']}")
        return
    
    # Créer le bouton pour jouer
    keyboard = [[InlineKeyboardButton("🎮 Lancer le jeu", url=play_check['game_url'])]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    game_stats = game_manager.get_game_stats(user_id)
    
    message = f"""
🦕 **Prêt à jouer au Dino Challenge !**

📊 **Vos statistiques :**
🎮 Tentatives restantes aujourd'hui : {play_check['attempts_remaining']}/5
🏆 Meilleur score ce mois : {game_stats['best_score']}
📈 Parties jouées ce mois : {game_stats['total_games']}
🏅 Rang actuel : #{game_stats['current_rank'] if game_stats['current_rank'] > 0 else 'Non classé'}

**Instructions :**
1. Cliquez sur le bouton ci-dessous pour jouer
2. Après votre partie, tapez votre score : `/score VOTRE_SCORE`
   Exemple : `/score 1435`

⚠️ **Important :** Vous devez soumettre votre score manuellement après chaque partie.
"""
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

@require_registration
@require_payment
async def score_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour soumettre un score"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if not context.args:
        await update.message.reply_text(
            "❌ Veuillez spécifier votre score.\n"
            "Exemple : `/score 1435`"
        )
        return
    
    score_text = context.args[0]
    game_manager = GameManager()
    
    # Valider le format du score
    is_valid, score = game_manager.validate_score_format(score_text)
    if not is_valid:
        await update.message.reply_text(
            "❌ Score invalide. Le score doit être un nombre positif.\n"
            "Exemple : `/score 1435`"
        )
        return
    
    # Soumettre le score
    result = game_manager.submit_score(user_id, username, score)
    
    if not result['success']:
        await update.message.reply_text(f"❌ {result['message']}")
        return
    
    # Score enregistré avec succès
    message = f"""
✅ **Score enregistré !**

🎯 Score soumis : **{result['score']}**
🏆 Votre meilleur score : **{result['personal_best']}**
🏅 Votre rang actuel : **#{result['rank']}**
🎮 Tentatives restantes : **{result['attempts_remaining']}/5**

"""
    
    if result['is_new_best']:
        message += "🎉 **Nouveau record personnel !** 🎉\n"
    
    if result['attempts_remaining'] > 0:
        message += f"\n🎮 Il vous reste {result['attempts_remaining']} tentative(s) aujourd'hui !"
    else:
        message += "\n⏰ Plus de tentatives aujourd'hui. Revenez demain !"
    
    await update.message.reply_text(message, parse_mode='Markdown')
