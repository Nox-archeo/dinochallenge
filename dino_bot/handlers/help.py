from telegram import Update
from telegram.ext import ContextTypes

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour l'aide et les règles"""
    
    help_message = """
ℹ️ **Aide et Règles - Dino Challenge**

🎯 **Concept :**
Concours mensuel basé sur le jeu Chrome Dino Runner. Battez les autres joueurs pour remporter des récompenses en CHF !

� **Pari mensuel :**
• Coût : 10 CHF par mois (OPTIONNEL)
• Paiement via PayPal (CB acceptée)
• Participez seulement si vous le souhaitez

🎮 **Règles de jeu :**
• Maximum 5 tentatives par jour
• Score basé sur votre meilleur résultat du mois
• Soumission manuelle du score après chaque partie
• Un seul compte par participant

⚙️ **Configuration simple :**
• **Nom :** Tapez juste votre nom → Configuration automatique
• **Email PayPal :** Tapez juste votre email → Configuration automatique
• Exemple : `john.doe@gmail.com` 

🏆 **Récompenses mensuelles :**
• 🥇 1er place : 40% de la cagnotte
• 🥈 2e place : 15% de la cagnotte
• 🥉 3e place : 5% de la cagnotte
• Le reste revient à l'organisateur

💰 **Paiements des gains :**
• L'organisateur envoie manuellement les gains PayPal
• Configurez votre email PayPal dans votre profil
• Gains distribués le 1er du mois suivant
• Notification automatique des gagnants

⚠️ **Règles anti-triche :**
• Un seul compte Telegram par personne
• Scores validés et horodatés
• Pas de modification possible des scores
• Limite stricte de 5 tentatives par jour

🎯 **Comment commencer :**
1. Tapez votre nom pour vous identifier
2. Tapez votre email PayPal pour recevoir vos gains
3. Utilisez le menu pour jouer et suivre votre progression
4. Pariez 10 CHF pour participer aux récompenses (optionnel)
• `/help` - Cette aide

🔧 **Support :**
En cas de problème, contactez l'organisateur.

**Bonne chance ! 🦕**
"""
    
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler spécifique pour les règles détaillées"""
    
    rules_message = """
📋 **Règlement détaillé - Dino Challenge**

**Article 1 - Participation**
• Ouvert à tous les utilisateurs Telegram
• Un seul compte par personne
• Abonnement mensuel obligatoire (10 CHF)

**Article 2 - Jeu**
• Jeu : Chrome Dino Runner hébergé sur GitHub Pages
• 5 tentatives maximum par jour (00h00-23h59 CET)
• Soumission manuelle obligatoire : `/score XXXX`
• Classement basé sur le meilleur score mensuel

**Article 3 - Classement**
• Remise à zéro chaque 1er du mois
• Seul le meilleur score compte (pas la moyenne)
• Égalité départagée par la date du score

**Article 4 - Récompenses**
• 1er : 40% de la cagnotte mensuelle
• 2e : 15% de la cagnotte mensuelle  
• 3e : 5% de la cagnotte mensuelle
• Organisme : 40% (frais, développement, maintenance)

**Article 5 - Paiements**
• Versement via PayPal uniquement
• Adresse PayPal obligatoire dans le profil
• Paiement dans les 7 jours suivant la fin du mois
• Gains non réclamés = forfaits après 30 jours

**Article 6 - Anti-triche**
• Modification de score = exclusion définitive
• Tentatives supplémentaires = score annulé
• Comptes multiples = bannissement

**Article 7 - Technique**
• Disponibilité du jeu non garantie 24h/24
• Problèmes techniques = prolongation possible
• Données sauvegardées automatiquement

**Article 8 - Réclamations**
• Délai : 48h après la fin du mois
• Contact via le support du bot
• Décision de l'organisateur finale

En participant, vous acceptez ce règlement.
"""
    
    await update.message.reply_text(rules_message, parse_mode='Markdown')

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour les informations de contact"""
    
    contact_message = """
📞 **Support et Contact**

🤖 **Bot Dino Challenge**
Version 1.0 - Développé avec ❤️

📧 **Support technique :**
Pour toute question ou problème :
• Problèmes de paiement
• Scores non enregistrés
• Bugs du jeu
• Questions sur les récompenses

🔒 **Sécurité et confidentialité :**
• Vos données sont stockées localement
• Paiements sécurisés via PayPal
• Aucune donnée partagée avec des tiers

⏰ **Délais de réponse :**
• Questions techniques : 24-48h
• Problèmes de paiement : 2-5 jours ouvrés
• Réclamations : Sous 48h

🆘 **Urgences :**
En cas de problème critique pendant un concours, contactez immédiatement le support.

**Merci de votre confiance ! 🦕**
"""
    
    await update.message.reply_text(contact_message, parse_mode='Markdown')
