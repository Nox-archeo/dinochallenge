import os
from typing import Dict, Any
from services.user_manager import UserManager
from services.score_manager import ScoreManager

class GameManager:
    def __init__(self):
        self.user_manager = UserManager()
        self.score_manager = ScoreManager()
        self.game_url = os.getenv('GAME_URL', 'https://nox-archeo.github.io/dinochallenge/')
    
    def can_user_play(self, user_id: int) -> Dict[str, Any]:
        """Vérifie si un utilisateur peut jouer et retourne les informations"""
        # Vérifier le paiement de la mise mensuelle
        if not self.user_manager.has_paid_this_month(user_id):
            return {
                'can_play': False,
                'reason': 'no_payment',
                'message': 'Vous devez payer votre mise mensuelle (10 CHF) pour participer au concours.'
            }
        
        # Vérifier les tentatives quotidiennes
        attempts_used = self.user_manager.get_daily_attempts(user_id)
        if attempts_used >= 5:
            return {
                'can_play': False,
                'reason': 'daily_limit',
                'message': f'Vous avez déjà utilisé vos 5 tentatives quotidiennes ({attempts_used}/5).'
            }
        
        return {
            'can_play': True,
            'attempts_remaining': 5 - attempts_used,
            'game_url': self.game_url
        }
    
    def submit_score(self, user_id: int, username: str, score: int) -> Dict[str, Any]:
        """Soumet un score après vérification"""
        # Vérifier si l'utilisateur peut jouer
        play_check = self.can_user_play(user_id)
        if not play_check['can_play']:
            return {
                'success': False,
                'message': play_check['message']
            }
        
        # Valider le score
        if score < 0 or score > 99999:
            return {
                'success': False,
                'message': 'Score invalide. Le score doit être entre 0 et 99999.'
            }
        
        # Utiliser une tentative
        if not self.user_manager.use_attempt(user_id):
            return {
                'success': False,
                'message': 'Impossible d\'utiliser une tentative.'
            }
        
        # Enregistrer le score
        self.score_manager.add_score(user_id, username, score)
        
        # Récupérer les nouvelles statistiques
        attempts_remaining = 5 - self.user_manager.get_daily_attempts(user_id)
        user_rank = self.score_manager.get_user_rank(user_id)
        user_best = self.score_manager.get_user_best_score(user_id)
        
        return {
            'success': True,
            'score': score,
            'attempts_remaining': attempts_remaining,
            'rank': user_rank,
            'personal_best': user_best,
            'is_new_best': score == user_best
        }
    
    def get_game_stats(self, user_id: int) -> Dict[str, Any]:
        """Récupère les statistiques de jeu d'un utilisateur"""
        user_stats = self.score_manager.get_user_stats(user_id)
        attempts_used = self.user_manager.get_daily_attempts(user_id)
        attempts_remaining = 5 - attempts_used
        
        return {
            'attempts_today': attempts_used,
            'attempts_remaining': attempts_remaining,
            'total_games': user_stats['total_games'],
            'best_score': user_stats['best_score'],
            'average_score': user_stats['average_score'],
            'current_rank': user_stats['rank']
        }
    
    def get_leaderboard_info(self) -> Dict[str, Any]:
        """Récupère les informations du classement avec cagnotte"""
        leaderboard = self.score_manager.get_monthly_leaderboard(limit=10)
        prize_pool = self.score_manager.get_total_prize_pool()
        
        # Calculer les récompenses
        prizes = {
            1: prize_pool * 0.40,  # 40% pour le 1er
            2: prize_pool * 0.15,  # 15% pour le 2e
            3: prize_pool * 0.05   # 5% pour le 3e
        }
        
        return {
            'leaderboard': leaderboard,
            'prize_pool': prize_pool,
            'prizes': prizes
        }
    
    def validate_score_format(self, score_text: str) -> tuple[bool, int]:
        """Valide le format d'un score soumis"""
        try:
            score = int(score_text)
            if 0 <= score <= 99999:
                return True, score
            else:
                return False, 0
        except ValueError:
            return False, 0
