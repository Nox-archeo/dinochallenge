from datetime import datetime, timedelta
import calendar

def get_current_month():
    """Retourne le mois et l'année actuels"""
    now = datetime.now()
    return now.month, now.year

def get_month_start_end(month=None, year=None):
    """Retourne le début et la fin d'un mois donné"""
    if month is None or year is None:
        month, year = get_current_month()
    
    start = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59)
    
    return start, end

def is_same_day(date1, date2):
    """Vérifie si deux dates sont le même jour"""
    return date1.date() == date2.date()

def days_until_month_end():
    """Retourne le nombre de jours jusqu'à la fin du mois"""
    now = datetime.now()
    _, end = get_month_start_end()
    return (end - now).days

def format_date(date_obj):
    """Formate une date en string lisible"""
    return date_obj.strftime("%d/%m/%Y %H:%M")

def parse_date(date_string):
    """Parse une string en objet datetime"""
    return datetime.fromisoformat(date_string)
