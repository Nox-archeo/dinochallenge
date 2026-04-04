#!/usr/bin/env python3
"""
DINO CHALLENGE - Configuration Database URL
Script pour tester la connexion à la base PostgreSQL sur Render
"""

import os

def check_database_config():
    """Vérifier la configuration de la base de données"""
    print("🔍 VÉRIFICATION CONFIGURATION DATABASE:")
    print("=" * 50)
    
    # Variables possibles sur Render
    possible_vars = [
        'DATABASE_URL',
        'POSTGRES_URL', 
        'POSTGRESQL_URL',
        'DB_URL',
        'NEON_DATABASE_URL',
        'SUPABASE_DB_URL'
    ]
    
    found_vars = []
    for var in possible_vars:
        value = os.environ.get(var)
        if value:
            found_vars.append((var, value))
            # Masquer le mot de passe pour l'affichage
            masked_url = mask_password(value)
            print(f"✅ {var}: {masked_url}")
    
    if not found_vars:
        print("❌ Aucune variable DATABASE_URL trouvée")
        print("💡 Variables d'environnement disponibles:")
        env_vars = [k for k in os.environ.keys() if 'DB' in k.upper() or 'DATABASE' in k.upper() or 'POSTGRES' in k.upper()]
        for var in env_vars:
            print(f"   - {var}")
    
    return found_vars

def mask_password(url):
    """Masquer le mot de passe dans l'URL pour l'affichage"""
    if '://' in url and '@' in url:
        parts = url.split('://')
        if len(parts) == 2:
            scheme = parts[0]
            rest = parts[1]
            if '@' in rest:
                user_pass, host_db = rest.split('@', 1)
                if ':' in user_pass:
                    user, password = user_pass.split(':', 1)
                    masked = f"{scheme}://{user}:***@{host_db}"
                    return masked
    return url

def create_env_template():
    """Créer un template .env avec les instructions"""
    template = """# DINO CHALLENGE - Configuration Base de Données
# Copiez votre DATABASE_URL depuis Render ici

# Format PostgreSQL:
# DATABASE_URL=postgresql://username:password@host:5432/database?sslmode=require

# Votre URL (remplacez par la vraie URL depuis Render):
DATABASE_URL=postgresql://user:password@host:5432/database
"""
    
    try:
        with open('.env.template', 'w') as f:
            f.write(template)
        print("📝 Fichier .env.template créé")
    except Exception as e:
        print(f"❌ Erreur création template: {e}")

if __name__ == "__main__":
    found_vars = check_database_config()
    
    if not found_vars:
        print("\n💡 INSTRUCTIONS POUR RÉCUPÉRER VOTRE DATABASE_URL:")
        print("1. Allez sur https://render.com")
        print("2. Sélectionnez votre service Dino Challenge")
        print("3. Onglet 'Environment'")
        print("4. Copiez la valeur de DATABASE_URL")
        print("5. Exportez-la localement:")
        print("   export DATABASE_URL='votre_url_ici'")
        
        create_env_template()
    else:
        print(f"\n✅ {len(found_vars)} variable(s) de base trouvée(s)")
        print("🚀 Vous pouvez utiliser le script view_users.py")