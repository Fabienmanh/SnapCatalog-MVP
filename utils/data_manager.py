# utils/data_manager.py
import pandas as pd
import streamlit as st
from io import BytesIO

def load_data_from_file(uploaded_file):
    """Charge les données depuis un fichier uploadé"""
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, encoding='utf-8')
        elif uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            return None, "Format de fichier non supporté"
        return df, None
    except Exception as e:
        return None, f"Erreur lors du chargement: {str(e)}"

def validate_dataframe(df):
    """Valide les données du DataFrame"""
    if df is None or df.empty:
        return False, "Le fichier est vide"
    
    required_columns = ['nom', 'prix']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        return False, f"Colonnes manquantes : {', '.join(missing_columns)}"
    
    return True, "Données valides"

def clean_dataframe(df):
    """Nettoie le DataFrame"""
    df = df.dropna(how='all')
    text_columns = df.select_dtypes(include=['object']).columns
    df[text_columns] = df[text_columns].fillna('')
    return df

def get_available_columns(df):
    """Retourne la liste des colonnes disponibles"""
    return list(df.columns) if df is not None else []

def filter_dataframe(df, filters=None):
    """Applique des filtres au DataFrame"""
    if filters is None or df is None:
        return df
    
    filtered_df = df.copy()
    for column, value in filters.items():
        if value and column in filtered_df.columns:
            if isinstance(value, str):
                filtered_df = filtered_df[filtered_df[column].str.contains(value, case=False, na=False)]
            else:
                filtered_df = filtered_df[filtered_df[column] == value]
    
    return filtered_df

def export_to_excel(df):
    """Exporte le DataFrame vers Excel"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Catalogue', index=False)
    return output.getvalue()
