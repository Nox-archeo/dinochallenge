import json
import os
from datetime import datetime
from typing import List, Dict, Any
from utils.time_utils import get_current_month, get_month_start_end

class ScoreManager:
    def __init__(self):
        self.scores_file = "data/scores.json"
        self.scores = self._load_scores()
    
    def _load_scores(self) -> list:
        """Charge les scores depuis le fichier JSON"""
        if os.path.exists(self.scores_file):
            try:
                with open(self.scores_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def _save_scores(self):
        """Sauvegarde les scores dans le fichier JSON"""
        os.makedirs(os.path.dirname(self.scores_file), exist_ok=True)
        with open(self.scores_file, 'w', encoding='utf-8') as f:
            json.dump(self.scores, f, indent=2, ensure_ascii=False)
    
    def add_score(self, user_id: int, username: str, score: int) -> bool:
        """Ajoute un nouveau score"""
        new_score = {
            'user_id': user_id,
            'username': username,
            'score': score,
            'timestamp': datetime.now().isoformat(),
            'month': get_current_month()[0],
            'year': get_current_month()[1]
        }
        
        self.scores.append(new_score)
        self._save_scores()
        return True
    
    def get_user_scores(self, user_id: int, month: int = None, year: int = None) -> List[Dict[Any, Any]]:
        """Récupère tous les scores d'un utilisateur pour un mois donné"""
        if month is None or year is None:
            month, year = get_current_month()
        
        return [
            score for score in self.scores
            if score['user_id'] == user_id and 
               score['month'] == month and 
               score['year'] == year
        ]
    
    def get_user_best_score(self, user_id: int, month: int = None, year: int = None) -> int:
        """Récupère le meilleur score d'un utilisateur pour un mois donné"""
        user_scores = self.get_user_scores(user_id, month, year)
        if not user_scores:
            return 0
        return max(score['score'] for score in user_scores)
    
    def get_monthly_leaderboard(self, month: int = None, year: int = None, limit: int = 10) -> List[Dict[Any, Any]]:
        """Récupère le classement mensuel"""
        if month is None or year is None:
            month, year = get_current_month()
        
        # Récupérer tous les scores du mois
        monthly_scores = [
            score for score in self.scores
            if score['month'] == month and score['year'] == year
        ]
        
        # Grouper par utilisateur et garder le meilleur score
        user_best_scores = {}
        for score in monthly_scores:
            user_id = score['user_id']
            if user_id not in user_best_scores or score['score'] > user_best_scores[user_id]['score']:
                user_best_scores[user_id] = {
                    'user_id': user_id,
                    'username': score['username'],
                    'score': score['score'],
                    'timestamp': score['timestamp']
                }
        
        # Trier par score décroissant
        leaderboard = sorted(user_best_scores.values(), key=lambda x: x['score'], reverse=True)
        
        return leaderboard[:limit]
    
    def get_user_rank(self, user_id: int, month: int = None, year: int = None) -> int:
        """Récupère le rang d'un utilisateur dans le classement mensuel"""
        leaderboard = self.get_monthly_leaderboard(month, year, limit=1000)  # Récupérer tout le classement
        
        for i, entry in enumerate(leaderboard):
            if entry['user_id'] == user_id:
                return i + 1
        
        return 0  # Utilisateur pas dans le classement
    
    def get_total_prize_pool(self, month: int = None, year: int = None) -> float:
        """Calcule la cagnotte totale du mois (nombre d'utilisateurs * 10 CHF)"""
        if month is None or year is None:
            month, year = get_current_month()
        
        # Compter les utilisateurs uniques qui ont joué ce mois
        monthly_scores = [
            score for score in self.scores
            if score['month'] == month and score['year'] == year
        ]
        
        unique_users = len(set(score['user_id'] for score in monthly_scores))
        return unique_users * 10.0  # 10 CHF par utilisateur
    
    def get_user_stats(self, user_id: int, month: int = None, year: int = None) -> Dict[str, Any]:
        """Récupère les statistiques d'un utilisateur"""
        user_scores = self.get_user_scores(user_id, month, year)
        
        if not user_scores:
            return {
                'total_games': 0,
                'best_score': 0,
                'average_score': 0,
                'rank': 0
            }
        
        total_games = len(user_scores)
        best_score = max(score['score'] for score in user_scores)
        average_score = sum(score['score'] for score in user_scores) / total_games
        rank = self.get_user_rank(user_id, month, year)
        
        return {
            'total_games': total_games,
            'best_score': best_score,
            'average_score': round(average_score, 1),
            'rank': rank
        }
    
    def clear_old_scores(self, months_to_keep: int = 12):
        """Supprime les anciens scores (garde seulement X mois)"""
        current_date = datetime.now()
        cutoff_date = current_date.replace(month=current_date.month - months_to_keep)
        
        self.scores = [
            score for score in self.scores
            if datetime.fromisoformat(score['timestamp']) > cutoff_date
        ]
        
        self._save_scores()
