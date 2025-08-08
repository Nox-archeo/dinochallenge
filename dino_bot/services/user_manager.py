import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

class UserManager:
    def __init__(self):
        self.users_file = "data/users.json"
        self.users = self._load_users()
    
    def _load_users(self) -> list:
        """Charge les utilisateurs depuis le fichier JSON"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def _save_users(self):
        """Sauvegarde les utilisateurs dans le fichier JSON"""
        os.makedirs(os.path.dirname(self.users_file), exist_ok=True)
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, indent=2, ensure_ascii=False)
    
    def user_exists(self, user_id: int) -> bool:
        """Vérifie si un utilisateur existe"""
        return any(user['user_id'] == user_id for user in self.users)
    
    def get_user(self, user_id: int) -> Optional[Dict[Any, Any]]:
        """Récupère un utilisateur par son ID"""
        for user in self.users:
            if user['user_id'] == user_id:
                return user
        return None
    
    def register_user(self, user_id: int, username: str) -> bool:
        """Enregistre un nouvel utilisateur"""
        if self.user_exists(user_id):
            return False
        
        new_user = {
            'user_id': user_id,
            'username': username,
            'paypal_email': '',
            'has_paid_this_month': False,
            'last_payment_month': None,
            'last_payment_year': None,
            'daily_attempts': 0,
            'last_attempt_date': None,
            'registration_date': datetime.now().isoformat()
        }
        
        self.users.append(new_user)
        self._save_users()
        return True
    
    def update_user(self, user_id: int, updates: Dict[Any, Any]):
        """Met à jour les informations d'un utilisateur"""
        user = self.get_user(user_id)
        if user:
            user.update(updates)
            self._save_users()
    
    def set_paypal_email(self, user_id: int, paypal_email: str) -> bool:
        """Définit l'email PayPal d'un utilisateur"""
        user = self.get_user(user_id)
        if user:
            user['paypal_email'] = paypal_email
            self._save_users()
            return True
        return False
    
    def has_paid_this_month(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur a payé sa mise du mois"""
        user = self.get_user(user_id)
        if not user:
            return False
        
        now = datetime.now()
        current_month = now.month
        current_year = now.year
        
        last_payment_month = user.get('last_payment_month')
        last_payment_year = user.get('last_payment_year')
        
        return (last_payment_month == current_month and 
                last_payment_year == current_year)
    
    def register_monthly_payment(self, user_id: int) -> bool:
        """Enregistre le paiement de la mise mensuelle"""
        user = self.get_user(user_id)
        if user:
            now = datetime.now()
            user['has_paid_this_month'] = True
            user['last_payment_month'] = now.month
            user['last_payment_year'] = now.year
            self._save_users()
            return True
        return False
    
    def get_daily_attempts(self, user_id: int) -> int:
        """Récupère le nombre de tentatives aujourd'hui"""
        user = self.get_user(user_id)
        if not user:
            return 0
        
        last_attempt_date = user.get('last_attempt_date')
        if not last_attempt_date:
            return 0
        
        last_date = datetime.fromisoformat(last_attempt_date).date()
        today = datetime.now().date()
        
        # Si c'est un nouveau jour, reset les tentatives
        if last_date != today:
            user['daily_attempts'] = 0
            user['last_attempt_date'] = datetime.now().isoformat()
            self._save_users()
            return 0
        
        return user.get('daily_attempts', 0)
    
    def can_play_today(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur peut encore jouer aujourd'hui"""
        return self.get_daily_attempts(user_id) < 5
    
    def use_attempt(self, user_id: int) -> bool:
        """Utilise une tentative de jeu"""
        if not self.can_play_today(user_id):
            return False
        
        user = self.get_user(user_id)
        if user:
            today = datetime.now()
            last_attempt_date = user.get('last_attempt_date')
            
            if last_attempt_date:
                last_date = datetime.fromisoformat(last_attempt_date).date()
                if last_date != today.date():
                    # Nouveau jour, reset les tentatives
                    user['daily_attempts'] = 1
                else:
                    # Même jour, incrémenter
                    user['daily_attempts'] = user.get('daily_attempts', 0) + 1
            else:
                user['daily_attempts'] = 1
            
            user['last_attempt_date'] = today.isoformat()
            self._save_users()
            return True
        return False
    
    def set_display_name(self, user_id: int, display_name: str) -> bool:
        """Configure le nom d'affichage de l'utilisateur"""
        user = self.get_user(user_id)
        if user:
            user['display_name'] = display_name
            user['name'] = display_name  # Aussi pour la compatibilité
            self._save_users()
            return True
        return False
    
    def get_all_users(self) -> list:
        """Retourne tous les utilisateurs"""
        return self.users.copy()
    
    def get_users_with_paypal(self) -> list:
        """Retourne les utilisateurs qui ont une adresse PayPal"""
        return [user for user in self.users if user.get('paypal_email')]
