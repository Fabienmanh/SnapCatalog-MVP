import streamlit as st
import pandas as pd
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Configuration de la page
st.set_page_config(
    page_title="SnapCatalog MVP",
    page_icon="📸",
    layout="wide"
)

def create_pdf_catalog(df):
    """Génère un PDF simple à partir du DataFrame"""
    buffer = io.BytesIO()
    
    # Création du document
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        spaceAfter=30,
        textColor=HexColor('#2E86AB')
    )
    title = Paragraph("📸 Mon Catalogue Produits", title_style)
    elements.append(title)
    
    # Date
    date_str = f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    date_para = Paragraph(date_str, styles['Normal'])
    elements.append(date_para)
    elements.append(Spacer(1, 20))
    
    # Conversion DataFrame en liste pour le tableau
    data = [df.columns.tolist()]  # En-têtes
    for _, row in df.iterrows():
        data.append(row.tolist())
    
    # Création du tableau
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E86AB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#FFFFFF')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#DEE2E6'))
    ]))
    
    elements.append(table)
    
    # Stats
    elements.append(Spacer(1, 30))
    stats = Paragraph(f"<b>Total produits :</b> {len(df)}", styles['Normal'])
    elements.append(stats)
    
    # Génération du PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

def main():
    st.title("📸 SnapCatalog MVP")
    st.markdown("---")
    
    # Upload du fichier
    uploaded_file = st.file_uploader(
        "📤 Choisissez votre fichier CSV",
        type=['csv'],
        help="Uploadez un fichier CSV avec vos produits"
    )
    
    if uploaded_file is not None:
        try:
            # Lecture du CSV
            df = pd.read_csv(uploaded_file)
            
            st.success(f"✅ Fichier chargé avec succès ! ({len(df)} lignes)")
            st.dataframe(df.head())
            
            # Bouton génération PDF
            if st.button("📄 Générer PDF Catalogue", type="primary"):
                with st.spinner("Génération du PDF en cours..."):
                    try:
                        pdf_buffer = create_pdf_catalog(df)
                        
                        st.success("🎉 PDF généré avec succès !")
                        
                        # Bouton de téléchargement
                        st.download_button(
                            label="⬇️ Télécharger le PDF",
                            data=pdf_buffer,
                            file_name=f"catalogue_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            mime="application/pdf"
                        )
                        
                    except Exception as e:
                        st.error(f"❌ Erreur lors de la génération PDF : {str(e)}")
            
        except Exception as e:
            st.error(f"❌ Erreur lors de la lecture du fichier : {str(e)}")
    
    else:
        st.info("👆 Uploadez un fichier CSV pour commencer")
        
        # Exemple de format
        with st.expander("📋 Voir un exemple de format CSV"):
            st.subheader("📋 Format CSV attendu :")
            exemple = pd.DataFrame({
                'nom': ['Produit 1', 'Produit 2'],
                'prix': [19.99, 29.99],
                'description': ['Description 1', 'Description 2']
            })
            st.dataframe(exemple)

if __name__ == "__main__":
    main()
