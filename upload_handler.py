# upload_handler.py
import streamlit as st
import pandas as pd
import os
from pathlib import Path
from utils.data_processing import detect_csv_type

class UploadHandler:
    """Gestionnaire des uploads et validation des fichiers"""
    
    @staticmethod
    def handle_file_upload():
        """Gère l'upload du fichier CSV"""
        uploaded_file = st.file_uploader(
            "Choisissez un fichier CSV (Etsy ou Shopify)", 
            type=["csv"]
        )
        return uploaded_file
    
    @staticmethod
    def validate_csv_file(uploaded_file):
        """Valide et charge le fichier CSV avec gestion intelligente des délimiteurs"""
        if uploaded_file is None:
            return None, None
            
        try:
            # D'abord, essayer la détection automatique de pandas
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, engine='python')
            
            if len(df) > 0 and len(df.columns) > 1:
                csv_type = detect_csv_type(df)
                st.success("✅ Fichier CSV lu avec succès (détection automatique)")
                st.info(f"📊 {len(df)} lignes, {len(df.columns)} colonnes détectées")
                return df, csv_type
                
        except Exception as e:
            st.warning(f"⚠️ Détection automatique échouée: {e}")
            st.info("🔄 Tentative avec délimiteurs spécifiques...")
        
        # Si la détection automatique échoue, essayer des délimiteurs spécifiques
        delimiters = [',', ';', '\t', '|', ':', ' ']
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            for delimiter in delimiters:
                try:
                    uploaded_file.seek(0)
                    
                    # Essayer avec le délimiteur actuel
                    df = pd.read_csv(
                        uploaded_file,
                        delimiter=delimiter,
                        encoding=encoding,
                        on_bad_lines='skip',
                        low_memory=False,
                        engine='python'
                    )
                    
                    if len(df) > 0 and len(df.columns) > 1:
                        csv_type = detect_csv_type(df)
                        st.success(f"✅ Fichier CSV lu avec succès ! Délimiteur: '{delimiter}', Encodage: {encoding}")
                        st.info(f"📊 {len(df)} lignes, {len(df.columns)} colonnes détectées")
                        return df, csv_type
                        
                except Exception as e:
                    continue
        
        # Dernière tentative : lecture brute et analyse manuelle
        try:
            uploaded_file.seek(0)
            content = uploaded_file.read().decode('utf-8', errors='ignore')
            lines = content.split('\n')
            
            if len(lines) > 1:
                # Analyser les premières lignes pour détecter le délimiteur
                first_line = lines[0]
                second_line = lines[1] if len(lines) > 1 else ""
                
                # Compter les occurrences de différents caractères
                char_counts = {}
                for char in [',', ';', '\t', '|', ':']:
                    char_counts[char] = first_line.count(char)
                
                # Trouver le délimiteur le plus fréquent
                if any(char_counts.values()):
                    best_delimiter = max(char_counts, key=char_counts.get)
                    
                    # Essayer de lire avec ce délimiteur
                    uploaded_file.seek(0)
                    df = pd.read_csv(
                        uploaded_file,
                        delimiter=best_delimiter,
                        encoding='utf-8',
                        on_bad_lines='skip',
                        engine='python'
                    )
                    
                    if len(df) > 0 and len(df.columns) > 1:
                        csv_type = detect_csv_type(df)
                        st.success(f"✅ Fichier CSV lu avec analyse manuelle ! Délimiteur: '{best_delimiter}'")
                        st.info(f"📊 {len(df)} lignes, {len(df.columns)} colonnes détectées")
                        return df, csv_type
                        
        except Exception as e:
            st.error(f"❌ Analyse manuelle échouée: {e}")
        
        # Si rien ne fonctionne
        st.error("❌ Impossible de lire le fichier CSV. Vérifiez le format.")
        st.error("💡 Conseils: Assurez-vous que le fichier est bien un CSV avec des colonnes séparées par des virgules, points-virgules, ou tabulations.")
        
        # Afficher un aperçu du contenu pour debug
        try:
            uploaded_file.seek(0)
            preview = uploaded_file.read(500).decode('utf-8', errors='ignore')
            st.code(f"Aperçu du fichier:\n{preview}")
        except:
            pass
            
        return None, None
    
    @staticmethod
    def validate_image_path(path_or_url):
        """Valide si un chemin/URL d'image est valide"""
        if pd.isna(path_or_url) or not str(path_or_url).strip():
            return False
            
        path_or_url = str(path_or_url)
        
        # URL HTTP
        if path_or_url.lower().startswith("http"):
            return True
            
        # Fichier local
        return os.path.isfile(path_or_url)

# Dans upload_handler.py, ajoutez cette méthode à la classe :

@staticmethod
def get_image_stats(df, image_column):
    """Analyse les statistiques des images dans le DataFrame"""
    stats = {
        'total': len(df),
        'with_images': 0,
        'without_images': 0,
        'invalid_paths': []
    }
    
    for idx, path in df[image_column].items():
        if UploadHandler.validate_image_path(path):
            stats['with_images'] += 1
        else:
            stats['without_images'] += 1
            if pd.notna(path):
                stats['invalid_paths'].append(f"Ligne {idx+2}: {path}")
    
    return stats
