import os
import json
import requests
import paypalrestsdk
from datetime import datetime
from typing import Dict, Any, List
from services.user_manager import UserManager

class PayPalService:
    def __init__(self):
        self.client_id = os.getenv('PAYPAL_CLIENT_ID')
        self.client_secret = os.getenv('PAYPAL_SECRET_KEY')
        self.sandbox = os.getenv('PAYPAL_SANDBOX', 'True').lower() == 'true'
        self.payments_file = "data/payments.json"
        
        # Configuration PayPal SDK
        paypalrestsdk.configure({
            "mode": "sandbox" if self.sandbox else "live",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        })
        
        self.payments = self._load_payments()
        self.user_manager = UserManager()
    
    def _load_payments(self) -> list:
        """Charge l'historique des paiements"""
        if os.path.exists(self.payments_file):
            try:
                with open(self.payments_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def _save_payments(self):
        """Sauvegarde l'historique des paiements"""
        os.makedirs(os.path.dirname(self.payments_file), exist_ok=True)
        with open(self.payments_file, 'w', encoding='utf-8') as f:
            json.dump(self.payments, f, indent=2, ensure_ascii=False)
    
    def create_monthly_bet_payment(self, user_id: int, username: str) -> Dict[str, Any]:
        """Crée un lien de paiement pour la mise mensuelle"""
        try:
            payment = paypalrestsdk.Payment({
                "intent": "sale",
                "payer": {
                    "payment_method": "paypal"
                },
                "redirect_urls": {
                    "return_url": "http://localhost:8000/payment/success",
                    "cancel_url": "http://localhost:8000/payment/cancel"
                },
                "transactions": [{
                    "item_list": {
                        "items": [{
                            "name": "Mise Dino Challenge",
                            "sku": "dino_bet_monthly",
                            "price": "10.00",
                            "currency": "CHF",
                            "quantity": 1
                        }]
                    },
                    "amount": {
                        "total": "10.00",
                        "currency": "CHF"
                    },
                    "description": f"Mise mensuelle Dino Challenge pour {username}"
                }]
            })
            
            if payment.create():
                # Sauvegarder le paiement en attente
                payment_record = {
                    'payment_id': payment.id,
                    'user_id': user_id,
                    'username': username,
                    'amount': 10.00,
                    'currency': 'CHF',
                    'status': 'created',
                    'type': 'monthly_bet',
                    'created_at': datetime.now().isoformat()
                }
                
                self.payments.append(payment_record)
                self._save_payments()
                
                # Récupérer l'URL d'approbation
                for link in payment.links:
                    if link.rel == "approval_url":
                        return {
                            'success': True,
                            'payment_url': link.href,
                            'payment_id': payment.id
                        }
            
            return {
                'success': False,
                'error': 'Erreur lors de la création du paiement PayPal'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Erreur PayPal: {str(e)}'
            }
    
    def execute_payment(self, payment_id: str, payer_id: str) -> Dict[str, Any]:
        """Exécute un paiement après approbation"""
        try:
            payment = paypalrestsdk.Payment.find(payment_id)
            
            if payment.execute({"payer_id": payer_id}):
                # Trouver le paiement dans notre base
                payment_record = None
                for p in self.payments:
                    if p['payment_id'] == payment_id:
                        payment_record = p
                        break
                
                if payment_record:
                    # Mettre à jour le statut
                    payment_record['status'] = 'completed'
                    payment_record['completed_at'] = datetime.now().isoformat()
                    payment_record['payer_id'] = payer_id
                    
                    # Enregistrer le paiement de la mise mensuelle
                    user_id = payment_record['user_id']
                    self.user_manager.register_monthly_payment(user_id)
                    
                    self._save_payments()
                    
                    return {
                        'success': True,
                        'message': 'Paiement confirmé et participation au concours activée'
                    }
            
            return {
                'success': False,
                'error': 'Échec de l\'exécution du paiement'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Erreur lors de l\'exécution: {str(e)}'
            }
    
    def send_prize_payment(self, user_id: int, amount: float, description: str) -> Dict[str, Any]:
        """Envoie un paiement de récompense à un utilisateur"""
        user = self.user_manager.get_user(user_id)
        if not user or not user.get('paypal_email'):
            return {
                'success': False,
                'error': 'Adresse PayPal non trouvée pour cet utilisateur'
            }
        
        try:
            # Simuler l'envoi de paiement pour le moment
            # En production, utiliser l'API PayPal Payouts
            payment_record = {
                'payment_id': f"PAYOUT_{user_id}_{int(datetime.now().timestamp())}",
                'user_id': user_id,
                'username': user['username'],
                'paypal_email': user['paypal_email'],
                'amount': amount,
                'currency': 'CHF',
                'status': 'sent',
                'type': 'prize',
                'description': description,
                'created_at': datetime.now().isoformat()
            }
            
            self.payments.append(payment_record)
            self._save_payments()
            
            return {
                'success': True,
                'message': f'Récompense de {amount} CHF envoyée à {user["paypal_email"]}'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Erreur lors de l\'envoi: {str(e)}'
            }
    
    def get_user_payments(self, user_id: int) -> List[Dict[str, Any]]:
        """Récupère l'historique des paiements d'un utilisateur"""
        return [p for p in self.payments if p['user_id'] == user_id]
    
    def get_monthly_revenue(self, month: int = None, year: int = None) -> float:
        """Calcule le revenu mensuel"""
        if month is None or year is None:
            now = datetime.now()
            month, year = now.month, now.year
        
        monthly_payments = []
        for payment in self.payments:
            if payment['status'] == 'completed' and payment['type'] == 'monthly_bet':
                payment_date = datetime.fromisoformat(payment['completed_at'])
                if payment_date.month == month and payment_date.year == year:
                    monthly_payments.append(payment)
        
        return sum(p['amount'] for p in monthly_payments)
    
    def process_monthly_prizes(self, leaderboard: List[Dict[str, Any]], prize_pool: float) -> List[Dict[str, Any]]:
        """Traite les paiements de récompenses mensuelles"""
        results = []
        
        prizes = {
            1: prize_pool * 0.40,  # 40% pour le 1er
            2: prize_pool * 0.15,  # 15% pour le 2e  
            3: prize_pool * 0.05   # 5% pour le 3e
        }
        
        for rank, player in enumerate(leaderboard[:3], 1):
            if rank in prizes:
                amount = prizes[rank]
                description = f"Récompense {rank}{'er' if rank == 1 else ('e' if rank == 2 else 'e')} place - Dino Challenge"
                
                result = self.send_prize_payment(
                    player['user_id'], 
                    amount, 
                    description
                )
                
                results.append({
                    'rank': rank,
                    'user_id': player['user_id'],
                    'username': player['username'],
                    'amount': amount,
                    'result': result
                })
        
        return results
