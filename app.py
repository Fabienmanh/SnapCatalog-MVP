import io, re, requests, os, tempfile, time, random, logging
from io import BytesIO
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import streamlit as st
import pandas as pd
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.platypus.doctemplate import LayoutError

# Import pour compression PDF
try:
    from pypdf2 import PdfReader, PdfWriter
    HAVE_PYPDF2 = True
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter
        HAVE_PYPDF2 = True
    except ImportError:
        HAVE_PYPDF2 = False

# Utils
from utils.font_manager import download_and_register_fonts, validate_background_color
from utils.helpers import update_progress_detailed
from utils.image_processing import open_image
from utils.data_processing import save_feedback_to_csv, save_feedback_to_sqlite

# Générateur PDF moderne (local)
from pdf_designer import generate_pdf_with_quality

# Import de l'upload handler
from upload_handler import UploadHandler

# Aperçu PDF (optionnel)
try:
    from pdf2image import convert_from_path
    HAVE_PDF2IMAGE = True
except Exception:
    HAVE_PDF2IMAGE = False

# ----- HTTP + CSV Etsy utils -----
log = logging.getLogger(__name__)

# Configuration de logging pour Streamlit Cloud
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

# Configuration spécifique pour Streamlit Cloud
if os.getenv("STREAMLIT_CLOUD"):
    # Désactiver les logs de debug en production
    logging.getLogger().setLevel(logging.WARNING)
    # Limiter la taille des fichiers temporaires
    os.environ["TMPDIR"] = "/tmp"

class HostRateLimiter:
    def __init__(self, rate_per_sec=2, burst=2):
        self.allowance = defaultdict(lambda: burst)
        self.last_check = defaultdict(lambda: time.time())
        self.rate = rate_per_sec
        self.burst = burst

    def wait(self, host):
        now = time.time()
        elapsed = now - self.last_check[host]
        self.last_check[host] = now
        self.allowance[host] = min(self.burst, self.allowance[host] + elapsed * self.rate)
        if self.allowance[host] < 1.0:
            # attendre le temps nécessaire + un petit jitter
            need = (1.0 - self.allowance[host]) / self.rate
            time.sleep(need + random.uniform(0, 0.15))
            self.allowance[host] = 0
        else:
            self.allowance[host] -= 1.0

def http_session():
    s = requests.Session()
    r = Retry(
        total=2, backoff_factor=0.8,
        status_forcelist=[429,500,502,503,504],
        allowed_methods=["GET", "HEAD"]
    )
    s.mount("http://", HTTPAdapter(max_retries=r))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update({"User-Agent": "SnapCatalog/1.0 (+contact@example.com)"})
    return s

rate = HostRateLimiter(rate_per_sec=1.0, burst=1)  # 1 req/s par hôte

def fetch_image_politely(url, timeout=8, max_bytes=2_000_000):
    host = urlparse(url).netloc
    rate.wait(host)
    s = http_session()
    # Si vous avez déjà un ETag/Last-Modified en cache, ajoutez If-None-Match / If-Modified-Since ici
    with s.get(url, timeout=timeout, stream=True, allow_redirects=True) as r:
        if r.status_code in (403, 429):
            # Backoff manuel plus long + message clair
            wait = int(r.headers.get("Retry-After", "4"))
            time.sleep(wait + random.uniform(0, 0.5))
            raise RuntimeError(f"Accès bloqué par l'hôte ({r.status_code}). Réduisez la cadence ou utilisez des copies locales.")
        r.raise_for_status()
        buf, total = io.BytesIO(), 0
        for chunk in r.iter_content(32_768):
            if not chunk: break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Image trop volumineuse")
            buf.write(chunk)
        return buf.getvalue()

# Configuration des timeouts pour Streamlit Cloud
if os.getenv("STREAMLIT_CLOUD"):
    # Timeouts plus courts pour éviter les timeouts de Streamlit
    IMAGE_TIMEOUT = 5
    MAX_IMAGE_SIZE = 1_000_000  # 1MB max
    RATE_LIMIT = 0.5  # Plus lent pour éviter les blocages
else:
    IMAGE_TIMEOUT = 8
    MAX_IMAGE_SIZE = 2_000_000  # 2MB max
    RATE_LIMIT = 1.0

# Mise à jour des paramètres
rate = HostRateLimiter(rate_per_sec=RATE_LIMIT, burst=1)

class Circuit:
    def __init__(self, threshold=5, cooldown=600):
        self.errors = defaultdict(int)
        self.block_until = defaultdict(float)
        self.threshold = threshold
        self.cooldown = cooldown

    def check(self, host):
        if time.time() < self.block_until[host]:
            raise RuntimeError(f"Hôte {host} en cooldown, réessayez plus tard.")
    def record(self, host, ok):
        if ok:
            self.errors[host] = 0
        else:
            self.errors[host] += 1
            if self.errors[host] >= self.threshold:
                self.block_until[host] = time.time() + self.cooldown

circuit = Circuit()

def safe_fetch(url):
    host = urlparse(url).netloc
    circuit.check(host)
    try:
        data = fetch_image_politely(url, timeout=IMAGE_TIMEOUT, max_bytes=MAX_IMAGE_SIZE)
        circuit.record(host, True)
        return data
    except Exception:
        circuit.record(host, False)
        raise

def compress_pdf(pdf_bytes):
    """Compresse un PDF en utilisant PyPDF2"""
    if not HAVE_PYPDF2:
        log.warning("PyPDF2 non disponible, compression ignorée")
        return pdf_bytes
    
    try:
        log.info("Début compression PDF")
        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()
        
        for page in reader.pages:
            writer.add_page(page)
        
        # Préserver les métadonnées si elles existent
        if reader.metadata:
            writer.add_metadata(reader.metadata)
        
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        compressed_bytes = output.getvalue()
        original_size = len(pdf_bytes)
        compressed_size = len(compressed_bytes)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        log.info(f"PDF compressé: {original_size/1024/1024:.2f}MB -> {compressed_size/1024/1024:.2f}MB ({compression_ratio:.1f}% de réduction)")
        
        return compressed_bytes
    except Exception as e:
        log.warning(f"Erreur compression PDF: {e}, retour du PDF original")
        return pdf_bytes

IMG_COL_RE = re.compile(r"^\s*IMAGE\s*\d+\s*$", re.I)
URL_RE = re.compile(r"^https?://[^\s\"']+$")

def fetch_csv_bytes(url, timeout=12, max_bytes=15_000_000):
    with http_session().get(url, timeout=timeout, stream=True, allow_redirects=True) as r:
        r.raise_for_status()
        buf = io.BytesIO()
        total = 0
        for chunk in r.iter_content(1024*32):
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"CSV trop volumineux (> {max_bytes/1_000_000:.1f} Mo)")
            buf.write(chunk)
        buf.seek(0)
        return buf

def read_etsy_csv(url):
    raw = fetch_csv_bytes(url)
    # Essai 1: UTF‑8 strict
    try:
        df = pd.read_csv(
            raw,
            sep=",", quotechar='"', engine="python",
            on_bad_lines="skip",
        )
    except UnicodeDecodeError:
        # Essai 2: CP1252
        raw.seek(0)
        df = pd.read_csv(
            raw,
            sep=",", quotechar='"', engine="python",
            encoding="cp1252",
            on_bad_lines="skip",
        )
    # Normalisation des noms de colonnes
    df.columns = [c.strip().upper() for c in df.columns]
    # Renommer quelques colonnes françaises fréquentes
    df = df.rename(columns={
        "TITRE": "TITLE",
        "DESCRIPTION": "DESCRIPTION",
        "PRIX": "PRICE",
        "CODE_DEVISE": "CURRENCY_CODE",
        "QUANTITÉ": "QUANTITY",
        "RÉFÉRENCE": "SKU",
    })
    # Collecte des colonnes image (IMAGE 1..10)
    img_cols = [c for c in df.columns if IMG_COL_RE.match(c)]

    def extract_urls(row):
        urls = []
        for c in img_cols:
            val = str(row.get(c, "")).strip()
            if val and URL_RE.match(val):
                urls.append(val)
        return urls

    df["IMAGE_URLS"] = df.apply(extract_urls, axis=1)
    df = df[df["IMAGE_URLS"].map(len) > 0].reset_index(drop=True)
    return df

# Exécuter une fonction avec délai maximum
def run_with_timeout(fn, timeout, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args, **kwargs)
        return fut.result(timeout=timeout)

# Fonction de génération sécurisée avec wrapper direct
def safe_generate_pdf(products, filename, titre, sous_titre, logo_path, cover_path,
                      quality, products_per_page, bg_color, primary_color,
                      output="bytes", progress_callback=None):
    # Adapter si generate_pdf_with_quality a une signature différente
    return generate_pdf_with_quality(
        products=products,
        filename=filename,
        titre=titre,
        sous_titre=sous_titre,
        logo_path=logo_path,
        cover_path=cover_path,
        quality=quality,
        products_per_page=products_per_page,
        bg_color=bg_color,
        primary_color=primary_color,
        output=output,
        progress_callback=progress_callback
    )

# Réglages PDF simples (mode images URL)
PAGE_W, PAGE_H = A4
MARGIN = 36
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Snacatalog/1.0)",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}
IMG_COLS = [f"IMAGE {i}" for i in range(1, 11)]
TITLE_COL = "TITRE"
DESC_COL  = "DESCRIPTION"
PRICE_COL = "PRIX"
CURR_COL  = "CODE_DEVISE"
REF_COL   = "RÉFÉRENCE"

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_image_bytes(url: str) -> bytes | None:
    url = (url or "").strip()
    if not url:
        return None
    try:
        log.info(f"Téléchargement image: {url[:50]}...")
        data = safe_fetch(url)
        log.info(f"Image téléchargée avec succès: {len(data)} bytes")
        return data
    except Exception as e:
        log.warning(f"Échec téléchargement image {url[:50]}: {e}")
        return None

def load_pil_image_from_url(url: str) -> Image.Image | None:
    data = fetch_image_bytes(url)
    if not data:
        return None
    try:
        img = Image.open(BytesIO(data))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        return img
    except Exception:
        return None

IMG_URL_RE = re.compile(
    r"https?://[^\s\"']+?\.(?:png|jpe?g|webp|gif|bmp|tiff)(?:\?[^\s\"']*)?",
    re.I
)

def extract_image_urls_from_cell(cell: str) -> list[str]:
    s = str(cell or "")
    s = s.replace(";ps://", "https://")
    urls = IMG_URL_RE.findall(s)
    out, seen = [], set()
    for u in urls:
        u = u.strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_row_image_urls(row: pd.Series) -> list[str]:
    urls = []
    for col in IMG_COLS:
        if col in row:
            urls.extend(extract_image_urls_from_cell(row[col]))
    return urls[:4]

def draw_image_keep_aspect(c, pil_img, x, y, max_w, max_h):
    w, h = pil_img.size
    scale = min(max_w / w, max_h / h)
    nw, nh = w * scale, h * scale
    c.drawImage(ImageReader(pil_img), x, y, width=nw, height=nh, preserveAspectRatio=True, mask='auto')
    return nw, nh

def build_pdf_from_df(df: pd.DataFrame, progress_callback=None) -> bytes:
    log.info(f"Début génération PDF pour {len(df)} produits")
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = PAGE_H - MARGIN
    max_img_w = PAGE_W - 2 * MARGIN
    max_img_h = 260
    
    total_products = len(df)
    processed = 0

    for idx, (_, row) in enumerate(df.iterrows()):
        if progress_callback:
            progress = (idx + 1) / total_products
            progress_callback(progress, f"Traitement produit {idx + 1}/{total_products}")
        
        log.info(f"Traitement produit {idx + 1}/{total_products}")
        title = (str(row.get(TITLE_COL, "") or "").strip()) or "Sans titre"
        desc  = str(row.get(DESC_COL, "") or "").strip()
        price = str(row.get(PRICE_COL, "") or "").strip()
        curr  = str(row.get(CURR_COL, "") or "").strip()
        ref   = str(row.get(REF_COL, "") or "").strip()
        urls  = extract_row_image_urls(row)

        block_min_h = max_img_h + 80
        if y - block_min_h < MARGIN:
            c.showPage()
            y = PAGE_H - MARGIN

        cols = 2
        cell_w = (max_img_w - 12) / cols
        cell_h = (max_img_h - 12) / 2
        top_y = y

        for idx, url in enumerate(urls):
            try:
                pil_img = load_pil_image_from_url(url)
                r = idx // cols
                cidx = idx % cols
                cx = MARGIN + cidx * (cell_w + 12)
                cy = top_y - (r + 1) * (cell_h + 12)
                if pil_img:
                    draw_image_keep_aspect(c, pil_img, cx + 6, cy + 6, cell_w - 12, cell_h - 12)
                else:
                    c.setFillColorRGB(0.92, 0.92, 0.92)
                    c.rect(cx, cy, cell_w, cell_h, fill=1, stroke=0)
                    c.setFillColorRGB(0, 0, 0)
                    c.setFont("Helvetica", 9)
                    c.drawString(cx + 8, cy + 8, "Image indisponible")
            except Exception as e:
                log.warning(f"Erreur traitement image {url}: {e}")
                # Dessiner un placeholder d'erreur
                r = idx // cols
                cidx = idx % cols
                cx = MARGIN + cidx * (cell_w + 12)
                cy = top_y - (r + 1) * (cell_h + 12)
                c.setFillColorRGB(0.95, 0.8, 0.8)
                c.rect(cx, cy, cell_w, cell_h, fill=1, stroke=0)
                c.setFillColorRGB(0.8, 0, 0)
                c.setFont("Helvetica", 8)
                c.drawString(cx + 4, cy + 4, "Erreur image")

        if not urls:
            cy = top_y - cell_h
            c.setFillColorRGB(0.95, 0.95, 0.95)
            c.rect(MARGIN, cy, max_img_w, cell_h, fill=1, stroke=0)
            c.setFillColorRGB(0, 0, 0)

        y = top_y - max(2 * (cell_h + 12), cell_h + 12) - 8
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN, y, title[:120])
        y -= 16

        small = []
        if ref:
            small.append(f"Réf: {ref}")
        if price:
            small.append(f"Prix: {price} {curr}".strip())

        c.setFont("Helvetica", 9)
        if small:
            c.drawString(MARGIN, y, " · ".join(small))
            y -= 12

        if desc:
            c.setFont("Helvetica", 9)
            c.drawString(MARGIN, y, desc.replace("\n", " ")[:180])
            y -= 14

        y -= 12
        if y < MARGIN + 150:
            c.showPage()
            y = PAGE_H - MARGIN

    c.save()
    buf.seek(0)
    result = buf.read()
    log.info(f"PDF généré avec succès: {len(result)} bytes")
    return result

# Configuration de la page Streamlit
st.set_page_config(
    page_title="SnapCatalog, votre catalogue en un clin d'œil", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Configuration pour éviter les timeouts sur Streamlit Cloud
if os.getenv("STREAMLIT_CLOUD"):
    st.set_option('deprecation.showPyplotGlobalUse', False)
    st.set_option('deprecation.showfileUploaderEncoding', False)

# État initial pour éviter la double génération
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None
    st.session_state.pdf_name = "catalogue_personnalise.pdf"
if "pdf_tmp_path" not in st.session_state:
    st.session_state.pdf_tmp_path = None
st.title("📒 SnapCatalog — Générateur de PDF produits")
st.write("Importe ton fichier produits (Shopify, Etsy…), sélectionne tes colonnes, choisis un template et génère ton catalogue au format PDF!")

def detect_image_type(df: pd.DataFrame) -> tuple[str, str]:
    # Heuristique simple: si on voit "http" dans une colonne IMAGE, on dit "url"
    image_cols = [c for c in df.columns if c.upper().startswith("IMAGE")]
    sample = " ".join(df.get(image_cols[0], "").astype(str)[:50]) if image_cols else ""
    if "http" in sample.lower():
        return "url", "URLs détectées"
    return "local", "Images locales"

# Mode par défaut
generation_mode = "Mode standard (avec images locales)"

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
        # Détection automatique du type d'images (silencieuse)
        image_type, detection_message = detect_image_type(df)
        
        # Option pour forcer le mode manuellement (masquée pour l'instant)
        # force_manual = st.checkbox("🔧 Forcer le choix manuel du mode", value=False)
        force_manual = False  # Désactivé temporairement
        
        if force_manual:
            st.warning("⚠️ Mode manuel activé - Vous pouvez choisir le mode indépendamment de la détection")
            generation_mode = st.radio(
                "Choisissez le mode de génération :",
                ["Mode standard (avec images locales)", "Mode images URL (pour CSV Etsy avec URLs)"],
                index=0
            )
        else:
            # Détection automatique silencieuse
            if image_type == "url":
                generation_mode = "Mode images URL (pour CSV Etsy avec URLs)"
            elif image_type == "local":
                generation_mode = "Mode standard (avec images locales)"
            elif image_type == "mixed":
                generation_mode = "Mode standard (avec images locales)"
            else:
                generation_mode = "Mode standard (avec images locales)"
        
        # --- Détection automatique des colonnes "utiles" ---
        auto_columns = []
        for name in ["title", "titre", "description", "prix", "code_devise", "référence", "image 1"]:
            for col in df.columns:
                if name.lower() == col.lower():
                    auto_columns.append(col)

        st.subheader("Colonnes à inclure dans le PDF")
        st.info("ℹ️ Pour une meilleure lisibilité, seule la première image (Image 1) peut être utilisée selon le template standard; le mode Etsy (URLs) peut en insérer jusqu'à 4.")
        choix_cols = st.multiselect(
            "Choisis les colonnes (pré-sélection automatique si détectées) :",
            options=list(df.columns),
            default=sorted(set(auto_columns))
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
        
        # Limite pour les tests en mode développement
        max_products = st.number_input(
            "Limite de produits pour les tests (0 = tous)", 
            min_value=0, 
            max_value=total_products, 
            value=min(50, total_products) if total_products > 50 else 0,
            help="Limitez le nombre de produits pour accélérer les tests"
        )
        
        if max_products > 0:
            filtered_df = filtered_df.head(max_products)
            total_products = len(filtered_df)
            st.warning(f"⚠️ Mode test: seulement {total_products} produits seront traités")
        
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

if generation_mode == "Mode images URL (pour CSV Etsy avec URLs)":
    # Mode images URL
    st.info("📡 Mode images URL activé - Les images seront téléchargées depuis les URLs du CSV")
    
    # Option d'aperçu pour le mode images URL
    preview = st.checkbox("Afficher un aperçu (lent)", value=False, disabled=not HAVE_PDF2IMAGE)
    if not HAVE_PDF2IMAGE and preview:
        st.info("pdf2image non disponible pour l'aperçu.")
    
    if st.button("Générer le PDF avec images URL 🚀"):
        log.info("Début génération PDF mode images URL")
        st.session_state.progress_bar = st.progress(0)
        st.session_state.status_text = st.empty()
        progress_bar = st.session_state.progress_bar
        status_text = st.session_state.status_text

        try:
            def update_progress(progress, message):
                progress_bar.progress(progress)
                status_text.text(message)
                log.info(f"Progression: {progress:.1%} - {message}")

            update_progress(0.05, "🔄 Préparation des données...")
            
            for col in IMG_COLS:
                if col not in filtered_df.columns:
                    filtered_df[col] = ""

            update_progress(0.10, "📡 Début téléchargement des images...")
            
            # Utiliser le callback de progression dans build_pdf_from_df
            pdf_bytes = build_pdf_from_df(filtered_df, progress_callback=update_progress)
            
            # Compression du PDF
            update_progress(0.90, "🗜️ Compression du PDF...")
            pdf_bytes = compress_pdf(pdf_bytes)
            
            st.session_state.pdf_bytes = pdf_bytes
            st.session_state.pdf_name = "catalog_images_url.pdf"

            update_progress(0.95, "💾 Sauvegarde du fichier...")

            tmp = Path(tempfile.gettempdir()) / st.session_state.pdf_name
            tmp.write_bytes(st.session_state.pdf_bytes)
            st.session_state.pdf_tmp_path = tmp

            update_progress(1.0, "✅ PDF généré avec succès !")
            st.success(f"Catalogue généré: {len(filtered_df)} articles")
            log.info(f"PDF généré avec succès: {len(pdf_bytes)} bytes")

        except Exception as e:
            log.error(f"Erreur génération PDF: {e}", exc_info=True)
            st.error(f"Erreur de lecture/génération: {e}")
            st.exception(e)
            status_text.text("❌ Erreur lors de la génération")
    


else:
    # Mode standard
    # Qualité fixée en HD par défaut
    selected_quality = "hd"

    # Option d'aperçu
    preview = st.checkbox("Afficher un aperçu (lent)", value=False, disabled=not HAVE_PDF2IMAGE)
    if not HAVE_PDF2IMAGE and preview:
        st.info("pdf2image non disponible pour l'aperçu.")

    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("Générer le PDF catalogue 🚀"):
            log.info("Début génération PDF mode standard")
            # Barre de progression
            st.session_state.progress_bar = st.progress(0)
            st.session_state.status_text = st.empty()
            progress_bar = st.session_state.progress_bar
            status_text = st.session_state.status_text
            
            try:
                def update_progress(progress, message):
                    progress_bar.progress(progress)
                    status_text.text(message)
                    log.info(f"Progression: {progress:.1%} - {message}")
                
                update_progress(0.05, "🔄 Préparation des données...")
                
                update_progress(0.10, "🔤 Enregistrement des polices...")
                download_and_register_fonts()
                
                update_progress(0.15, "📊 Pré-traitement des données...")
                
                def safe_truncate(text, max_len):
                    s = str(text or "")
                    return s if len(s) <= max_len else s[:max_len-3] + "..."

                df_pdf = filtered_df.copy().fillna("").astype(str)
                max_chars = 800
                df_pdf = df_pdf.applymap(lambda s: safe_truncate(s, max_chars))
                products = df_pdf.to_dict(orient="records")
                
                update_progress(0.20, "📄 Génération de la couverture...")
                
                update_progress(0.25, "📦 Génération des pages produits...")
                
                pdf_bytes = safe_generate_pdf(
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
                
                # Compression du PDF
                update_progress(0.90, "🗜️ Compression du PDF...")
                pdf_bytes = compress_pdf(pdf_bytes)
                st.session_state.pdf_bytes = pdf_bytes
                
                update_progress(0.95, "🔧 Finalisation du PDF...")
                
                update_progress(0.98, "💾 Sauvegarde temporaire...")
                tmp = Path(tempfile.gettempdir()) / st.session_state.pdf_name
                tmp.write_bytes(st.session_state.pdf_bytes)
                st.session_state.pdf_tmp_path = tmp
                
                update_progress(1.0, "✅ PDF généré avec succès !")
                
                st.success("PDF moderne généré avec succès en Haute Définition (HD) !")
                log.info(f"PDF généré avec succès: {len(st.session_state.pdf_bytes)} bytes")
                
            except LayoutError as e:
                log.error(f"Erreur de mise en page: {e}", exc_info=True)
                st.error(f"❌ Erreur de mise en page : {e}")
                st.info("💡 Le contenu est trop large pour la page. Essayez de réduire le nombre de colonnes ou de produits par page.")
                status_text.text("❌ Erreur de mise en page")
            except Exception as e:
                log.error(f"Erreur génération PDF: {e}", exc_info=True)
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

# Section Debug et Téléchargement
if 'pdf_bytes' in st.session_state and st.session_state.pdf_bytes:
    st.markdown("---")
    st.subheader("💾 Télécharger votre catalogue")
    
    # Debug : Affiche taille et preview
    pdf_size_mb = len(st.session_state.pdf_bytes) / 1024 / 1024
    st.write(f"PDF généré avec succès ! Taille : {pdf_size_mb:.2f} MB")
    
    # Afficher le statut de compression si PyPDF2 est disponible
    if HAVE_PYPDF2:
        st.info("✅ PDF compressé automatiquement pour réduire la taille")
    else:
        st.warning("⚠️ PyPDF2 non installé - compression non disponible")
    
    # Option 1 : Download direct (avec try-except)
    try:
        st.download_button(
            label="📥 Télécharger PDF",
            data=st.session_state.pdf_bytes,
            file_name=st.session_state.pdf_name or "catalogue.pdf",
            mime="application/pdf",
            key="download_pdf_button"  # Key unique pour forcer refresh
        )
    except Exception as e:
        st.error(f"Erreur lors du download : {e}. Essayez de rafraîchir la page.")
    
    # Option 2 : Sauvegarde temporaire sur disque (plus robuste pour gros fichiers)
    temp_pdf_path = "temp_catalogue.pdf"
    with open(temp_pdf_path, "wb") as f:
        f.write(st.session_state.pdf_bytes)
    with open(temp_pdf_path, "rb") as f:
        st.download_button(
            label="📥 Télécharger PDF (via fichier temp)",
            data=f,
            file_name="catalogue.pdf",
            mime="application/pdf",
            key="download_temp_button"
        )
    # Nettoyage (optionnel)
    if os.path.exists(temp_pdf_path):
        os.remove(temp_pdf_path)

    # Aperçu (si tu as pdf2image installé)
    if st.checkbox("Afficher aperçu (première page)"):
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(st.session_state.pdf_bytes)
            st.image(images[0], caption="Aperçu PDF", use_column_width=True)
        except Exception as e:
            st.warning(f"Aperçu indisponible: {e}")

    # Section Feedback (optionnelle)
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
    else:
        st.warning("⚠️ Vous devez d'abord soumettre votre avis pour télécharger le PDF.")
        st.info("Veuillez remplir le formulaire de feedback ci-dessus.")

    # Ajout : Bouton pour reset session si bug
    if st.button("🔄 Reset session (si download bloqué)"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.experimental_rerun()

else:
    st.warning("Aucun PDF n'a encore été généré. Cliquez d'abord sur 'Générer le PDF catalogue 🚀'.")
