# utils/text_processing.py
from reportlab.pdfbase import pdfmetrics
import re

# Constantes pour les espaces
NBSP = '\u00A0'  # Espace insécable
NARROW_NBSP = '\u202F'  # Espace insécable fine

def wrap_lines_by_width(text, font_name, font_size, max_width_pts, max_lines=2):
    """
    Coupe le texte par mots en veillant à ne jamais dépasser max_width_pts.
    Retourne (lines, real_max_width) avec au plus max_lines lignes.
    Plus robuste que la version précédente (ne perd pas de mots dupliqués).
    """
    words = text.split()
    lines = []
    cur = []
    real_max = 0.0

    def width_of(ws):
        s = " ".join(ws)
        return pdfmetrics.stringWidth(s, font_name, font_size)

    for w in words:
        test = cur + [w]
        if width_of(test) <= max_width_pts or not cur:
            cur = test
        else:
            # on fige la ligne courante
            w_cur = width_of(cur)
            real_max = max(real_max, w_cur)
            lines.append(" ".join(cur))
            cur = [w]
            if len(lines) >= max_lines - 1:
                # dernière ligne: on met tout le reste
                rest = " ".join([w] + words[words.index(w)+1:])
                if rest:
                    lines.append(rest)
                break

    if len(lines) < max_lines and cur:
        w_cur = width_of(cur)
        real_max = max(real_max, w_cur)
        lines.append(" ".join(cur))

    # recalcule la largeur réelle max
    for ln in lines:
        real_max = max(real_max, pdfmetrics.stringWidth(ln, font_name, font_size))

    # tronque si plus de lignes que max_lines (sécurité)
    return lines[:max_lines], real_max

def truncate(txt, n=50):
    txt = str(txt)
    return (txt[:n] + '...') if len(txt) > n else txt

def _strip_spaces(s: str) -> str:
    if s is None:
        return ""
    # Normalise les espaces: remplace fine/insécables par espace simple, compresse
    s = s.replace(NBSP, " ").replace(NARROW_NBSP, " ")
    s = re.sub(r"\s+", " ", s.strip())
    return s
