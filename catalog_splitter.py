# utils/catalog_splitter.py
"""
Utilitaire pour diviser un gros catalogue en plusieurs petits catalogues
pour éviter les problèmes de mémoire sur Streamlit Cloud
"""

import pandas as pd
from typing import List, Tuple
import math


def split_dataframe(df: pd.DataFrame, max_products_per_split: int = 150) -> List[pd.DataFrame]:
    """
    Divise un DataFrame en plusieurs DataFrames de taille maximale
    
    Args:
        df: DataFrame à diviser
        max_products_per_split: Nombre maximum de produits par split
        
    Returns:
        Liste de DataFrames
    """
    total_products = len(df)
    num_splits = math.ceil(total_products / max_products_per_split)
    
    splits = []
    for i in range(num_splits):
        start_idx = i * max_products_per_split
        end_idx = min((i + 1) * max_products_per_split, total_products)
        split_df = df.iloc[start_idx:end_idx].copy()
        splits.append(split_df)
    
    return splits


def get_split_info(total_products: int, max_per_split: int = 150) -> dict:
    """
    Calcule les informations de division d'un catalogue
    
    Args:
        total_products: Nombre total de produits
        max_per_split: Maximum de produits par split
        
    Returns:
        Dict avec les informations de division
    """
    num_splits = math.ceil(total_products / max_per_split)
    
    splits_info = []
    for i in range(num_splits):
        start_idx = i * max_per_split + 1  # +1 pour affichage (commence à 1)
        end_idx = min((i + 1) * max_per_split, total_products)
        num_products = end_idx - start_idx + 1
        
        splits_info.append({
            'split_num': i + 1,
            'start': start_idx,
            'end': end_idx,
            'count': num_products,
            'name': f"Catalogue_{i+1}_sur_{num_splits}.pdf"
        })
    
    return {
        'total_products': total_products,
        'num_splits': num_splits,
        'max_per_split': max_per_split,
        'splits': splits_info
    }


def recommend_split_strategy(total_products: int, is_cloud: bool = False) -> Tuple[bool, int, str]:
    """
    Recommande une stratégie de division basée sur le nombre de produits
    
    Args:
        total_products: Nombre total de produits
        is_cloud: True si sur Streamlit Cloud
        
    Returns:
        (should_split, max_per_split, message)
    """
    if is_cloud:
        if total_products <= 100:
            return False, total_products, "✅ Pas besoin de diviser (≤ 100 produits)"
        elif total_products <= 150:
            return False, total_products, "⚠️ À la limite, mais génération possible en une fois"
        elif total_products <= 300:
            return True, 150, f"🚨 Recommandé de diviser en {math.ceil(total_products/150)} catalogues de 150 produits max"
        else:
            return True, 150, f"🚨 Fortement recommandé de diviser en {math.ceil(total_products/150)} catalogues"
    else:
        # En local, plus de marge
        if total_products <= 500:
            return False, total_products, "✅ Génération possible en une fois (local)"
        else:
            return True, 250, f"💡 Suggestion de diviser en {math.ceil(total_products/250)} catalogues pour optimiser"
    
    return False, total_products, ""


def format_split_summary(split_info: dict) -> str:
    """
    Formate un résumé lisible de la division
    
    Args:
        split_info: Informations de division retournées par get_split_info
        
    Returns:
        String formatté pour affichage
    """
    summary = f"""
📊 **Plan de division du catalogue**

**Total de produits** : {split_info['total_products']}
**Nombre de catalogues** : {split_info['num_splits']}
**Produits par catalogue** : max {split_info['max_per_split']}

**Détail des catalogues :**
"""
    
    for split in split_info['splits']:
        summary += f"\n  {split['split_num']}. {split['name']}"
        summary += f"\n     → Produits {split['start']} à {split['end']} ({split['count']} produits)"
    
    return summary


# Exemple d'utilisation
if __name__ == "__main__":
    # Test avec 316 produits
    total = 316
    should_split, max_per, message = recommend_split_strategy(total, is_cloud=True)
    
    print(f"Total produits: {total}")
    print(f"Message: {message}")
    print(f"Diviser: {should_split}")
    print()
    
    if should_split:
        info = get_split_info(total, max_per)
        print(format_split_summary(info))

