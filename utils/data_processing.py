# utils/data_processing.py
import pandas as pd
import streamlit as st
import sqlite3
import os
from datetime import datetime

def detect_csv_type(df):
    """Détecte si le CSV provient d'Etsy ou Shopify basé sur les colonnes"""
    if df is None or df.empty:
        return "unknown"
    
    columns = [col.lower() for col in df.columns]
    
    # Détection Etsy
    etsy_indicators = ['listing_id', 'title', 'price', 'currency', 'quantity', 'state']
    if any(indicator in columns for indicator in etsy_indicators):
        return "etsy"
    
    # Détection Shopify
    shopify_indicators = ['handle', 'title', 'vendor', 'product_type', 'tags', 'published']
    if any(indicator in columns for indicator in shopify_indicators):
        return "shopify"
    
    return "unknown"

def save_feedback_to_csv(feedback_data, filename="feedback_snapcatalog.csv"):
    """Sauvegarde le feedback dans un fichier CSV"""
    try:
        df = pd.DataFrame([feedback_data])
        
        # Ajouter l'horodatage
        df['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Créer le fichier s'il n'existe pas, sinon ajouter
        if os.path.exists(filename):
            df.to_csv(filename, mode='a', header=False, index=False)
        else:
            df.to_csv(filename, index=False)
            
        return True, "Feedback sauvegardé avec succès"
    except Exception as e:
        return False, f"Erreur lors de la sauvegarde : {str(e)}"

def save_feedback_to_sqlite(feedback_data, db_path="utils/snapcatalog_feedback.db"):
    """Sauvegarde le feedback dans une base SQLite"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Créer la table si elle n'existe pas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rating INTEGER,
                comment TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insérer le feedback
        cursor.execute('''
            INSERT INTO feedback (rating, comment)
            VALUES (?, ?)
        ''', (feedback_data.get('rating'), feedback_data.get('comment')))
        
        conn.commit()
        conn.close()
        
        return True, "Feedback sauvegardé en base de données"
    except Exception as e:
        return False, f"Erreur lors de la sauvegarde en base : {str(e)}"

def get_feedback_stats(db_path="utils/snapcatalog_feedback.db"):
    """Récupère les statistiques des feedbacks"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Vérifier si la table existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
        if not cursor.fetchone():
            conn.close()
            return {"total": 0, "average_rating": 0, "ratings": {}}
        
        # Statistiques générales
        cursor.execute("SELECT COUNT(*) FROM feedback")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(rating) FROM feedback")
        avg_rating = cursor.fetchone()[0] or 0
        
        # Distribution des notes
        cursor.execute("SELECT rating, COUNT(*) FROM feedback GROUP BY rating ORDER BY rating")
        ratings_dist = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            "total": total,
            "average_rating": round(avg_rating, 1),
            "ratings": ratings_dist
        }
    except Exception as e:
        return {"error": str(e)}
