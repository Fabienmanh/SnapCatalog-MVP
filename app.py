import io
from datetime import datetime

import pandas as pd
import streamlit as st
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch  # (optionnel si tu veux des espacements en pouces)
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Configuration de la page
st.set_page_config(
    page_title="SnapCatalog MVP",
    page_icon="📸",
    layout="wide",
)


def create_pdf_catalog(df: pd.DataFrame) -> io.BytesIO:
    """Génère un PDF simple à partir du DataFrame."""
    # Convertir en chaînes pour éviter les objets non sérialisables dans le tableau
    df_for_pdf = df.astype(str)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    # Titre
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=24,
        spaceAfter=30,
        textColor=HexColor("#2E86AB"),
    )
    title = Paragraph("📸 Mon Catalogue Produits", title_style)
    elements.append(title)

    # Date
    date_str = f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    date_para = Paragraph(date_str, styles["Normal"])
    elements.append(date_para)
    elements.append(Spacer(1, 20))

    # Conversion DataFrame en liste pour le tableau
    data = [list(df_for_pdf.columns)]  # En-têtes
    for _, row in df_for_pdf.iterrows():
        data.append(list(row.values))

    # Tableau
    table = Table(data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2E86AB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), HexColor("#F8F9FA")),
                ("GRID", (0, 0), (-1, -1), 1, HexColor("#DEE2E6")),
            ]
        )
    )
    elements.append(table)

    # Stats
    elements.append(Spacer(1, 30))
    stats = Paragraph(f"<b>Total produits :</b> {len(df)}", styles["Normal"])
    elements.append(stats)

    # Génération du PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def main():
    st.title("📸 SnapCatalog MVP")
    st.markdown("---")

    uploaded_file = st.file_uploader(
        "📤 Choisissez votre fichier CSV",
        type=["csv"],
        help="Uploadez un fichier CSV avec vos produits",
    )

    if uploaded_file is not None:
        try:
            # Lecture du CSV (séparateur auto simple: essaie virgule puis point-virgule)
            try:
                df = pd.read_csv(uploaded_file)
            except Exception:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=";")

            st.success(f"✅ Fichier chargé avec succès ! ({len(df)} lignes)")
            st.dataframe(df.head())

            if st.button("📄 Générer PDF Catalogue", type="primary"):
                with st.spinner("Génération du PDF en cours..."):
                    pdf_buffer = create_pdf_catalog(df)
                    st.success("🎉 PDF généré avec succès !")
                    st.download_button(
                        label="⬇️ Télécharger le PDF",
                        data=pdf_buffer,  # BytesIO accepté par Streamlit
                        file_name=f"catalogue_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                    )
        except Exception as e:
            st.error(f"❌ Erreur lors du traitement: {e}")
    else:
        st.info("👆 Uploadez un fichier CSV pour commencer")
        with st.expander("📋 Voir un exemple de format CSV"):
            st.subheader("📋 Format CSV attendu :")
            exemple = pd.DataFrame(
                {
                    "nom": ["Produit 1", "Produit 2"],
                    "prix": [19.99, 29.99],
                    "description": ["Description 1", "Description 2"],
                }
            )
            st.dataframe(exemple)


if __name__ == "__main__":
    main()
