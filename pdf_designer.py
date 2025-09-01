from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import os
import textwrap
from PIL import Image as PILImage
import re
from typing import Optional, Dict, Any

# Import des fonctions utilitaires
from utils.text_processing import _strip_spaces

NBSP = "\u00A0"          # espace insécable
NARROW_NBSP = "\u202F"   # espace fine insécable

def truncate_text_to_fit(text, max_width, font_name, font_size):
    """Coupe le texte avec ... si trop long"""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    
    if stringWidth(text, font_name, font_size) <= max_width:
        return text
    
    # Couper progressivement
    for i in range(len(text), 0, -1):
        truncated = text[:i] + "..."
        if stringWidth(truncated, font_name, font_size) <= max_width:
            return truncated
    
    return "..."

# Constantes pour le bandeau d'en-tête
BANNER_H = 24 * mm      # hauteur bandeau
BANNER_W = 210 * mm     # largeur A4 portrait
TEXT_Y_FROM_TOP = 18 * mm  # distance baseline texte -> bord haut
TEXT_LEFT_PAD = 10 * mm    # marge à gauche dans le bandeau



def _detect_ttc_flag(s_low: str) -> Optional[bool]:
    # True si TTC/T.V.A incluse détecté, False si HT détecté, None sinon
    ttc_patterns = [
        r"\bttc\b", r"\bt\.?t\.?c\.?\b", r"tva incl", r"tvaincluse", r"inclus[ea]? tva",
        r"toutes taxes? (comprises?|incluse?s?)"
    ]
    ht_patterns = [
        r"\bht\b", r"\bh\.?t\.?\b", r"hors taxe?s?\b", r"hors tva\b", r"sans tva\b"
    ]
    if any(re.search(p, s_low) for p in ttc_patterns):
        return True
    if any(re.search(p, s_low) for p in ht_patterns):
        return False
    return None

# Certaines devises n'ont pas de décimales usuelles
ZERO_DEC_CURRENCIES = {
    "JPY", "KRW", "VND", "CLP", "ISK", "HUF"  # (HUF/ISK historiquement 0, gardez si ça vous convient)
}

# Base de connaissance devise: regex -> (code, symbole, position "prefix"/"suffix")
# L'ordre compte: entrées plus spécifiques d'abord.
CURRENCY_KB = [
    (r"\b(xpf|cfp)\b",         ("XPF", "XPF", "suffix")),
    (r"\b(xof|cfa)\b",         ("XOF", "CFA", "suffix")),
    (r"\b(xaf|cfa)\b",         ("XAF", "CFA", "suffix")),
    (r"\b(mad|dh)\b",          ("MAD", "DH",  "suffix")),
    (r"\b(dzd)\b",             ("DZD", "DZD", "suffix")),
    (r"\b(tnd)\b",             ("TND", "TND", "suffix")),
    (r"\b(chf|sfr|fr\.)\b",    ("CHF", "CHF", "suffix")),
    (r"\b(gbp|£)\b|£",         ("GBP", "£",   "prefix")),
    (r"\b(usd)\b|\$",          ("USD", "$",   "prefix")),
    (r"\b(cad)\b|cad\$",       ("CAD", "C$",  "prefix")),
    (r"\b(aud)\b|au\$",        ("AUD", "A$",  "prefix")),
    (r"\b(nzd)\b|nz\$",        ("NZD", "NZ$", "prefix")),
    (r"\b(jpy|¥|￥)\b|¥|￥",   ("JPY", "¥",   "prefix")),
    (r"\b(cny|rmb)\b|¥|￥",    ("CNY", "¥",   "prefix")),
    (r"\b(hkd)\b",             ("HKD", "HK$", "prefix")),
    (r"\b(sgd)\b",             ("SGD", "S$",  "prefix")),
    (r"\b(sek)\b|kr\b",        ("SEK", "kr",  "suffix")),
    (r"\b(nok)\b|kr\b",        ("NOK", "kr",  "suffix")),
    (r"\b(dkk)\b|kr\b",        ("DKK", "kr",  "suffix")),
    (r"\b(pln)\b|zł",          ("PLN", "zł",  "suffix")),
    (r"\b(czk)\b|kč",          ("CZK", "Kč",  "suffix")),
    (r"\b(huf)\b|ft\b",        ("HUF", "Ft",  "suffix")),
    (r"\b(ron|lei|leu)\b",     ("RON", "lei", "suffix")),
    (r"\b(bgn)\b|лв\.?",       ("BGN", "лв",  "suffix")),
    (r"\b(try)\b|₺",           ("TRY", "₺",   "suffix")),
    (r"\b(uah)\b|₴",           ("UAH", "₴",   "suffix")),
    (r"\b(rub)\b|₽",           ("RUB", "₽",   "suffix")),
    (r"\b(inr)\b|₹|rs\.?",     ("INR", "₹",   "prefix")),
    (r"\b(aed)\b|د\.?إ\.?",    ("AED", "AED", "suffix")),
    (r"\b(sar)\b|ر\.?س\.?",    ("SAR", "SAR", "suffix")),
    (r"\b(qar)\b",             ("QAR", "QAR", "suffix")),
    (r"\b(brl)\b|r\$",         ("BRL", "R$",  "prefix")),
    (r"\b(mxn)\b",             ("MXN", "MX$", "prefix")),
    (r"\b(ars)\b",             ("ARS", "AR$", "prefix")),
    (r"\b(cop)\b",             ("COP", "COL$", "prefix")),
    (r"\b(zar)\b|r\b",         ("ZAR", "R",   "prefix")),
    (r"\b(ils|nis)\b|₪",       ("ILS", "₪",   "prefix")),
    (r"\b(php)\b|₱",           ("PHP", "₱",   "prefix")),
    (r"\b(thb)\b|฿",           ("THB", "฿",   "prefix")),
    (r"\b(vnd)\b|₫",           ("VND", "₫",   "suffix")),
    (r"\b(kwd)\b",             ("KWD", "KWD", "suffix")),
    (r"\b(omr)\b",             ("OMR", "OMR", "suffix")),
    (r"\b(bhd)\b",             ("BHD", "BHD", "suffix")),
    # EUR en dernier (par défaut en contexte FR)
    (r"€|\beur\b|\beuro?s?\b", ("EUR", "€",   "suffix")),
]

def _detect_currency(raw: str) -> tuple[str, str, str]:
    """
    Retourne (code, symbole, position) avec position in {"prefix","suffix"}.
    Par défaut EUR si rien détecté (contexte FR).
    """
    s = raw.lower()
    for pat, (code, symbol, pos) in CURRENCY_KB:
        if re.search(pat, s, flags=re.UNICODE):
            return code, symbol, pos
    return "EUR", "€", "suffix"

def _extract_unit(raw: str) -> str:
    # Extrait un suffixe d'unité typique pour l'affichage
    s = raw.lower()
    # Ordre important: m² avant m2, etc.
    unit_candidates = [
        r"/\s*m²", r"/\s*m2", r"/\s*u", r"/\s*unité", r"/\s*kg", r"/\s*g",
        r"/\s*l", r"/\s*litre?s?", r"/\s*pa?ck", r"/\s*lot", r"/\s*ml", r"/\s*pi[eè]ce"
    ]
    for pat in unit_candidates:
        m = re.search(pat, s)
        if m:
            # Récupère exactement comme écrit dans la source (utilise l'index trouvé)
            start, end = m.span()
            return raw[start:end].strip()
    return ""

def _extract_prefix(raw: str) -> str:
    s = raw.strip()
    m = re.match(r"(?i)\s*(à\s*partir\s*de|dès|~|≈|env\.?|environ|à partir d')\s*", s, flags=re.UNICODE)
    return m.group(0).strip() if m else ""

def _find_numbers(raw: str):
    # Capture nombres FR: mille: espace/point, décimale: virgule
    # Ex: "1 234,56" "1.234,56" "1234,56" "12,5" "12"
    # On autorise aussi le format US si clairement utilisé: "1,234.56"
    s = raw
    # Unifie espaces
    s = s.replace(NBSP, " ").replace(NARROW_NBSP, " ")
    # Deux patterns: FR et US
    pat_fr = r"\d{1,3}(?:[ .]\d{3})*(?:,\d+)?|\d+(?:,\d+)?"
    pat_us = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
    nums_fr = re.findall(pat_fr, s)
    nums_us = re.findall(pat_us, s)
    # Heuristique: si présence d'une virgule décimale, on privilégie FR
    if any("," in n for n in nums_fr):
        return nums_fr, "FR"
    # Sinon si présence de points décimaux et virgules de milliers, on bascule US
    if any(re.search(r"\d,\d{3}\.", n) or "." in n for n in nums_us):
        return nums_us, "US"
    # Par défaut FR
    return nums_fr if nums_fr else nums_us, "FR"

def _to_float(num_str: str, style: str) -> Optional[float]:
    try:
        s = num_str.replace(" ", "").replace(".", "") if style == "FR" else num_str.replace(",", "")
        s = s.replace(",", ".")
        return float(s)
    except Exception:
        return None

def _format_eur_fr(value: float, decimals: int = 2) -> str:
    if value is None:
        return ""
    s = f"{value:,.{decimals}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", NARROW_NBSP)
    if decimals > 0 and s.endswith(",00"):
        s = s[:-3]
    return f"{s} €"

def _format_other_currency(value: float, code: str, symbol: str, pos: str, decimals: int) -> str:
    if value is None:
        return ""
    # Format FR: séparateur milliers fine insécable, virgule décimale
    s = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", NARROW_NBSP)
    if decimals > 0 and s.endswith(",00"):
        s = s[:-3]
    if pos == "prefix":
        return f"{symbol}{s}"
    else:
        # espace fine insécable avant un suffixe
        return f"{s}{NARROW_NBSP}{symbol}"

def normalize_price(
    raw_price: Any,
    *,
    default_is_ttc: bool = True,
    fx_to_eur: Optional[Dict[str, float]] = None,   # ex: {"USD": 0.92, "GBP": 1.17}
    min_decimals: int = 0,
    max_decimals: int = 2
) -> Dict[str, Any]:
    """
    Normalise un prix pour affichage FR + valeur numérique en EUR.
    - raw_price: str ou nombre
    - default_is_ttc: si TTC/HT non détecté dans le texte
    - fx_to_eur: taux (1 unité devise -> EUR). Si devise != EUR et taux absent: value_eur=None, display conservé.
    - min/max_decimals: pour l'affichage (ex: 12,5 -> 12,50 si min_decimals=2)
    """
    # Cas numériques directs
    if isinstance(raw_price, (int, float)):
        value = float(raw_price)
        display = _format_eur_fr(value, decimals=max_decimals)
        return {
            "value_eur": round(value, max_decimals),
            "is_ttc": default_is_ttc,
            "display": (display + (" TTC" if default_is_ttc else " HT"))
        }

    raw = _strip_spaces(str(raw_price) if raw_price is not None else "")
    if raw == "":
        return {"value_eur": None, "is_ttc": default_is_ttc, "display": ""}

    # Gratuit / Offert
    if re.search(r"(?i)\b(gratuit|offert|inclus)\b", raw):
        # On suppose TTC pour l'affichage si non spécifié
        disp = "Gratuit"
        return {"value_eur": 0.0, "is_ttc": True if _detect_ttc_flag(raw.lower()) is not False else False, "display": disp}

    s_low = raw.lower()
    is_ttc = _detect_ttc_flag(s_low)
    if is_ttc is None:
        is_ttc = default_is_ttc

    currency_code, currency_symbol, currency_pos = _detect_currency(raw)
    unit = _extract_unit(raw)
    prefix = _extract_prefix(raw)

    # Intervalles / "de … à …"
    # On récupère tous les nombres, on garde le min comme value_eur
    nums, style = _find_numbers(raw)
    values = [_to_float(n, style) for n in nums if n is not None]
    values = [v for v in values if v is not None]

    value_num = None
    is_range = False
    if len(values) == 0:
        # Rien de solide trouvé: on renvoie l'affichage nettoyé
        return {"value_eur": None, "is_ttc": is_ttc, "display": raw}
    elif len(values) == 1:
        value_num = values[0]
    else:
        is_range = True
        value_num = min(values)

    # Conversion devise -> EUR si nécessaire
    value_eur: Optional[float]
    if currency_code == "EUR":
        value_eur = value_num
    else:
        if fx_to_eur and currency_code in fx_to_eur:
            value_eur = value_num * float(fx_to_eur[currency_code])
        else:
            value_eur = None  # on ne sait pas convertir

    # Décimales d'affichage: respecte min/max
    # Détermine si l'original avait des décimales ou si la devise n'utilise pas de décimales
    had_decimals = any(("," in n or "." in n) for n in nums)
    if currency_code in ZERO_DEC_CURRENCIES:
        decimals = 0
    else:
        decimals = max(min_decimals, 2 if had_decimals else 0)
        decimals = min(decimals, max_decimals)

    # Reconstruction de l'affichage
    # Texte prix:
    if currency_code == "EUR":
        if is_range and len(values) >= 2:
            txt = f"{_format_eur_fr(min(values), decimals)} – {_format_eur_fr(max(values), decimals)}"
        else:
            txt = _format_eur_fr(value_num, decimals)
    else:
        # Autre devise: utilise la nouvelle fonction de formatage
        if is_range and len(values) >= 2:
            txt = f"{_format_other_currency(min(values), currency_code, currency_symbol, currency_pos, decimals)} – {_format_other_currency(max(values), currency_code, currency_symbol, currency_pos, decimals)}"
        else:
            txt = _format_other_currency(value_num, currency_code, currency_symbol, currency_pos, decimals)

    # Suffixes TTC/HT
    tax_txt = "TTC" if is_ttc else "HT"

    # Assemble display
    parts = []
    if prefix:
        # Majuscule et apostrophe typographique
        pref = prefix.strip().capitalize().replace("'", "'")
        # Normalise quelques variantes
        pref = pref.replace("Env.", "Environ")
        parts.append(pref)
    parts.append(txt)
    if unit:
        parts.append(unit.replace(" ", " ").replace("m2", "m²"))  # m2 -> m² pour l'esthétique
    parts.append(tax_txt)
    display = " ".join(p for p in parts if p).strip()

    return {
        "value_eur": round(value_eur, decimals) if value_eur is not None else None,
        "is_ttc": is_ttc,
        "display": display
    }

def draw_modern_cover(c, titre, sous_titre, logo_path=None, cover_path=None):
    page_width, page_height = A4
    
    # Image de couverture
    if cover_path and os.path.exists(cover_path):
        try:
            cover_img = ImageReader(cover_path)
            c.drawImage(cover_img, 0, 0, width=page_width, height=page_height)
        except Exception as e:
            print(f"Erreur couverture : {e}")

    # Logo
    if logo_path and os.path.exists(logo_path):
        try:
            logo = PILImage.open(logo_path)
            if logo.mode != 'RGBA':
                logo = logo.convert('RGBA')
            logo_img = ImageReader(logo)
            max_logo_w, max_logo_h = 3.5 * cm, 3.5 * cm  # Augmenter la taille de 3cm à 3.5cm
            c.drawImage(
                logo_img,
                page_width - max_logo_w - 1.5 * cm,  # Réduire la marge droite de 2.5cm à 1.5cm
                page_height - max_logo_h - 1.5 * cm,  # Réduire la marge haute de 2.5cm à 1.5cm
                width=max_logo_w,
                height=max_logo_h,
                preserveAspectRatio=True,
                mask='auto',
            )
        except Exception as e:
            print(f"Erreur logo : {e}")

    # === TITRE PRINCIPAL ===
    # Calculer la taille optimale du rectangle selon la longueur du titre
    title_length = len(titre)
    
    # Ajuster la largeur et hauteur du rectangle selon la longueur
    if title_length <= 30:
        rect_width = page_width * 0.75
        rect_height = 3.5 * cm
        font_size = 38
    elif title_length <= 50:
        rect_width = page_width * 0.80
        rect_height = 4.0 * cm
        font_size = 34
    elif title_length <= 70:
        rect_width = page_width * 0.85
        rect_height = 4.5 * cm
        font_size = 30
    else:
        rect_width = page_width * 0.90
        rect_height = 5.0 * cm
        font_size = 26
    
    # Position du rectangle (centré horizontalement, au-dessus du centre)
    rect_x = (page_width - rect_width) / 2
    rect_y = page_height / 2 + 30
    
    # Dessiner le rectangle blanc semi-transparent
    c.saveState()
    c.setFillColorRGB(1, 1, 1, alpha=0.9)
    c.roundRect(rect_x, rect_y, rect_width, rect_height, 15, fill=1, stroke=0)
    c.restoreState()
    
    # Diviser le titre en lignes avec textwrap
    import textwrap
    # Calculer la largeur maximale en caractères (approximatif)
    max_chars_per_line = int(rect_width / (font_size * 0.6))
    title_lines = textwrap.wrap(titre, width=max_chars_per_line)
    
    # Limiter à 4 lignes maximum
    if len(title_lines) > 4:
        title_lines = title_lines[:4]
        # Ajouter "..." si le titre est tronqué
        if title_lines[-1]:
            title_lines[-1] = title_lines[-1][:max_chars_per_line-3] + "..."
    
    # Ajuster la hauteur du rectangle si nécessaire
    actual_height = len(title_lines) * (font_size + 50) / 72 * cm  # Ajuster avec le nouvel interlignage de 50
    if actual_height > rect_height:
        rect_height = actual_height + 1 * cm  # Ajouter 1cm de marge
        rect_y = page_height / 2 + 30
        # Redessiner le rectangle avec la nouvelle hauteur
        c.saveState()
        c.setFillColorRGB(1, 1, 1, alpha=0.9)
        c.roundRect(rect_x, rect_y, rect_width, rect_height, 15, fill=1, stroke=0)
        c.restoreState()
    
    # Dessiner le titre ligne par ligne
    c.setFont("Helvetica-Bold", font_size)
    c.setFillColor(colors.HexColor("#1E3A8A"))
    
    line_height = (font_size + 50) / 72 * cm  # Augmenter encore l'interlignage de 35 à 50 pour éliminer définitivement le chevauchement
    total_text_height = len(title_lines) * line_height
    
    # Centrage vertical simplifié et équilibré
    # Commencer par le bas du rectangle et remonter pour centrer parfaitement
    start_y = rect_y + (rect_height - total_text_height) / 2 + total_text_height - line_height
    
    for i, line in enumerate(title_lines):
        y_pos = start_y - i * line_height
        # Centrer horizontalement chaque ligne
        text_width = c.stringWidth(line, "Helvetica-Bold", font_size)
        x_pos = rect_x + (rect_width - text_width) / 2
        c.drawString(x_pos, y_pos, line)
    
    # === SOUS-TITRE ===
    # Calculer la taille du rectangle pour le sous-titre
    subtitle_length = len(sous_titre)
    
    if subtitle_length <= 40:
        sub_rect_width = page_width * 0.60
        sub_rect_height = 2.5 * cm
        sub_font_size = 20
    elif subtitle_length <= 60:
        sub_rect_width = page_width * 0.65
        sub_rect_height = 3.0 * cm
        sub_font_size = 18
    else:
        sub_rect_width = page_width * 0.70
        sub_rect_height = 3.5 * cm
        sub_font_size = 16
    
    # Position du rectangle du sous-titre (centré, en dessous du centre)
    sub_rect_x = (page_width - sub_rect_width) / 2
    sub_rect_y = page_height / 2 - 80
    
    # Dessiner le rectangle du sous-titre
    c.saveState()
    c.setFillColorRGB(1, 1, 1, alpha=0.9)
    c.roundRect(sub_rect_x, sub_rect_y, sub_rect_width, sub_rect_height, 12, fill=1, stroke=0)
    c.restoreState()
    
    # Diviser le sous-titre en lignes
    max_sub_chars = int(sub_rect_width / (sub_font_size * 0.6))
    subtitle_lines = textwrap.wrap(sous_titre, width=max_sub_chars)
    
    # Limiter à 3 lignes maximum
    if len(subtitle_lines) > 3:
        subtitle_lines = subtitle_lines[:3]
        if subtitle_lines[-1]:
            subtitle_lines[-1] = subtitle_lines[-1][:max_sub_chars-3] + "..."
    
    # Dessiner le sous-titre
    c.setFont("Helvetica", sub_font_size)
    c.setFillColor(colors.HexColor("#1976d2"))
    
    sub_line_height = (sub_font_size + 40) / 72 * cm  # Augmenter l'interlignage de 28 à 40 pour éliminer définitivement le chevauchement
    sub_total_height = len(subtitle_lines) * sub_line_height
    
    # Centrage vertical simplifié et équilibré (même logique que le titre)
    sub_start_y = sub_rect_y + (sub_rect_height - sub_total_height) / 2 + sub_total_height - sub_line_height
    
    for i, line in enumerate(subtitle_lines):
        y_pos = sub_start_y - i * sub_line_height
        # Centrer horizontalement
        text_width = c.stringWidth(line, "Helvetica", sub_font_size)
        x_pos = sub_rect_x + (sub_rect_width - text_width) / 2
        c.drawString(x_pos, y_pos, line)

def draw_snapcatalog_filigrane(c, page_num, pagesize):
    # Filigrane à partir de la page 2 uniquement
    if page_num < 2:
        return
    width, height = pagesize
    c.saveState()
    try:
        c.setFillGray(0.88)  # plus proche du "très léger"; ajuste entre 0.85 et 0.95
        font_name = "Helvetica"  # garde ta police actuelle
        font_size = 9
        text = "Catalogue généré par SnapCatalog"
        c.setFont(font_name, font_size)
        tw = c.stringWidth(text, font_name, font_size)
        x = (width - tw) / 2.0
        y = 0.7 * cm  # marge basse; ajuste si besoin
        c.drawString(x, y, text)
    finally:
        c.restoreState()

def draw_header_banner(c, page_w, page_h, title, subtitle=None,
                       bg_color=colors.HexColor("#1976D2"),
                       title_color=colors.white,
                       subtitle_color=colors.white):
    """
    Dessine un bandeau d'en-tête moderne en haut de page
    """
    # 1) Fond du bandeau (en haut de page)
    c.saveState()
    c.setFillColor(bg_color)
    c.setStrokeColor(bg_color)
    c.rect(0, page_h - BANNER_H, BANNER_W, BANNER_H, stroke=0, fill=1)

    # 2) Texte
    y_base = page_h - TEXT_Y_FROM_TOP  # baseline mesurée depuis le haut
    c.setFillColor(title_color)
    c.setFont("Helvetica-Bold", 18)    # ajuste la taille si besoin
    c.drawString(TEXT_LEFT_PAD, y_base, title)

    # Option: sous-titre (voir note ci-dessous)
    if subtitle:
        c.setFillColor(subtitle_color)
        c.setFont("Helvetica", 11)
        # place le sous-titre un peu sous le titre
        c.drawString(TEXT_LEFT_PAD, y_base - 5*mm, subtitle)

    c.restoreState()



def draw_header_banner_two_lines_with_color(c, page_w, page_h, title, subtitle, bg_color):
    """
    Dessine un bandeau d'en-tête avec titre et sous-titre positionnés précisément sur deux lignes
    et couleur de fond personnalisable
    """
    c.saveState()
    c.setFillColor(bg_color)
    c.rect(0, page_h - BANNER_H, BANNER_W, BANNER_H, stroke=0, fill=1)

    # Titre à 12 mm, sous-titre à 18 mm du haut
    y_title = page_h - 12*mm
    y_sub   = page_h - 18*mm
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(TEXT_LEFT_PAD, y_title, title)
    if subtitle:
        c.setFont("Helvetica", 11)
        c.drawString(TEXT_LEFT_PAD, y_sub, subtitle)
    c.restoreState()

def get_local_image(product_index, image_column, images_folder="images"):
    """Récupère l'image locale au lieu de la télécharger"""
    try:
        # Pattern corrigé pour correspondre aux noms de fichiers réels
        # Format: {index}_IMAGE 1_{hash}.jpg
        pattern = f"{product_index}_IMAGE 1_"
        print(f"🔍 [GET_IMAGE] Recherche pattern: {pattern}")
        
        for fname in os.listdir(images_folder):
            if fname.startswith(pattern):
                full_path = os.path.join(images_folder, fname)
                print(f"✅ [GET_IMAGE] Image trouvée: {fname}")
                return full_path
        
        print(f"❌ [GET_IMAGE] Aucune image trouvée pour pattern: {pattern}")
        return None
    except FileNotFoundError:
        print(f"❌ [GET_IMAGE] Dossier {images_folder} non trouvé")
        return None
    except Exception as e:
        print(f"❌ [GET_IMAGE] Erreur: {e}")
        return None

class CatalogDesigner:
    def __init__(self, style="modern", primary_color="#1976d2"):
        self.config = {
            "primary_color": colors.HexColor(primary_color),
            "accent_color": colors.HexColor("#EF4444"),
            "text_color": colors.black,
            "light_gray": colors.HexColor("#F3F4F6"),
        }

    def smart_truncate_description(self, text, max_chars=400):
        """Tronque intelligemment la description en respectant les phrases"""
        if not text or len(text) <= max_chars:
            return text or ""

        # Tronquer à max_chars
        truncated = text[:max_chars]
        
        # Chercher la fin de phrase la plus proche
        last_sentence = truncated.rfind('.')
        
        if last_sentence > max_chars * 0.7:  # Si on trouve une phrase pas trop courte
            return truncated[:last_sentence + 1]
        else:
            # Sinon, tronquer au dernier espace
            last_space = truncated.rfind(' ')
            if last_space > 0:
                return truncated[:last_space] + "..."
            return truncated[:max_chars - 3] + "..."

    def draw_wrapped_text(self, c, text, x, y, max_width_chars=85, line_height=0.35 * cm, max_lines=6):
        """Dessine du texte avec retour à la ligne automatique"""
        if not text:
            return y
        
        lines = textwrap.wrap(str(text), width=max_width_chars)
        current_y = y
        
        for line in lines[:max_lines]:
            c.drawString(x, current_y, line)
            current_y -= line_height
        
        return current_y

    def draw_product_card_premium(self, c, product, x, y, width=18 * cm, height=6.5 * cm, product_index=None, image_dpi=300, image_quality=95):
        """Dessine une carte produit avec style moderne"""
        print(f"🖼️  [DRAW_CARD] Traitement image avec DPI={image_dpi}, Quality={image_quality}")
        
        # Fond carte
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#E5E7EB"))
        c.rect(x, y, width, height, fill=1, stroke=1)

        # Zone image
        image_width = 4 * cm
        image_file = None
        
        if product_index is not None:
            image_file = get_local_image(product_index, "IMAGE 1")
            if image_file and os.path.exists(image_file):
                print(f"[OK] Image locale trouvée: {image_file}")

        if image_file and os.path.exists(image_file):
            try:
                print(f"🖼️ [DRAW] Tentative d'affichage de l'image: {image_file}")
                
                # ✅ UTILISEZ LES PARAMÈTRES DE QUALITÉ :
                c.drawImage(
                    image_file,
                    x + 0.3 * cm, y + 0.3 * cm,
                    width=image_width, height=height - 0.6 * cm,
                    preserveAspectRatio=True,
                    mask='auto'
                    # Note: dpi n'est pas un paramètre valide pour c.drawImage dans ReportLab
                )
                print(f"✅ [DRAW] Image affichée avec succès: {image_file}")
                
                # Debug: vérifier que l'image est bien dessinée
                print(f"🖼️ [DRAW] Image dessinée aux coordonnées: x={x + 0.3 * cm}, y={y + 0.3 * cm}, w={image_width}, h={height - 0.6 * cm}")
                    
            except Exception as e:
                print(f"❌ [ERREUR] Erreur affichage image {image_file}: {e}")
                print(f"❌ [ERREUR] Détails de l'erreur: {type(e).__name__}: {str(e)}")
                # Fallback: dessiner un rectangle gris avec texte
                c.setFillColor(self.config["light_gray"])
                c.rect(x + 0.3 * cm, y + 0.3 * cm, image_width, height - 0.6 * cm, fill=1, stroke=0)
                c.setFillColor(colors.HexColor("#9CA3AF"))
                c.setFont("Helvetica", 8)
                c.drawString(x + 0.3 * cm + image_width / 2 - 15, y + height / 2, "IMAGE")
        else:
            print(f"[ATTENTION] Aucune image trouvée pour le produit {product_index}")
            c.setFillColor(self.config["light_gray"])
            c.rect(x + 0.3 * cm, y + 0.3 * cm, image_width, height - 0.6 * cm, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#9CA3AF"))
            c.setFont("Helvetica", 8)
            c.drawString(x + 0.3 * cm + image_width / 2 - 15, y + height / 2, "IMAGE")

        # Contenu
        content_x = x + image_width + 0.8 * cm
        current_y = y + height - 0.5 * cm

        # Titre avec retour à la ligne si trop long
        c.setFillColor(self.config["text_color"])
        c.setFont("Helvetica-Bold", 13)
        title = str(product.get('title', product.get('TITRE', 'Produit sans nom')))
        print(f"DEBUG - Titre: {title}")
        
        # Découper le titre si trop long (max 40 caractères par ligne)
        title_lines = textwrap.wrap(title, width=40)
        for line in title_lines[:2]:  # Maximum 2 lignes pour le titre
            c.drawString(content_x, current_y, line)
            current_y -= 0.6 * cm  # Augmentation de l'interlignage de 0.4 à 0.6 cm
        current_y -= 0.4 * cm  # Espacement supplémentaire après le titre

        # Prix
        c.setFillColor(self.config["accent_color"])
        c.setFont("Helvetica-Bold", 16)
        raw_price = product.get('price', product.get('PRIX', 'Prix N/A'))
        print(f"DEBUG - Prix brut: {raw_price}")
        
        # Normaliser le prix avec la nouvelle fonction
        price_info = normalize_price(raw_price)
        normalized_price = price_info['display']
        print(f"DEBUG - Prix normalisé: {normalized_price}")
        
        # Ajouter un carré devant le prix
        price_with_square = f"■ {normalized_price}"
        c.drawString(content_x, current_y, price_with_square)
        current_y -= 1 * cm

        # Description
        c.setFillColor(self.config["text_color"])
        c.setFont("Helvetica", 9)
        description = self.smart_truncate_description(
            product.get('description', product.get('DESCRIPTION', '')),
            max_chars=400  # Augmentation de 250 à 400 caractères
        )
        print(f"DEBUG - Description: {description[:50]}...")
        current_y = self.draw_wrapped_text(
            c, description,
            content_x, current_y,
            max_width_chars=85,  # Augmentation de 70 à 85 caractères par ligne
            max_lines=6  # Augmentation de 5 à 6 lignes
        ) - 0.3 * cm

        # Metadata
        c.setFillColor(colors.HexColor("#6B7280"))
        c.setFont("Helvetica", 8)
        ref = product.get('Ref', product.get('ref', product.get('RÉFÉRENCE', 'N/A')))
        qty = product.get('Quantité', product.get('quantity', product.get('QUANTITÉ', 'N/A')))
        material = product.get('Matériaux', product.get('material', product.get('MATÉRIAUX', 'N/A')))
        meta_text = f"■ Qté: {qty} • ■ Réf: {ref} • ■ {material}"
        c.drawString(content_x, y + 0.3 * cm, meta_text)

    def draw_catalog_header(self, c, page_num, total_pages, titre="Catalogue", sous_titre="", is_cover=False):
        # Ne pas afficher le header sur la couverture
        if is_cover:
            return
        
        # Utiliser la nouvelle fonction de bandeau avec la couleur principale configurée
        page_width, page_height = A4
        draw_header_banner_two_lines_with_color(c, page_width, page_height, titre, sous_titre, self.config["primary_color"])

        # Numéro de page centré en bas de page en noir (commencer à 2)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 10)
        c.drawCentredString(21 * cm / 2, 1 * cm, f"Page {page_num + 1}")

def generate_modern_catalog(products, filename="catalog_modern.pdf", titre="Catalogue", sous_titre="", logo_path=None, cover_path=None, products_per_page=4, bg_color="#F0F0F0", primary_color="#1976d2", return_bytes=False):
    print(f"[DEBUT] - {len(products)} produits")
    designer = CatalogDesigner("modern", primary_color)
    
    if return_bytes:
        # Génération en mémoire
        from io import BytesIO
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
    else:
        # Génération sur fichier
        c = canvas.Canvas(filename, pagesize=A4)
    print("[OK] Canvas créé")
    
    # Couverture (sans fond coloré)
    print("[PAGE] Génération de la couverture...")
    draw_modern_cover(c, titre, sous_titre, logo_path, cover_path)
    print("[OK] Couverture OK")
    draw_snapcatalog_filigrane(c, 1, A4)  # Page 1 (couverture)
    c.showPage()

    # Produits
    page_width, page_height = A4
    current_page = 1
    total_pages = (len(products) + products_per_page - 1) // products_per_page

    print(f"[PROG] Progression: 0% - Début du traitement des {len(products)} produits")

    # Utiliser la même logique améliorée que generate_modern_catalog_with_progress
    def paint_page_background():
        c.setFillColor(colors.HexColor(bg_color))
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    # Marges et paramètres d'empilement (comme dans la version améliorée)
    left_margin = right_margin = 1.20 * cm
    top_margin = 3.0 * cm      # un peu plus haut pour l'en-tête
    bottom_margin = 2.0 * cm
    GAP = 0.5 * cm             # écart fixe entre cartes

    # Aire utile verticale
    available_height = page_height - top_margin - bottom_margin

    # Hauteur de carte: au moins 6.5 cm, sinon calculée pour tenir avec les gaps
    if products_per_page > 0:
        card_height_auto = (available_height - (products_per_page - 1) * GAP) / products_per_page
        # FIXÉ: Suppression du minimum de 6.5cm qui causait les débordements
        card_height = card_height_auto
        # Sécurité: ne pas dépasser l'aire utile
        card_height = min(card_height, available_height)
    else:
        card_height = 6.5 * cm  # fallback

    card_width = page_width - left_margin - right_margin

    # DEBUG: Afficher les calculs de hauteur
    print(f"[DEBUG] Calculs de hauteur:")
    print(f"  - page_height: {page_height/cm:.1f}cm")
    print(f"  - top_margin: {top_margin/cm:.1f}cm")
    print(f"  - bottom_margin: {bottom_margin/cm:.1f}cm")
    print(f"  - available_height: {available_height/cm:.1f}cm")
    print(f"  - products_per_page: {products_per_page}")
    print(f"  - GAP: {GAP/cm:.1f}cm")
    print(f"  - card_height_auto: {card_height_auto/cm:.1f}cm")
    print(f"  - card_height_final: {card_height/cm:.1f}cm")
    
    # Vérification: est-ce que products_per_page cartes rentrent vraiment ?
    total_needed = products_per_page * card_height + (products_per_page - 1) * GAP
    print(f"  - Espace total nécessaire pour {products_per_page} cartes: {total_needed/cm:.1f}cm")
    print(f"  - Espace disponible: {available_height/cm:.1f}cm")
    print(f"  - Marge restante: {(available_height - total_needed)/cm:.1f}cm")

    # Dessine en haut -> bas. y attendu par draw_product_card_premium = bas de la carte
    def y_bottom_for_index_on_page(index_on_page: int) -> float:
        y_top = page_height - top_margin
        return y_top - index_on_page * (card_height + GAP) - card_height

    for i, product in enumerate(products):
        progress = int((i / max(1, len(products))) * 100)
        print(f"[PROD] Produit {i + 1}/{len(products)} ({progress}%): {product.get('title', product.get('TITRE', 'NO NAME'))[:50]}")

        # Début d'une nouvelle page produits ? (logique corrigée)
        if i % products_per_page == 0:
            if i > 0:
                # Finir la page précédente, passer à la suivante
                # Ajouter le filigrane avant de changer de page
                draw_snapcatalog_filigrane(c, current_page + 1, A4)
                c.showPage()
                paint_page_background()
                current_page += 1
            # En-tête + filigrane de la page produits courante
            designer.draw_catalog_header(c, current_page, total_pages, titre, sous_titre)

        index_on_page = i % products_per_page
        x = left_margin
        y = y_bottom_for_index_on_page(index_on_page)

        # Sécurité: si jamais ça déborde (ne devrait pas avec le calcul), on force un saut de page
        if y < bottom_margin:
            # Ajouter le filigrane avant de changer de page
            draw_snapcatalog_filigrane(c, current_page + 1, A4)
            c.showPage()
            paint_page_background()
            current_page += 1
            designer.draw_catalog_header(c, current_page, total_pages, titre, sous_titre)
            index_on_page = 0
            y = y_bottom_for_index_on_page(index_on_page)

        # Dessin de la carte
        designer.draw_product_card_premium(
            c, product, x, y,
            width=card_width, height=card_height,
            product_index=i,
            image_dpi=image_dpi,      # ✅ Transmettre le DPI
            image_quality=image_quality  # ✅ Transmettre la qualité
        )

    # Ajouter le filigrane sur la dernière page
    draw_snapcatalog_filigrane(c, current_page + 1, A4)
    print("[SAVE] Sauvegarde du PDF...")
    c.save()
    print("[OK] FINI ! - 100%")
    
    if return_bytes:
        buffer.seek(0)
        return buffer.getvalue()
    else:
        return filename

def generate_modern_catalog_with_progress(
    products, filename="catalog_modern.pdf", titre="Catalogue", sous_titre="",
    logo_path=None, cover_path=None, progress_callback=None,
    products_per_page=4, bg_color="#F0F0F0", primary_color="#1976d2", 
    return_bytes=False, image_dpi=300, image_quality=95  # ✅ AJOUTEZ CES PARAMÈTRES
):
    """Version avec progression détaillée pour l'interface Streamlit"""
    print(f"🎨 [PDF_DESIGNER] Paramètres reçus: DPI={image_dpi}, Quality={image_quality}")
    print(f"[DEBUT] - {len(products)} produits")
    designer = CatalogDesigner("modern", primary_color)

    # Canvas: mémoire ou fichier
    if return_bytes:
        from io import BytesIO
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
    else:
        c = canvas.Canvas(filename, pagesize=A4)
    print("[OK] Canvas créé")

    # 1) Couverture
    print("[PAGE] Génération de la couverture...")
    draw_modern_cover(c, titre, sous_titre, logo_path, cover_path)
    print("[OK] Couverture OK")
    # Filigrane de la page 1 (couverture)
    draw_snapcatalog_filigrane(c, 1, A4)
    # Passe à la première page produits
    c.showPage()

    # 2) Fond de page produits (appliqué page par page)
    page_width, page_height = A4
    def paint_page_background():
        c.setFillColor(colors.HexColor(bg_color))
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    paint_page_background()

    # Marges et paramètres d'empilement
    left_margin = right_margin = 1.20 * cm
    top_margin = 3.0 * cm      # un peu plus haut pour l'en-tête
    bottom_margin = 2.0 * cm
    GAP = 0.5 * cm             # écart fixe entre cartes

    # Aire utile verticale
    available_height = page_height - top_margin - bottom_margin

    # Hauteur de carte: au moins 6.5 cm, sinon calculée pour tenir avec les gaps
    if products_per_page > 0:
        card_height_auto = (available_height - (products_per_page - 1) * GAP) / products_per_page
        # FIXÉ: Suppression du minimum de 6.5cm qui causait les débordements
        card_height = card_height_auto
        # Sécurité: ne pas dépasser l'aire utile
        card_height = min(card_height, available_height)
    else:
        card_height = 6.5 * cm  # fallback

    card_width = page_width - left_margin - right_margin

    # Pagination
    current_page = 1  # 1 = couverture
    total_pages = (len(products) + products_per_page - 1) // max(1, products_per_page)

    print(f"[PROG] Progression: 0% - Début du traitement des {len(products)} produits")

    # Dessine en haut -> bas. y attendu par draw_product_card_premium = bas de la carte
    def y_bottom_for_index_on_page(index_on_page: int) -> float:
        y_top = page_height - top_margin
        return y_top - index_on_page * (card_height + GAP) - card_height

    for i, product in enumerate(products):
        # Progress callback amélioré avec plus de détails
        if progress_callback:
            # Appel du callback avec progression détaillée
            progress_callback(i + 1, len(products), 1.0)
            
            # Affichage console détaillé
            progress = int((i / max(1, len(products))) * 100)
            print(f"[PROD] Produit {i + 1}/{len(products)} ({progress}%): {product.get('title', product.get('TITRE', 'NO NAME'))[:50]}")
            
            # Affichage des étapes intermédiaires
            if i == 0:
                print(f"[PROG] 🚀 Début du traitement des produits - 0%")
            elif i == len(products) // 4:
                print(f"[PROG] 📦 25% des produits traités")
            elif i == len(products) // 2:
                print(f"[PROG] ⚡ 50% des produits traités")
            elif i == 3 * len(products) // 4:
                print(f"[PROG] 🔥 75% des produits traités")
            elif i == len(products) - 1:
                print(f"[PROG] 🏁 Dernier produit en cours...")
        else:
            # Affichage console simple si pas de callback
            progress = int((i / max(1, len(products))) * 100)
            print(f"[PROD] Produit {i + 1}/{len(products)} ({progress}%): {product.get('title', product.get('TITRE', 'NO NAME'))[:50]}")

        # Début d'une nouvelle page produits ?
        if i % products_per_page == 0:
            if i > 0:
                # Finir la page précédente, passer à la suivante
                c.showPage()
                paint_page_background()
                current_page += 1

            # En-tête + filigrane de la page produits courante
            designer.draw_catalog_header(c, current_page, total_pages, titre, sous_titre)
            # current_page + 1 car current_page compte depuis la couverture
            draw_snapcatalog_filigrane(c, current_page + 1, A4)

        index_on_page = i % products_per_page
        x = left_margin
        y = y_bottom_for_index_on_page(index_on_page)

        # Sécurité: si jamais ça déborde (ne devrait pas avec le calcul), on force un saut de page
        if y < bottom_margin:
            c.showPage()
            paint_page_background()
            current_page += 1
            designer.draw_catalog_header(c, current_page, total_pages, titre, sous_titre)
            draw_snapcatalog_filigrane(c, current_page + 1, A4)
            index_on_page = 0
            y = y_bottom_for_index_on_page(index_on_page)

        # Dessin de la carte
        designer.draw_product_card_premium(
            c, product, x, y,
            width=card_width, height=card_height,
            product_index=i,
            image_dpi=image_dpi,      # ✅ Transmettre le DPI
            image_quality=image_quality  # ✅ Transmettre la qualité
        )

    # Filigrane de la dernière page produits
    draw_snapcatalog_filigrane(c, current_page + 1, A4)

    # Progression finale avec callback
    if progress_callback:
        progress_callback(len(products) + 1, len(products), 1.0)  # Étape de finalisation
        print(f"[PROG] 🔧 Finalisation du PDF...")

    print("[SAVE] Sauvegarde du PDF...")
    c.save()
    print("[OK] FINI ! - 100%")

    if return_bytes:
        buffer.seek(0)
        return buffer.getvalue()
    else:
        return filename

def generate_pdf_with_quality(
    products, filename="catalog_modern.pdf", titre="Catalogue", sous_titre="",
    logo_path=None, cover_path=None, quality="hd", products_per_page=4, 
    bg_color="#F0F0F0", primary_color="#1976d2", output="file", progress_callback=None
):
    """
    Génère un catalogue PDF avec différentes qualités d'image
    
    Args:
        products: Liste des produits
        filename: Nom du fichier de sortie
        titre: Titre du catalogue
        sous_titre: Sous-titre du catalogue
        logo_path: Chemin vers le logo
        cover_path: Chemin vers l'image de couverture
        quality: Qualité du PDF ('hd', 'medium', 'bd')
        products_per_page: Nombre de produits par page
        bg_color: Couleur de fond des pages
        primary_color: Couleur principale
        output: Type de sortie ('file' ou 'bytes')
        progress_callback: Callback pour la progression (current, total, stage_percent)
    
    Returns:
        Chemin du fichier ou bytes selon output
    """
    
    # Configuration de la qualité
    quality_config = {
        'hd': {'dpi': 300, 'image_quality': 95},
        'medium': {'dpi': 150, 'image_quality': 75}, 
        'bd': {'dpi': 72, 'image_quality': 50}
    }
    
    config = quality_config.get(quality, quality_config['hd'])
    print(f"[QUALITE] Génération en qualité {quality.upper()}")
    print(f"[CONFIG] DPI: {config['dpi']}, Quality: {config['image_quality']}")
    
    return_bytes = (output == "bytes")
    
    # AJOUTEZ LES PARAMÈTRES DE QUALITÉ ICI :
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
        progress_callback=progress_callback,  # ✅ Transmettre le callback de progression
        # ✅ AJOUTEZ CES LIGNES :
        image_dpi=config['dpi'],
        image_quality=config['image_quality']
    )