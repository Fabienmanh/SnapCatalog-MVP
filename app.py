import streamlit as st
import pandas as pd
from datetime import datetime
import io

# Configuration de la page
st.set_page_config(
    page_title="SnapCatalog MVP",
    page_icon="📸",
    layout="wide"
)

def main():
    st.title("📸 SnapCatalog MVP")
    st.markdown("### Générateur de catalogue simple")
    
    # Upload de fichier
    uploaded_file = st.file_uploader(
        "Choisissez votre fichier CSV", 
        type=['csv'],
        help="Uploadez votre fichier CSV avec colonnes : nom, prix, description"
    )
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success("✅ Fichier chargé avec succès!")
            
            # Affichage des données
            st.subheader("📊 Aperçu des données")
            st.dataframe(df.head(10))
            
            st.info(f"📈 Total : {len(df)} produits")
            
        except Exception as e:
            st.error(f"❌ Erreur : {str(e)}")
    else:
        st.info("👆 Uploadez un fichier CSV pour commencer")
        
        # Exemple de format
        st.subheader("📋 Format CSV attendu :")
        exemple = pd.DataFrame({
            'nom': ['Produit 1', 'Produit 2'],
            'prix': [19.99, 29.99],
            'description': ['Description 1', 'Description 2']
        })
        st.dataframe(exemple)

if __name__ == "__main__":
    main()
