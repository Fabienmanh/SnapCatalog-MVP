# utils/font_manager.py
import os
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import streamlit as st

def download_and_register_fonts():
    """Enregistre les polices système et retourne le mapping des polices disponibles"""
    
    try:
        # Essayer d'enregistrer les polices système
        system_fonts = {
            "Helvetica": ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Helvetica.dfont"],
            "Courier": ["/System/Library/Fonts/Courier.ttc", "/System/Library/Fonts/Courier New.ttf", "/System/Library/Fonts/Courier.dfont"],
            "Times": ["/System/Library/Fonts/Times.ttc", "/System/Library/Fonts/Times New Roman.ttf", "/System/Library/Fonts/Times.dfont"]
        }
        
        registered_fonts = {}
        
        for font_name, font_paths in system_fonts.items():
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        # Enregistrer la police
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        registered_fonts[font_name] = font_name
                        print(f"✅ Police {font_name} enregistrée depuis {font_path}")
                        break
                    except Exception as e:
                        print(f"⚠️ Impossible d'enregistrer {font_name} depuis {font_path}: {e}")
                        continue
                else:
                    print(f"⚠️ Fichier de police non trouvé: {font_path}")
        
        # Si aucune police système n'est enregistrée, utiliser les polices intégrées
        if not registered_fonts:
            print("ℹ️ Utilisation des polices intégrées ReportLab")
            return {
                "Helvetica": "Helvetica",
                "Courier": "Courier", 
                "Times": "Times-Roman"
            }
        
        return registered_fonts
        
    except Exception as e:
        print(f"⚠️ Erreur lors de l'enregistrement des polices: {e}")
        print("ℹ️ Utilisation des polices intégrées ReportLab")
        return {
            "Helvetica": "Helvetica",
            "Courier": "Courier", 
            "Times": "Times-Roman"
        }

def get_font_name(police_choice, bold=False):
    """Convertit le choix de police en nom de police ReportLab"""
    # Mapping des polices avec leurs noms ReportLab (polices intégrées)
    font_mapping = {
        "Helvetica": "Helvetica",
        "Courier": "Courier", 
        "Times": "Times-Roman"
    }
    
    font_name = font_mapping.get(police_choice, "Helvetica")

    if bold:
        # Gestion des variantes en gras pour chaque police
        bold_mapping = {
            "Helvetica": "Helvetica-Bold",
            "Courier": "Courier-Bold", 
            "Times": "Times-Bold"
        }
        return bold_mapping.get(police_choice, "Helvetica-Bold")
    else:
        return font_name

def validate_background_color(color_hex):
    """Valide et ajuste la couleur de fond pour maintenir la lisibilité (max 10% d'opacité)"""
    # Convertir hex en RGB
    color_hex = color_hex.lstrip('#')
    r = int(color_hex[0:2], 16)
    g = int(color_hex[2:4], 16)
    b = int(color_hex[4:6], 16)
    
    # Calculer la luminosité relative (formule standard)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    
    # Si la couleur est trop sombre (luminance < 0.9), ajuster vers une couleur plus claire
    if luminance < 0.9:
        # Ajuster vers une couleur plus claire (max 10% d'opacité)
        adjusted_r = min(255, int(r + (255 - r) * 0.9))
        adjusted_g = min(255, int(g + (255 - g) * 0.9))
        adjusted_b = min(255, int(b + (255 - b) * 0.9))
        
        # Convertir back en hex
        adjusted_hex = f"#{adjusted_r:02x}{adjusted_g:02x}{adjusted_b:02x}"
        return adjusted_hex, True
    else:
        # Toujours retourner avec le #
        return f"#{color_hex}", False