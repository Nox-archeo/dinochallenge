#!/usr/bin/env python3
"""
WSGI Configuration pour production
"""
import os
from app import flask_app as application

# Alias pour Gunicorn
app = application

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    application.run(host='0.0.0.0', port=port)
