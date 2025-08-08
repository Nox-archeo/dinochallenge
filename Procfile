web: gunicorn wsgi:flask_app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
worker: python telegram_bot.py
worker: python bot.py
