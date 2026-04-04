#!/usr/bin/env python3
"""
DINO CHALLENGE - Explorateur de structure DB
Script pour découvrir la structure de votre base PostgreSQL
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

def connect_to_db():
    """Se connecter à la base PostgreSQL"""
    try:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            print("❌ DATABASE_URL non définie")
            return None
            
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        print("✅ Connexion à PostgreSQL réussie!")
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return None

def explore_database(conn):
    """Explorer la structure de la base"""
    try:
        cursor = conn.cursor()
        
        print("\n🔍 EXPLORATION DE LA BASE DE DONNÉES:")
        print("=" * 60)
        
        # 1. Lister toutes les tables
        cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        print(f"\n📋 TABLES TROUVÉES ({len(tables)}):")
        for table in tables:
            print(f"   - {table['table_name']}")
        
        # 2. Explorer chaque table
        for table in tables:
            table_name = table['table_name']
            print(f"\n📊 TABLE: {table_name}")
            print("-" * 40)
            
            # Structure des colonnes
            cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position;
            """, (table_name,))
            columns = cursor.fetchall()
            
            print("   Colonnes:")
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"     - {col['column_name']}: {col['data_type']} ({nullable})")
            
            # Compter les enregistrements
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name};")
            count = cursor.fetchone()['count']
            print(f"   📈 Nombre d'enregistrements: {count}")
            
            # Si c'est une table users, montrer quelques exemples
            if table_name.lower() == 'users' and count > 0:
                print("\n   📝 EXEMPLES D'UTILISATEURS (3 premiers):")
                try:
                    cursor.execute(f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT 3;" if 'created_at' in [c['column_name'] for c in columns] 
                                 else f"SELECT * FROM {table_name} LIMIT 3;")
                    examples = cursor.fetchall()
                    for i, example in enumerate(examples, 1):
                        print(f"\n     Utilisateur {i}:")
                        for key, value in example.items():
                            if key.lower() in ['password', 'token', 'secret']:
                                value = "***masqué***"
                            print(f"       {key}: {value}")
                except Exception as e:
                    print(f"       ❌ Erreur lecture exemples: {e}")
    
    except Exception as e:
        print(f"❌ Erreur exploration: {e}")

def main():
    """Fonction principale"""
    print("🔍 DINO CHALLENGE - Explorateur de Base de Données")
    print("=" * 55)
    
    conn = connect_to_db()
    if not conn:
        return
    
    try:
        explore_database(conn)
    except Exception as e:
        print(f"❌ Erreur: {e}")
    finally:
        conn.close()
        print(f"\n✅ Connexion fermée")

if __name__ == "__main__":
    main()