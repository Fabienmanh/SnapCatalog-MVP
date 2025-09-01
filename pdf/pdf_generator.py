# pdf/pdf_generator.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate
import os
from pdf.drawing_utils import draw_box, draw_guides, draw_logo_mm, debug_probe_cover

def draw_title_block(
    c, page_w, page_h,
    title_text, subtitle_text,
    title_offset_top_mm=112, subtitle_offset_top_mm=211,
    max_block_width_mm=170,   # largeur max autorisée (en mm)
    pad_mm=6,
    title_font_name="Helvetica-Bold",
    title_font_base=42, title_font_min=16,
    subtitle_font_name="Helvetica", subtitle_font_size=20,
    color_hex="#1E5AA8",
    box_alpha=0.92, radius_mm=4
):
    pass

def cover_page(c, doc, bg_image_path=None, show_debug_guides=False):
    page_w, page_h = doc.pagesize

    # 1) Fond plein cadre (optionnel)
    if bg_image_path:
        try:
            c.drawImage(bg_image_path, 0, 0, width=page_w, height=page_h, mask='auto')
        except Exception as e:
            print("BG error:", e)

    # 2) Logo aux coordonnées demandées
    try:
        draw_logo_mm(
            c, page_w, page_h,
            img_path="assets/logo_classic_game_cover.png",
            x_from_left_mm=179.5, y_from_top_mm=30.95, size_mm=37
        )
    except Exception as e:
        print("Logo error:", e)

    # 3) Titre + Sous-titre
    draw_title_block(
        c, page_w, page_h,
        title_text="Catalogue Classic Game Cover 2025",
        subtitle_text="Tous nos produits en un coup d'œil",
        title_offset_top_mm=112,
        subtitle_offset_top_mm=211,
        max_block_width_mm=170,
        pad_mm=6,
        title_font_base=42, title_font_min=18,
        subtitle_font_size=20,
        color_hex="#1E5AA8",
        box_alpha=0.92, radius_mm=4
    )

    # 4) Guides (debug visuel)
    if show_debug_guides:
        draw_guides(c, page_w, page_h, [
            (179.5, 30.95, "Logo coin sup."),
            (page_w/mm/2, 112, "Titre @112mm"),
            (page_w/mm/2, 211, "Sous‑titre @211mm"),
        ])

    # 3) TITRE / SOUS-TITRE aux offsets exacts
    draw_title_block(
        canvas, page_w, page_h,
        title_text="Catalogue Classic Game Cover 2025",
        subtitle_text="Tous nos produits en un coup d'œil",
        title_offset_top_mm=112,
        subtitle_offset_top_mm=211,
        max_block_width_mm=170,   # élargis si tu veux plus large
        pad_mm=6,
        title_font_base=42, title_font_min=18,
        subtitle_font_size=20
    )

    # 4) GUIDES de contrôle (optionnel)
    if show_debug_guides:
        draw_guides(canvas, page_w, page_h, [
            (179.5, 30.95, "Logo (TL)"),
            (page_w/mm/2, 112, "Titre baseline ~"),
            (page_w/mm/2, 211, "Sous-titre baseline ~"),
        ])
    pass

def build_pdf(output_path="cover_test.pdf", bg_image_path=None, show_debug_guides=False):
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    story = []  # rien dans l'histoire : on compose tout dans le callback
    pass

    def first_page(c, d):
        cover_page(c, d, bg_image_path=bg_image_path, show_debug_guides=show_debug_guides)
    doc.build(story, onFirstPage=first_page, onLaterPages=first_page)
    pass

def generate_pdf(products, filename, titre, sous_titre, logo_path, cover_path, dpi=300, image_quality=0.95):
    # Utiliser les paramètres de qualité pour la génération
    print(f"[QUALITE] Génération en DPI: {dpi}, Qualité image: {image_quality}")
    return generate_modern_catalog(products, filename, titre, sous_titre, logo_path, cover_path)

def generate_pdf_with_progress(products, filename, titre, sous_titre, logo_path, cover_path, progress_callback=None, products_per_page=4, bg_color="#F0F0F0", primary_color="#1976d2", output="file"):
    """Génère le PDF avec une barre de progression détaillée
    
    Args:
        output: "file" pour écrire sur disque, "bytes" pour retourner en mémoire
    """
    
    if output == "bytes":
        # Génération en mémoire
        if progress_callback:
            return generate_modern_catalog_with_progress(products, None, titre, sous_titre, logo_path, cover_path, progress_callback, products_per_page, bg_color, primary_color, return_bytes=True)
        else:
            return generate_modern_catalog(products, None, titre, sous_titre, logo_path, cover_path, products_per_page, bg_color, primary_color, return_bytes=True)
    else:
        # Génération sur disque (comportement original)
        if progress_callback:
            return generate_modern_catalog_with_progress(products, filename, titre, sous_titre, logo_path, cover_path, progress_callback, products_per_page, bg_color, primary_color)
        else:
            return generate_modern_catalog(products, filename, titre, sous_titre, logo_path, cover_path, products_per_page, bg_color, primary_color)
            pass

def generate_pdf_with_quality(
    products, filename="catalog_modern.pdf", titre="Catalogue", sous_titre="",
    logo_path=None, cover_path=None, quality="hd", products_per_page=4, 
    bg_color="#F0F0F0", primary_color="#1976d2", output="file"
):
    # Configuration de la qualité
    quality_config = {
        'hd': {'dpi': 300, 'image_quality': 95},
        'medium': {'dpi': 150, 'image_quality': 75}, 
        'bd': {'dpi': 72, 'image_quality': 50}
    }
    
    config = quality_config.get(quality, quality_config['hd'])
    print(f"🎯 [PDF_GENERATOR] Qualité demandée: {quality}")
    print(f"🎯 [PDF_GENERATOR] Config: DPI={config['dpi']}, Quality={config['image_quality']}")
    
    return_bytes = (output == "bytes")
    
    # ✅ TRANSMISSION CORRIGÉE - AJOUTEZ LES PARAMÈTRES :
    return generate_modern_catalog_with_progress(
        products=products,
        filename=filename,
        titre=titre,
        sous_titre=sous_titre,
        logo_path=logo_path,
        cover_path=cover_path,
        products_per_page=products_per_page,
        bg_color=bg_color,
        primary_color=primary_color,
        return_bytes=return_bytes,
        # ✅ NOUVEAUX PARAMÈTRES DE QUALITÉ :
        image_dpi=config['dpi'],
        image_quality=config['image_quality']
    )
