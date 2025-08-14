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
