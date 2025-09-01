import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pathlib import Path
import tempfile
from io import BytesIO

# Imports des modules utilitaires
from utils.font_manager import download_and_register_fonts, validate_background_color
from utils.helpers import update_progress_detailed
from utils.image_processing import open_image
from utils.data_processing import save_feedback_to_csv, save_feedback_to_sqlite

# Import du générateur PDF (un seul module)
from pdf_designer import generate_pdf_with_quality

# Import de l'upload handler
from upload_handler import UploadHandler

# Gestion des erreurs de mise en page ReportLab
from reportlab.platypus.doctemplate import LayoutError

# Optionnel: aperçu PDF
try:
    from pdf2image import convert_from_path
    HAVE_PDF2IMAGE = True
except Exception:
    HAVE_PDF2IMAGE = False

# Fonction de génération sécurisée avec fallback automatique
def safe_generate_pdf(products, **kw):
    """Génère le PDF avec gestion automatique des erreurs de mise en page"""
    try:
        return generate_pdf_with_quality(products, **kw)
    except LayoutError as e:
        st.warning("⚠️ Le contenu déborde. Nouvelle tentative en mode sécurisé (paysage + troncature renforcée).")
        
        # 1) Passage en mode paysage avec moins de produits par page
        kw2 = {**kw, "products_per_page": max(2, kw.get("products_per_page", 4))}
        
        # 2) Troncature plus agressive des textes
        products2 = []
        for p in products:
            p2 = {}
            for k, v in p.items():
                if isinstance(v, str):
                    # Troncature à 400 caractères pour le mode sécurisé
                    if len(v) > 400:
                        p2[k] = v[:397] + "..."
                    else:
                        p2[k] = v
                else:
                    p2[k] = v
            products2.append(p2)
        
        # 3) Nouvelle tentative avec les paramètres sécurisés
        try:
            return generate_pdf_with_quality(products2, **kw2)
        except LayoutError as e2:
            st.error(f"❌ Impossible de générer le PDF même en mode sécurisé : {e2}")
            st.info("💡 Essayez de réduire le nombre de colonnes ou de produits par page.")
            raise e2

# État initial pour éviter la double génération
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None
    st.session_state.pdf_name = "catalogue_personnalise.pdf"
if "pdf_tmp_path" not in st.session_state:
    st.session_state.pdf_tmp_path = None

st.set_page_config(page_title="SnapCatalog, votre catalogue en un clin d'oeil", layout="wide")
st.title("📒 SnapCatalog — Générateur de PDF produits")
st.write("Importe ton fichier produits (Shopify, Etsy…), sélectionne tes colonnes, choisis un template et génère ton catalogue au format PDF!")

# NOUVEAU : Section de personnalisation (placée tôt pour qu'elle s'affiche toujours)
st.subheader("🎨 Personnalisation du PDF")

bg_color = st.color_picker("Choisis la couleur de fond des pages (max 10% d'opacité pour la lisibilité)", "#F0F0F0")

# Validation de la couleur de fond pour maintenir la lisibilité
validated_color, was_adjusted = validate_background_color(bg_color)

if was_adjusted:
    st.warning(f"⚠️ La couleur a été ajustée pour maintenir la lisibilité : {validated_color}")
    st.info("💡 Les couleurs trop sombres sont automatiquement éclaircies pour garantir une lecture confortable.")

# Utiliser la couleur validée
bg_color = validated_color

# 1. Import du fichier CSV de produits
uploaded_file = UploadHandler.handle_file_upload()

if uploaded_file is not None:
    df, csv_type = UploadHandler.validate_csv_file(uploaded_file)
    
    if df is not None and csv_type:
        # --- Détection automatique des colonnes "utiles" ---
        auto_columns = []
        for name in ["title", "titre", "description", "desc", "price", "prix", "image 1", "image", "photo", "sku", "référence", "ref", "code devise", "devise", "quantité", "quantite", "qte", "matériaux", "materiaux", "material"]:
            auto_columns += [c for c in df.columns if name in c.lower()]
        auto_columns = list(dict.fromkeys(auto_columns))

        # 3. Sélection des colonnes à inclure dans le PDF
        st.subheader("Colonnes à inclure dans le PDF")
        st.info("ℹ️ Pour une meilleure lisibilité, **seule la première image** (\"Image 1\") de chaque produit sera utilisée dans le catalogue PDF. Les autres images sont ignorées.")
        choix_cols = st.multiselect(
            "Choisis les colonnes (pré-sélection automatique si détectées) :",
            options=list(df.columns),
            default=auto_columns
        )
        if not choix_cols:
            st.warning("Merci de sélectionner au moins une colonne.")
            st.stop()
        filtered_df = df[choix_cols].copy()

        # Aperçu du tableau filtré
        st.markdown("### Aperçu du tableau filtré")
        st.dataframe(filtered_df.head(12))
        
        # Affichage du nombre total de produits
        total_products = len(filtered_df)
        st.info(f"📊 **{total_products} produits** seront traités pour la génération du PDF")

        # 4. Choix ressources graphiques et paramètres
        st.markdown("---")
        col1, col2 = st.columns(2)
        logo_path = None
        cover_path = None
        with col1:
            logo_img = st.file_uploader("Logo de votre marque (optionnel, PNG)", type=["png"], key="logo")
            if logo_img:
                logo_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                logo_temp.write(logo_img.read())
                logo_temp.close()
                logo_path = logo_temp.name
                st.image(logo_img, width=100, caption="Aperçu du logo")
        with col2:
            cover_img = st.file_uploader(
                "Image de couverture (obligatoire pour une couverture pleine page A4, JPG/PNG, 2480x3508px)",
                type=["jpg", "jpeg", "png"], key="cover"
            )
            st.markdown(
                "<small style='color: #d32f2f'>⚠️ Pour une couverture parfaite : importe une image de <b>2480 x 3508 px</b> (format A4 à 300 dpi). Toute autre dimension sera déformée.</small>",
                unsafe_allow_html=True
            )
            cover_path = None
            if cover_img:
                cover_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                cover_temp.write(cover_img.read())
                cover_temp.close()
                cover_path = cover_temp.name

                # Validation des dimensions de l'image de couverture
                img = open_image(cover_path)
                if img.size != (2480, 3508):
                    st.warning("⚠️ Image de couverture non optimale (idéal: 2480x3508 px). Elle sera redimensionnée, mais pourrait se déformer.")

                # Aperçu réduit (divisé par 8)
                w, h = img.size
                st.image(cover_img, width=int(w/8), caption="Aperçu de l'image de couverture")

        # Sélection du nombre de produits par page
        produits_par_page = st.selectbox("Nombre de produits par page :", [1, 2, 3, 4], index=3, help="Plus de produits par page optimise l'espace mais réduit la taille des éléments")
        if produits_par_page >= 3:
            st.info("ℹ️ Mode haute densité : polices optimisées et espacement ajusté pour une meilleure utilisation de l'espace.")
        
        color = st.color_picker("Couleur principale du catalogue :", value="#1976d2")
        titre = st.text_input("Titre du catalogue :", "Catalogue SnapCatalog")
        sous_titre = st.text_input("Sous-titre :", "Tous nos produits en un coup d'œil")

else:
    st.stop()

# --- GÉNÉRATION DU PDF ---
st.subheader("🚀 Génération du PDF")

# Qualité fixée en HD par défaut
selected_quality = "hd"

# Option d'aperçu
preview = st.checkbox("Afficher un aperçu (lent)", value=False, disabled=not HAVE_PDF2IMAGE)
if not HAVE_PDF2IMAGE and preview:
    st.info("pdf2image non disponible pour l'aperçu.")

col1, col2 = st.columns([1, 1])

with col1:
    if st.button("Générer le PDF catalogue 🚀"):
        # Barre de progression
        st.session_state.progress_bar = st.progress(0)
        st.session_state.status_text = st.empty()
        progress_bar = st.session_state.progress_bar
        status_text = st.session_state.status_text
        
        try:
            # Étape 1: Préparation des données (5%)
            status_text.text("🔄 Préparation des données...")
            progress_bar.progress(0.05)
            
            # Enregistrement des polices système (10%)
            status_text.text("🔤 Enregistrement des polices...")
            download_and_register_fonts()
            progress_bar.progress(0.10)
            
            # Conversion des données (15%)
            status_text.text("📊 Pré-traitement des données...")
            progress_bar.progress(0.15)
            
            # Sécurisation automatique des données (anti-dépassement)
            df_pdf = filtered_df.copy().fillna("").astype(str)
            max_chars = 800  # Limite fixe pour éviter les erreurs PDF
            
            # Fonction de troncature intelligente
            def safe_truncate(text, max_len):
                if len(str(text)) <= max_len:
                    return str(text)
                return str(text)[:max_len-3] + "..."
            
            df_pdf = df_pdf.applymap(lambda s: safe_truncate(s, max_chars))
            
            products = df_pdf.to_dict(orient="records")
            
            # Étape 2: Génération de la couverture (20%)
            status_text.text("📄 Génération de la couverture...")
            progress_bar.progress(0.20)
            
            # Étape 3: Génération du PDF avec progression détaillée
            status_text.text("📦 Génération des pages produits...")
            progress_bar.progress(0.25)
            
            # Génération en mémoire avec qualité sélectionnée et callback de progression détaillée
            st.session_state.pdf_bytes = safe_generate_pdf(
                products=products,
                filename=None,
                titre=titre,
                sous_titre=sous_titre,
                logo_path=logo_path,
                cover_path=cover_path,
                quality=selected_quality,
                products_per_page=produits_par_page,
                bg_color=bg_color,
                primary_color=color,
                output="bytes",
                progress_callback=update_progress_detailed
            )
            
            # Progression finale après génération
            progress_bar.progress(0.95)
            status_text.text("🔧 Finalisation du PDF...")
            
            # Chemin temporaire pour l'aperçu (98%)
            status_text.text("💾 Sauvegarde temporaire...")
            tmp = Path(tempfile.gettempdir()) / st.session_state.pdf_name
            tmp.write_bytes(st.session_state.pdf_bytes)
            st.session_state.pdf_tmp_path = tmp
            progress_bar.progress(0.98)
            
            # Étape 4: Finalisation (100%)
            progress_bar.progress(1.0)
            status_text.text("✅ PDF généré avec succès !")
            
            st.success("PDF moderne généré avec succès en Haute Définition (HD) !")
            
        except LayoutError as e:
            st.error(f"❌ Erreur de mise en page : {e}")
            st.info("💡 Le contenu est trop large pour la page. Essayez de réduire le nombre de colonnes ou de produits par page.")
            status_text.text("❌ Erreur de mise en page")
        except Exception as e:
            st.error(f"Erreur lors de la génération du PDF : {e}")
            status_text.text("❌ Erreur lors de la génération")

with col2:
    # Espace pour équilibrer la mise en page
    st.write("")

# Aperçu optionnel (1–3 pages) sans relancer la génération
if preview and st.session_state.pdf_tmp_path and st.session_state.pdf_tmp_path.exists():
    st.markdown("---")
    st.subheader("📄 Aperçu du PDF généré")
    st.write("**Voici un aperçu des 3 premières pages de votre catalogue :**")
    
    try:
        images = convert_from_path(
            str(st.session_state.pdf_tmp_path),
            dpi=110,
            first_page=1,
            last_page=3,
        )
        for i, img in enumerate(images, 1):
            # Redimensionner l'image (diviser par 8)
            w, h = img.size
            new_w, new_h = w // 8, h // 8
            img_resized = img.resize((new_w, new_h))
            
            st.image(img_resized, caption=f"Aperçu page {i}", width=new_w)
    except Exception as e:
        st.warning(f"⚠️ Aperçu indisponible: {e}")
        st.info("💡 L'aperçu nécessite l'installation de poppler-utils.")

# Section Feedback (optionnelle)
if st.session_state.pdf_bytes:
    st.markdown("---")
    st.subheader("📝 Feedback obligatoire")
    st.write("**Pour télécharger votre PDF, vous devez d'abord nous donner votre avis :**")

    # Initialiser les variables de session pour le feedback
    if "feedback_submitted" not in st.session_state:
        st.session_state.feedback_submitted = False
    if "feedback_rating" not in st.session_state:
        st.session_state.feedback_rating = None
    if "feedback_comment" not in st.session_state:
        st.session_state.feedback_comment = None

    with st.form("feedback_form"):
        st.write("**Votre avis sur SnapCatalog :**")
        exp = st.radio("Comment trouvez-vous l'expérience SnapCatalog ?", 
                       ["⭐️⭐️⭐️⭐️⭐️ Excellent", "⭐️⭐️⭐️⭐️ Bien", "⭐️⭐️ Moyen", "⭐️ Pas terrible"], 
                       index=None, horizontal=True)
        feedback = st.text_area("Un commentaire ou une suggestion ? (obligatoire)")
        feedback_submitted = st.form_submit_button("💾 Soumettre mon avis")
        
        # Validation du formulaire
        if feedback_submitted:
            if not exp:
                st.error("⚠️ Veuillez sélectionner une note.")
            elif not feedback or feedback.strip() == "":
                st.error("⚠️ Veuillez saisir un commentaire.")
            else:
                try:
                    save_feedback_to_csv(exp, feedback)
                    save_feedback_to_sqlite(exp, feedback)
                    st.session_state.feedback_submitted = True
                    st.session_state.feedback_rating = exp
                    st.session_state.feedback_comment = feedback
                    st.success("✅ Feedback sauvegardé avec succès !")
                    st.write(f"📁 Fichiers créés dans : {os.path.dirname(__file__)}")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Erreur de sauvegarde : {e}")

    # Bouton de téléchargement - seulement si le feedback a été soumis
    if st.session_state.feedback_submitted:
        st.success("🎉 Merci pour votre retour !")
        st.markdown("---")
        st.subheader("💾 Télécharger votre catalogue")
        st.download_button(
            label="📥 Télécharger le PDF catalogue",
            data=st.session_state.pdf_bytes,
            file_name=st.session_state.pdf_name,
            mime="application/pdf",
            help="Cliquez pour télécharger votre catalogue personnalisé !"
        )
    else:
        st.warning("⚠️ Vous devez d'abord soumettre votre avis pour télécharger le PDF.")
        st.info("Veuillez remplir le formulaire de feedback ci-dessus.")
else:
    st.warning("Aucun PDF n'a encore été généré. Cliquez d'abord sur 'Générer le PDF catalogue 🚀'.")
