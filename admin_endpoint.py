#!/usr/bin/env python3
"""
DINO CHALLENGE - Endpoint Admin pour voir les utilisateurs
Ajouter cette route à votre app.py sur Render
"""

@app.route('/admin/users')
def admin_users():
    """Endpoint admin pour voir tous les utilisateurs"""
    try:
        # Vérification simple (vous pouvez ajouter un token)
        admin_key = request.args.get('key')
        if admin_key != 'your_secret_admin_key':  # Changez ça !
            return jsonify({"error": "Accès refusé"}), 403
        
        db = DatabaseManager(DATABASE_URL)
        
        # Récupérer tous les utilisateurs
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_id, username, first_name, last_name,
                       registration_date, premium_status, total_games, high_score
                FROM users 
                ORDER BY registration_date DESC
            """)
            users = cursor.fetchall()
            
            # Statistiques
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as premium FROM users WHERE premium_status = true")
            premium_users = cursor.fetchone()['premium']
            
            # Formater pour JSON
            user_list = []
            for user in users:
                user_list.append({
                    'telegram_id': user['telegram_id'],
                    'username': user['username'],
                    'name': f"{user['first_name']} {user['last_name'] or ''}".strip(),
                    'registration_date': str(user['registration_date']),
                    'premium': user['premium_status'],
                    'games': user['total_games'],
                    'high_score': user['high_score']
                })
            
            return jsonify({
                'stats': {
                    'total_users': total_users,
                    'premium_users': premium_users
                },
                'users': user_list
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Usage: https://votre-app.onrender.com/admin/users?key=your_secret_admin_key