# utils/image_processing.py
from PIL import Image as PILImage
import streamlit as st
from pathlib import Path
import pandas as pd
import tempfile  # ← AJOUTEZ
import os        # ← AJOUTEZ

def open_image(image_path):
    """Ouvre une image avec PIL"""
    try:
        return PILImage.open(image_path)
    except Exception as e:
        st.error(f"Erreur ouverture image {image_path}: {e}")
        return None

def get_image_info(image_path):
    """Récupère infos d'une image"""
    img = open_image(image_path)
    if img:
        return {
            'size': img.size,
            'mode': img.mode,
            'format': img.format
        }
    return None

def get_hex_color_safe(col):
    """Retourne une couleur hexadécimale sécurisée."""
    if col is None:
        return "#FFFFFF"
    col = str(col).strip()
    if col.startswith('#'):
        return col
    else:
        return f"#{col}"

        # Ajoutez cette fonction à la fin de votre image_processing.py
def get_image(path_or_url, max_width_cm, max_height_cm, centered=False):
    if pd.isna(path_or_url) or not str(path_or_url).strip():
        return None
    path_or_url = str(path_or_url)
    if path_or_url.lower().startswith("http"):
        import urllib.request
        temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        try:
            urllib.request.urlretrieve(path_or_url, temp_img.name)
            path = temp_img.name
        except Exception:
            return None
    elif os.path.isfile(path_or_url):
        path = path_or_url
    else:
        return None
    # ... reste du code
def process_images(df):
    """Traite les images depuis les URLs ou fichiers locaux"""
    images = []
    for idx, row in df.iterrows():
        # Utilise votre fonction get_image existante
        img_path = row.get('image_path', '') or row.get('Image', '')
        img = get_image(img_path, 5, 5)  # 5cm max
        images.append(img)
    return images