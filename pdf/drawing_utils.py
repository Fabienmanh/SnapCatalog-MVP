# pdf/drawing_utils.py
from reportlab.lib.units import mm
from reportlab.lib import colors

def draw_box(c, x, y, w, h, r=4*mm, fill=colors.white, alpha=0.92):
    c.saveState()
    if hasattr(c, 'setFillAlpha'):
        c.setFillAlpha(alpha)
    c.setFillColor(fill)
    c.setStrokeColor(None)
    c.roundRect(x, y, w, h, r, stroke=0, fill=1)
    if hasattr(c, 'setFillAlpha'):
        c.setFillAlpha(1)
    c.restoreState()
    pass

def draw_guides(c, page_w, page_h, points_mm, color=colors.Color(1,0,0,0.6)):
    c.saveState()
    c.setStrokeColor(color)
    c.setFillColor(color)
    for (x_mm, y_mm, label) in points_mm:
        x = x_mm * mm
        y = mm_from_top_to_y(page_h, y_mm)
        c.circle(x, y, 1.5, stroke=1, fill=1)
        c.setFont("Helvetica", 7)
        c.drawString(x+3, y+3, label)
    c.rect(0, 0, page_w, page_h, stroke=1, fill=0)
    c.restoreState()
    pass

def draw_logo_mm(c, page_w, page_h, img_path, x_from_left_mm, y_from_top_mm, size_mm):
    """Place une image carrée aux coordonnées demandées."""
    img = ImageReader(img_path)
    w = h = size_mm * mm
    x = x_from_left_mm * mm
    y = mm_from_top_to_y(page_h, y_from_top_mm, h)
    c.drawImage(img, x, y, width=w, height=h, mask='auto', preserveAspectRatio=True, anchor='sw')
    pass

def debug_probe_cover(c, tag="DBG"):
    c.saveState()
    # 1. Cadre fluo sur toute la page
    c.setStrokeColor(colors.magenta)
    c.setLineWidth(3)
    c.rect(3, 3, page_w-6, page_h-6, stroke=1, fill=0)

    # 2. Étiquette de version en haut-gauche
    c.setFillColor(colors.magenta)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(10, page_h-24, f"{tag} {datetime.now().strftime('%H:%M:%S')}")

    # 3. Croix énorme au centre
    c.setLineWidth(6)
    c.line(0, 0, page_w, page_h)
    c.line(0, page_h, page_w, 0)
    c.restoreState()
    pass

def draw_cover_text_at_offsets(
    c, page_w, page_h,
    title_text, subtitle_text,
    title_offset_top_mm=112, subtitle_offset_top_mm=211,
    max_title_w_mm=160, max_title_h_mm=26,
    max_sub_w_mm=160,   max_sub_h_mm=16,
    title_font_base=40, title_font_min=16,
    subtitle_font=20,
    color=colors.HexColor("#1E5AA8"),
    pad_mm=6, radius_mm=4,
    font_bold="Helvetica-Bold", font_regular="Helvetica"
):
    pass
