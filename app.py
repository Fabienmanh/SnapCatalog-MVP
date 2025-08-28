
import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pathlib import Path
import tempfile

from utils.image_processing import get_image, get_hex_color_safe, open_image, process_images

# EN HAUT de app.py, ajoutez :
from utils.font_manager import download_and_register_fonts, get_font_name
from reportlab.lib.units import cm
from utils.helpers import update_progress_detailed

from pdf.pdf_generator import generate_pdf_with_progress, generate_pdf_with_quality

# Nos modules
from upload_handler import UploadHandler
from pdf_designer import CatalogDesigner, generate_modern_catalog_with_progress, generate_pdf_with_quality
from utils.data_processing import save_feedback_to_csv, save_feedback_to_sqlite, get_feedback_stats, detect_csv_type

# Optionnel: aperçu PDF
try:
    from pdf2image import convert_from_path
    HAVE_PDF2IMAGE = True
except Exception:
    HAVE_PDF2IMAGE = False

# Code de dessin de couverture supprimé car remplacé par les fonctions de pdf_designer.py


# Ces imports sont déjà présents en haut du fichier

# Fonctions utilitaires supprimées car remplacées par celles de pdf_designer.py

# ---------- 

# Fonction de test supprimée car non utilisée

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
from utils.font_manager import validate_background_color
validated_color, was_adjusted = validate_background_color(bg_color)

if was_adjusted:
    st.warning(f"⚠️ La couleur a été ajustée pour maintenir la lisibilité : {validated_color}")
    st.info("💡 Les couleurs trop sombres sont automatiquement éclaircies pour garantir une lecture confortable.")

# Utiliser la couleur validée
bg_color = validated_color


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
    try:
        from utils.image_processing import open_image
        from reportlab.platypus import Image as RLImage
        pil = open_image(path)
        if pil:
            iw, ih = pil.size
            max_w = max_width_cm * cm
            max_h = max_height_cm * cm
            ratio = min(max_w / iw, max_h / ih, 1)
            new_w, new_h = iw * ratio, ih * ratio
            # Toujours retourner un RLImage, le centrage sera géré par la table
            return RLImage(path, width=new_w, height=new_h)
        return None
    except Exception:
        return None

# 1. Import du fichier CSV de produits
from upload_handler import UploadHandler

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
                from utils.image_processing import open_image
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
        # Police fixée en Helvetica (choix des polices supprimé de l'interface)
        police = "Helvetica"
        color = st.color_picker("Couleur principale du catalogue :", value="#1976d2")
        titre = st.text_input("Titre du catalogue :", "Catalogue SnapCatalog")
        sous_titre = st.text_input("Sous-titre :", "Tous nos produits en un coup d'œil")

else:
    st.stop()

# --- FONCTION DE COUVERTURE (ne fait que dessiner la 1re page) ---







def draw_cover(canvas, doc):
    page_width, page_height = doc.pagesize

    # 1. Couverture pleine page
    if cover_path:
        from utils.image_processing import open_image
        from reportlab.lib.utils import ImageReader
        img = open_image(cover_path)
        if img:
            # Conversion correcte des dimensions ReportLab en pixels pour éviter la pixelisation
            dpi = 300  # Résolution élevée pour la qualité
            width_px = int(page_width * dpi / 72)  # 72 points = 1 pouce
            height_px = int(page_height * dpi / 72)
            img = img.resize((width_px, height_px), img.Resampling.LANCZOS)
            cover_img = ImageReader(img)
            canvas.drawImage(cover_img, 0, 0, width=page_width, height=page_height)

    # 2. Logo en haut à droite, dans la marge
    logo_top_margin = 2.5 * cm
    if logo_path:
        try:
            from utils.image_processing import open_image
            from reportlab.lib.utils import ImageReader
            logo = open_image(logo_path)
            if logo:
                max_logo_w, max_logo_h = 3*cm, 3*cm
                logo_ratio = logo.width / logo.height
                if logo_ratio > 1:
                    lw, lh = max_logo_w, max_logo_w / logo_ratio
                else:
                    lw, lh = max_logo_h * logo_ratio, max_logo_h
                # Amélioration de la qualité du logo avec un redimensionnement plus précis
                dpi = 300  # Résolution élevée pour la qualité
                new_width_px = int(lw * dpi / 72)  # Conversion en pixels
                new_height_px = int(lh * dpi / 72)
                logo_resized = logo.resize((new_width_px, new_height_px), logo.Resampling.LANCZOS)
                logo_img = ImageReader(logo_resized)
                canvas.drawImage(
                    logo_img,
                    page_width - lw - logo_top_margin,  # x
                    page_height - lh - logo_top_margin, # y
                    width=lw, height=lh, mask='auto'
                )
        except Exception as e:
            print(f"Erreur logo: {e}")

    # --- TITRE avec wrap et centrage amélioré ---
    # Calcul dynamique de la taille du rectangle selon la longueur du titre
    title_length = len(titre)
    
    # Ajuster la largeur du rectangle selon la longueur du titre
    if title_length <= 30:
        rect_width = page_width * 0.86
        rect_height = 100
        font_size = 38
    elif title_length <= 50:
        rect_width = page_width * 0.90
        rect_height = 120
        font_size = 34
    elif title_length <= 70:
        rect_width = page_width * 0.92
        rect_height = 140
        font_size = 30
    else:
        rect_width = page_width * 0.94
        rect_height = 160
        font_size = 26
    
    # Forcer le wrap manuel si le titre est trop long
    if title_length > 50:
        # Diviser le titre en mots et forcer le retour à la ligne
        words = titre.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            if len(test_line) > 25:  # Limite de caractères par ligne
                if current_line:
                    lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        
        if current_line:
            lines.append(current_line)
        
        # Ajuster la hauteur du rectangle selon le nombre de lignes
        if len(lines) > 2:
            rect_height = max(rect_height, len(lines) * (font_size + 10))
    
    rect_x = (page_width - rect_width) / 2
    rect_y = page_height - rect_height - 2.5*cm - (logo_path and lh or 0) - 12
    
    # Rectangle blanc transparent
    canvas.saveState()
    try: canvas.setFillAlpha(0.84)
    except: pass
    canvas.setFillColorRGB(1, 1, 1)
    canvas.roundRect(rect_x, rect_y, rect_width, rect_height, 20, stroke=0, fill=1)
    canvas.setFillAlpha(1)
    canvas.restoreState()

    # Style du titre avec wrap et centrage vertical amélioré
    title_style = ParagraphStyle(
        'cover_title',
        fontName=get_font_name(police, bold=True),
        fontSize=font_size,
        alignment=1,  # centré horizontalement
        textColor=colors.HexColor(color),
        leading=font_size + 6,  # Leading proportionnel à la taille de police
        spaceBefore=0,
        spaceAfter=0,
        wordWrap='CJK',  # Meilleur wrap des mots
        splitLongWords=True,  # Forcer la coupure des mots longs
        splitLongWordsMaxLength=15,  # Longueur max des mots avant coupure
    )
    
    # Créer le paragraphe avec une marge plus généreuse pour le wrap
    p_title = Paragraph(titre, title_style)
    
    # Calculer la taille optimale avec une marge plus généreuse
    wrap_width = rect_width - 60  # Marge de 30px de chaque côté (plus généreuse)
    wrap_height = rect_height - 40  # Marge de 20px en haut et en bas (plus généreuse)
    
    # Essayer de wrapper le texte
    w, h = p_title.wrap(wrap_width, wrap_height)
    
    # Si le texte ne rentre toujours pas, réduire la taille de police de manière plus agressive
    if h > wrap_height:
        # Réduire progressivement la taille de police
        for test_size in [font_size-3, font_size-6, font_size-9, font_size-12, font_size-15]:
            if test_size < 16:  # Taille minimum plus basse
                break
            title_style.fontSize = test_size
            title_style.leading = test_size + 6
            p_title = Paragraph(titre, title_style)
            w, h = p_title.wrap(wrap_width, wrap_height)
            if h <= wrap_height:
                break
    
    # Si le texte ne rentre toujours pas, agrandir le rectangle
    if h > wrap_height:
        # Agrandir le rectangle pour accommoder le texte
        rect_height = h + 60  # 30px de marge en haut et en bas
        rect_y = page_height - rect_height - 2.5*cm - (logo_path and lh or 0) - 12
        
        # Redessiner le rectangle avec la nouvelle taille
        canvas.saveState()
        try: canvas.setFillAlpha(0.84)
        except: pass
        canvas.setFillColorRGB(1, 1, 1)
        canvas.roundRect(rect_x, rect_y, rect_width, rect_height, 20, stroke=0, fill=1)
        canvas.setFillAlpha(1)
        canvas.restoreState()
    
    # Dessiner le titre centré avec un centrage vertical parfait
    title_x = rect_x + (rect_width - w) / 2
    
    # Centrage vertical amélioré : calculer la position exacte
    # Ajouter un petit offset pour compenser la descente des caractères
    baseline_offset = font_size * 0.25  # Offset pour la baseline
    title_y = rect_y + (rect_height - h) / 2 + baseline_offset
    
    # Debug: afficher les dimensions pour diagnostiquer
    print(f"[DEBUG] Titre: '{titre}' (longueur: {title_length})")
    print(f"[DEBUG] Rectangle: {rect_width:.1f} x {rect_height:.1f}")
    print(f"[DEBUG] Wrap: {w:.1f} x {h:.1f}")
    print(f"[DEBUG] Position: ({title_x:.1f}, {title_y:.1f})")
    print(f"[DEBUG] Baseline offset: {baseline_offset:.1f}")
    
    # Si le wrap automatique a échoué, utiliser un wrap manuel
    if h > rect_height - 40:  # Si le texte dépasse encore
        print(f"[DEBUG] Wrap automatique échoué, utilisation du wrap manuel")
        
        # Wrap manuel complet
        words = titre.split()
        lines = []
        current_line = ""
        max_chars_per_line = int(rect_width / (font_size * 0.6))  # Estimation des caractères par ligne
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            if len(test_line) > max_chars_per_line:
                if current_line:
                    lines.append(current_line.strip())
                current_line = word
            else:
                current_line = test_line
        
        if current_line:
            lines.append(current_line.strip())
        
        # Dessiner chaque ligne manuellement avec centrage vertical parfait
        line_height = font_size + 6
        total_height = len(lines) * line_height
        # Centrage vertical amélioré avec offset pour la baseline
        start_y = rect_y + (rect_height - total_height) / 2 + baseline_offset
        
        for i, line in enumerate(lines):
            y_pos = start_y + i * line_height
            # Centrer horizontalement chaque ligne
            text_width = canvas.stringWidth(line, get_font_name(police, bold=True), font_size)
            x_pos = rect_x + (rect_width - text_width) / 2
            
            canvas.setFont(get_font_name(police, bold=True), font_size)
            canvas.setFillColor(colors.HexColor(color))
            canvas.drawString(x_pos, y_pos, line)
    else:
        # Utiliser le wrap automatique normal avec centrage vertical parfait
        p_title.drawOn(canvas, title_x, title_y)

    # --- SOUS-TITRE wrap et centré amélioré ---
    # Calcul dynamique de la taille du rectangle selon la longueur du sous-titre
    subtitle_length = len(sous_titre)
    
    # Ajuster la largeur du rectangle selon la longueur du sous-titre
    if subtitle_length <= 40:
        sub_rect_width = page_width * 0.65
        sub_rect_height = 120
        sub_font_size = 20
    elif subtitle_length <= 60:
        sub_rect_width = page_width * 0.70
        sub_rect_height = 140
        sub_font_size = 18
    elif subtitle_length <= 80:
        sub_rect_width = page_width * 0.75
        sub_rect_height = 160
        sub_font_size = 16
    else:
        sub_rect_width = page_width * 0.80
        sub_rect_height = 180
        sub_font_size = 14
    
    sub_rect_x = (page_width - sub_rect_width) / 2
    sub_rect_y = page_height / 2 - sub_rect_height / 2

    canvas.saveState()
    try: canvas.setFillAlpha(0.80)
    except: pass
    canvas.setFillColorRGB(1, 1, 1)
    canvas.roundRect(sub_rect_x, sub_rect_y, sub_rect_width, sub_rect_height, 12, stroke=0, fill=1)
    canvas.setFillAlpha(1)
    canvas.restoreState()

    subtitle_style = ParagraphStyle(
        'cover_subtitle',
        fontName=get_font_name(police),
        fontSize=sub_font_size,
        alignment=1,
        textColor=colors.HexColor(color),
        leading=sub_font_size + 8,  # Leading proportionnel
        spaceBefore=0,
        spaceAfter=0,
        wordWrap='CJK',  # Meilleur wrap des mots
    )
    
    # Créer le paragraphe du sous-titre
    p_sub = Paragraph(sous_titre, subtitle_style)
    
    # Calculer la taille optimale avec une marge généreuse
    sub_wrap_width = sub_rect_width - 40
    sub_wrap_height = sub_rect_height - 20
    
    # Wrapper le sous-titre
    w2, h2 = p_sub.wrap(sub_wrap_width, sub_wrap_height)
    
    # Si le texte ne rentre pas, réduire la taille de police
    if h2 > sub_wrap_height:
        for test_size in [sub_font_size-2, sub_font_size-4, sub_font_size-6]:
            if test_size < 12:  # Taille minimum
                break
            subtitle_style.fontSize = test_size
            subtitle_style.leading = test_size + 8
            p_sub = Paragraph(sous_titre, subtitle_style)
            w2, h2 = p_sub.wrap(sub_wrap_width, sub_wrap_height)
            if h2 <= sub_wrap_height:
                break
    
    # Dessiner le sous-titre centré avec un centrage vertical parfait
    subtitle_x = sub_rect_x + (sub_rect_width - w2) / 2
    
    # Centrage vertical amélioré : calculer la position exacte
    # Ajouter un petit offset pour compenser la descente des caractères
    sub_baseline_offset = sub_font_size * 0.25  # Offset pour la baseline
    subtitle_y = sub_rect_y + (sub_rect_height - h2) / 2 + sub_baseline_offset
    
    # Debug: afficher les dimensions pour diagnostiquer
    print(f"[DEBUG] Sous-titre: '{sous_titre}' (longueur: {subtitle_length})")
    print(f"[DEBUG] Rectangle sous-titre: {sub_rect_width:.1f} x {sub_rect_height:.1f}")
    print(f"[DEBUG] Wrap sous-titre: {w2:.1f} x {h2:.1f}")
    print(f"[DEBUG] Position sous-titre: ({subtitle_x:.1f}, {subtitle_y:.1f})")
    print(f"[DEBUG] Baseline offset sous-titre: {sub_baseline_offset:.1f}")
    
    p_sub.drawOn(canvas, subtitle_x, subtitle_y)

def draw_footer(canvas, doc):
    page_width, page_height = doc.pagesize
    
    # Numéro de page
    page_num = canvas.getPageNumber()
    if page_num > 1:  # À partir de la page 2
        canvas.saveState()
        canvas.setFont(get_font_name(police, bold=False), 10)
        canvas.setFillColor(colors.black)  # Numéro de page en noir
        
        # Position du numéro de page et logo selon pages paires/impaires
        footer_y = 1.5 * cm
        page_text = f"Page {page_num}"
        text_width = canvas.stringWidth(page_text, get_font_name(police, bold=False), 10)
        
        # Alterner la position selon les pages paires/impaires
        if page_num % 2 == 0:  # Page paire
            # Numéro de page à gauche
            page_x = 1.5 * cm
            # Logo à droite
            logo_x = page_width - 0.7*cm - 1.5*cm  # 7mm logo + marge
        else:  # Page impaire
            # Numéro de page à droite
            page_x = page_width - text_width - 1.5*cm
            # Logo à gauche
            logo_x = 1.5 * cm
        
        canvas.drawString(page_x, footer_y, page_text)
        
        # Logo (7mm x 7mm max)
        if logo_path:
            try:
                logo = PILImage.open(logo_path)
                logo_size = 0.7 * cm  # 7mm
                logo_ratio = logo.width / logo.height
                if logo_ratio > 1:
                    lw, lh = logo_size, logo_size / logo_ratio
                else:
                    lw, lh = logo_size * logo_ratio, logo_size
                
                # Amélioration de la qualité du logo footer
                dpi = 300  # Résolution élevée pour la qualité
                new_width_px = int(lw * dpi / 72)  # Conversion en pixels
                new_height_px = int(lh * dpi / 72)
                logo_resized = logo.resize((new_width_px, new_height_px), PILImage.Resampling.LANCZOS)
                logo_img = ImageReader(logo_resized)
                logo_y = footer_y - lh/2  # Centré verticalement avec le texte
                
                canvas.drawImage(logo_img, logo_x, logo_y, width=lw, height=lh, mask='auto')
            except Exception as e:
                print(f"Erreur logo footer: {e}")
        
        canvas.restoreState()

# --- GÉNÉRATION DU PDF ---
st.subheader("🚀 Génération du PDF")

# Qualité fixée en HD par défaut (à réintégrer plus tard)
selected_quality = "hd"

# Police fixée en Helvetica (choix supprimé de l'interface)

# Option d'aperçu (définie au niveau global)
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
            status_text.text("📊 Conversion des données...")
            products = filtered_df.to_dict(orient="records")
            progress_bar.progress(0.15)
            
            # Étape 2: Génération de la couverture (20%)
            status_text.text("📄 Génération de la couverture...")
            progress_bar.progress(0.20)
            
            # Étape 3: Génération du PDF avec progression détaillée
            status_text.text("📦 Génération des pages produits...")
            progress_bar.progress(0.25)
            
            # Génération en mémoire avec qualité sélectionnée et callback de progression détaillée
            # Le callback update_progress gère maintenant la progression automatiquement
            st.session_state.pdf_bytes = generate_pdf_with_quality(
                products, None, titre, sous_titre, logo_path, cover_path, 
                quality=selected_quality, products_per_page=produits_par_page, 
                bg_color=bg_color, primary_color=color, output="bytes", progress_callback=update_progress_detailed
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
            
        except Exception as e:
            st.error(f"Erreur lors de la génération du PDF : {e}")
            status_text.text("❌ Erreur lors de la génération")

with col2:
    # Espace pour équilibrer la mise en page
    st.write("")

# Note: Section de téléchargement déplacée après l'aperçu et le feedback

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
