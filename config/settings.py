# config/settings.py

# Configuration par défaut
DEFAULT_CONFIG = {
    'pdf': {
        'products_per_page': 4,
        'bg_color': "#F0F0F0",
        'primary_color': "#1976d2",
        'quality': 'hd'
    },
    'images': {
        'max_width': 800,
        'max_height': 600,
        'quality': 85
    },
    'colors': {
        'primary': "#1976d2",
        'secondary': "#f50057",
        'background': "#F0F0F0"
    }
}

def get_config():
    """Retourne la configuration par défaut"""
    return DEFAULT_CONFIG
