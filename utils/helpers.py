# utils/helpers.py
import pandas as pd
import streamlit as st

def update_progress(current, total, stage_percent=None, status_text=""):
    """Met à jour une barre de progression Streamlit avec granularité détaillée"""
    if total > 0:
        # Calculer la progression en tenant compte du stage_percent
        if stage_percent is not None:
            # Si stage_percent est fourni, l'utiliser directement
            progress = float(stage_percent)
        else:
            # Sinon, calculer à partir de current/total
            progress = current / total
        
        # S'assurer que la progression reste entre 0.0 et 1.0
        progress = max(0.0, min(1.0, progress))
        
        # Mettre à jour la barre de progression
        if hasattr(st, 'session_state') and hasattr(st.session_state, 'progress_bar'):
            st.session_state.progress_bar.progress(progress)
        
        # Mettre à jour le texte de statut avec pourcentage détaillé
        if hasattr(st, 'session_state') and hasattr(st.session_state, 'status_text'):
            percentage = int(progress * 100)
            if status_text:
                st.session_state.status_text.text(f"{status_text} - {percentage}% ({current}/{total})")
            else:
                st.session_state.status_text.text(f"Progression: {percentage}% ({current}/{total})")
    
    return current

def update_progress_detailed(current, total, stage_percent=None, status_text=""):
    """Version améliorée qui coordonne avec les étapes manuelles de progression"""
    if total > 0:
        # La progression des produits doit être mappée sur la plage 25% à 95%
        # (car 0-25% est géré manuellement avant, et 95-100% après)
        base_progress = 0.25  # 25% de base (étapes manuelles)
        product_progress_range = 0.70  # 70% pour les produits (25% à 95%)
        
        if stage_percent is not None:
            # Si stage_percent est fourni, l'utiliser
            progress = float(stage_percent)
        else:
            # Calculer la progression relative des produits
            product_progress = current / total
            # Mapper sur la plage 25% à 95%
            progress = base_progress + (product_progress * product_progress_range)
        
        # S'assurer que la progression reste entre 0.0 et 1.0
        progress = max(0.0, min(1.0, progress))
        
        # Mettre à jour la barre de progression
        if hasattr(st, 'session_state') and hasattr(st.session_state, 'progress_bar'):
            st.session_state.progress_bar.progress(progress)
        
        # Mettre à jour le texte de statut avec pourcentage détaillé
        if hasattr(st, 'session_state') and hasattr(st.session_state, 'status_text'):
            percentage = int(progress * 100)
            if status_text:
                st.session_state.status_text.text(f"{status_text} - {percentage}% ({current}/{total})")
            else:
                st.session_state.status_text.text(f"Génération des produits: {percentage}% ({current}/{total})")
    
    return current

def format_price(price):
    """Formate un prix"""
    try:
        return f"{float(price):.2f} €"
    except:
        return "N/A"

def clean_text(text):
    """Nettoie un texte pour l'affichage"""
    if pd.isna(text):
        return ""
    return str(text).strip()
