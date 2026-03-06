import os
import sys
import time
import shutil
import re
import json
import logging
import datetime
import configparser

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageTk
import io
import tkinter as tk
from tkinter import messagebox
from openpyxl import load_workbook

# ---------------------------------------------------------------------------
# CONFIG — chargé depuis config.ini dans le dossier du script ou de l'exe
# ---------------------------------------------------------------------------
def _get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = _get_script_dir()
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.ini")

_cfg = configparser.ConfigParser()
_cfg.read(CONFIG_FILE, encoding='utf-8')

_base = _cfg.get('CHEMINS', 'BASE_DIR', fallback='').strip()
BASE_DIR   = _base if _base else SCRIPT_DIR
EXCEL_FILE = _cfg.get('CHEMINS', 'EXCEL_FILE',    fallback=r'Z:\NZBG\échéanciers\Echeancier_cible.xlsx')
TESS_PATH  = _cfg.get('CHEMINS', 'TESSERACT_PATH', fallback=r'C:\Tesseract-OCR\tesseract.exe')
SEUIL      = _cfg.getint('PARAMETRES', 'SEUIL_CONFIANCE', fallback=7)
MAX_LOG    = _cfg.getint('PARAMETRES', 'MAX_ENTREES_LOG',  fallback=500)

FOLDER_IN  = os.path.join(BASE_DIR, _cfg.get('CHEMINS', 'FOLDER_ENTRANT', fallback='Entrant'))
FOLDER_OUT = os.path.join(BASE_DIR, _cfg.get('CHEMINS', 'FOLDER_TRAITE',  fallback='Traite'))
FOLDER_ERR = os.path.join(BASE_DIR, _cfg.get('CHEMINS', 'FOLDER_ERREUR',  fallback='Erreur'))

# Constantes d'extraction
OCR_DPI          = 300   # résolution d'image pour Tesseract
PREVIEW_DPI      = 150   # résolution de l'aperçu affiché dans l'UI
MAX_PDF_PAGES    = 3     # nombre max de pages analysées par facture
MIN_NATIVE_CHARS = 50    # seuil en dessous duquel on bascule en OCR
ECHEANCE_JOURS   = 30    # délai de paiement par défaut (J+30)

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "workflow.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

pytesseract.pytesseract.tesseract_cmd = TESS_PATH

NOTIF_DURATION_SEC = 5  # durée d'affichage des notifications Windows

# ---------------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------------
def notify(title, message, duration=NOTIF_DURATION_SEC):
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=duration, threaded=True)
    except Exception:
        logging.info(f"[NOTIF] {title} : {message}")

# ---------------------------------------------------------------------------
# CLIENTS CONNUS — FIX FUNC-03
# ---------------------------------------------------------------------------
def _load_clients():
    path = os.path.join(SCRIPT_DIR, "clients_connus.json")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

CLIENTS_CONNUS = _load_clients()

_TAUROENTUM_ADDR = re.compile(
    r'TAUROENTUM|CIOTAT|Centre Louis|Victor de Delacour|PÔLE|Pôle Tauro',
    re.IGNORECASE
)

def detect_client(text):
    text_up = text.upper()
    for entry in CLIENTS_CONNUS:
        if re.search(entry["pattern"], text_up, re.IGNORECASE):
            return entry["client"]
    m = re.search(r'(?i)SOCIETE\s+(.*)', text)
    if m:
        return m.group(1).strip()
    # Détection par bloc adresse : exclut les blocs contenant l'adresse de l'émetteur
    for m_addr in re.finditer(r'(?m)^([A-Z][A-Z0-9\s\-\.]{3,})\r?\n(?:.*\r?\n){0,3}\d{5}', text):
        block = m_addr.group(0)
        name  = m_addr.group(1).strip()
        if _TAUROENTUM_ADDR.search(block):
            continue
        if re.search(r'(?i)facture|description|formation|stagiaire|tél|siret|^[0-9]', name):
            continue
        if len(name) >= 4:
            return name
    return ""

# ---------------------------------------------------------------------------
# DÉTECTION TYPE — FIX FUNC-01
# ---------------------------------------------------------------------------
def detect_type(text, client):
    text_up = text.upper()
    if client == "CPF" or "CAISSE DES DEPOTS" in text_up or "COMPTE PERSONNEL DE FORMATION" in text_up or re.search(r'\b\d{11}\b', text):
        return "CPF"
    if re.search(r'(?i)(particulier|personne physique)', text) and "SIREN" not in text_up:
        return "B2C"
    return "B2B"

# ---------------------------------------------------------------------------
# CONVERSION DATE — FIX FUNC-02
# ---------------------------------------------------------------------------
def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return date_str

# ---------------------------------------------------------------------------
# PRE-TRAITEMENT IMAGE
# ---------------------------------------------------------------------------
def preprocess_image(img):
    img = img.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    return img

# ---------------------------------------------------------------------------
# EXTRACTION TEXTE + IMAGE PREVIEW — FIX PERF-01
# ---------------------------------------------------------------------------
def extract_text_and_first_page_image(pdf_path):
    parts = []
    preview_img = None
    try:
        doc = fitz.open(pdf_path)
        max_pages = min(len(doc), MAX_PDF_PAGES)
        for page_num in range(max_pages):
            page = doc.load_page(page_num)
            pix_preview = page.get_pixmap(dpi=PREVIEW_DPI)
            img_preview = Image.open(io.BytesIO(pix_preview.tobytes()))
            if page_num == 0:
                preview_img = img_preview.copy()
            # Texte natif en priorité, OCR en fallback si le texte est insuffisant
            native = page.get_text("text").strip()
            if native and len(native) > MIN_NATIVE_CHARS:
                parts.append(native)
            else:
                img_ocr = preprocess_image(img_preview)
                ocr_text = pytesseract.image_to_string(img_ocr, lang='fra', config='--psm 6')
                parts.append(ocr_text)
        doc.close()
    except Exception as e:
        logging.error(f"Erreur OCR/aperçu sur {pdf_path}: {e}")
    return "\n".join(parts), preview_img

# ---------------------------------------------------------------------------
# PARSING — FIX FUNC-01, FUNC-03, REGEX-01
# ---------------------------------------------------------------------------
def parse_invoice_text(text):
    data = {
        "num_facture": "", "client": "", "type_facture": "",
        "date_facture": "", "date_echeance": "", "montant_ttc": "",
        "session": "", "is_avoir": False
    }
    if re.search(r'(?i)\bavoir\b', text):
        data["is_avoir"] = True

    _DATE = r'(\d{2}[/.\-]\d{2}[/.\-]\d{4})'
    _SEP  = r'[^a-zA-Z0-9]{0,4}'

    # Session extraite en premier pour exclure ses dates du fallback date_facture
    # Les deux dates doivent être différentes pour éviter de confondre avec une ligne de tableau
    m_sess = re.search(r'(?i)Session(?:\s*du)?\s*(\d{2}[/.\-]\d{2}[/.\-]\d{4})\s*au\s*(\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_sess and m_sess.group(1) != m_sess.group(2):
        data["session"] = f"{m_sess.group(1)} au {m_sess.group(2)}"
    _session_dates = set(re.findall(r'\d{2}[/.\-]\d{2}[/.\-]\d{4}', data["session"])) if data["session"] else set()

    # Numéro — 5 niveaux de fallback (tolérance aux artefacts OCR)
    # Tier 0 : format littéral exact TAU_YYYY-NNN — dates cherchées dans la fenêtre de contexte
    m_tier0_num = re.search(r'TAU_(\d{4})-(\d{3,})', text, re.IGNORECASE)
    if m_tier0_num:
        data["num_facture"] = f"TAU_{m_tier0_num.group(1)}-{m_tier0_num.group(2)}"
        ctx_start = max(0, m_tier0_num.start() - 50)
        ctx_end   = min(len(text), m_tier0_num.end() + 200)
        ctx = text[ctx_start:ctx_end]
        dates_in_ctx = re.findall(r'\d{2}[/.\-]\d{2}[/.\-]\d{4}', ctx)
        dates_in_ctx = [d for d in dates_in_ctx if d not in _session_dates]
        if len(dates_in_ctx) >= 2:
            data["date_facture"]  = dates_in_ctx[0]
            data["date_echeance"] = dates_in_ctx[-1]
        elif len(dates_in_ctx) == 1:
            data["date_facture"] = dates_in_ctx[0]

    # Tiers 1-4 : fallback OCR-permissif si Tier 0 n'a pas tout trouvé
    if not data["num_facture"]:
        m_row = re.search(r'TAU' + _SEP + r'(\d{4})' + _SEP + r'(\d{3,})\s+' + _DATE + r'(?:\s+\S+)?\s+' + _DATE, text, re.IGNORECASE)
        if m_row:
            data["num_facture"]   = f"TAU_{m_row.group(1)}-{m_row.group(2)}"
            data["date_facture"]  = m_row.group(3).strip()
            data["date_echeance"] = m_row.group(4).strip()
        else:
            m_row2 = re.search(r'TAU' + _SEP + r'(\d{4})' + _SEP + r'(\d{3,})\s+' + _DATE, text, re.IGNORECASE)
            if m_row2:
                data["num_facture"]  = f"TAU_{m_row2.group(1)}-{m_row2.group(2)}"
                data["date_facture"] = m_row2.group(3).strip()
            else:
                m_fac = re.search(r'TAU' + _SEP + r'(\d{4})' + _SEP + r'(\d{3,})', text, re.IGNORECASE)
                if m_fac:
                    data["num_facture"] = f"TAU_{m_fac.group(1)}-{m_fac.group(2)}"
                else:
                    m_near = re.search(r'(?i)num[eé]ro.{0,200}?(\d{4})[^a-zA-Z0-9]{1,4}(\d{3,})', text, re.DOTALL)
                    if m_near and 2020 <= int(m_near.group(1)) <= 2040:
                        data["num_facture"] = f"TAU_{m_near.group(1)}-{m_near.group(2)}"

    # Fallback date facture : exclut les lignes de session
    if not data["date_facture"]:
        for line in text.splitlines():
            if re.search(r'(?i)session|\bdu\b.+\bau\b', line):
                continue
            m_d = re.search(_DATE, line)
            if m_d and m_d.group(1) not in _session_dates:
                data["date_facture"] = m_d.group(1).strip()
                break

    if not data["date_echeance"]:
        m_ech = re.search(r'(?i)(?:[eé]ch[eé]ance|r[eè]glement)\D{0,30}' + _DATE, text)
        if m_ech:
            data["date_echeance"] = re.findall(_DATE, m_ech.group(0))[-1]

    data["client"] = detect_client(text)
    data["type_facture"] = detect_type(text, data["client"])

    # Montant — priorité : Total TTC / Net à payer → Restant dû → Montant → fallback €
    # Pattern unifié : supporte 1.234,56 / 1 234,56 / 1234,56 / 260.00 / 260,00
    _AMOUNT = r'(\d{1,3}(?:[\s]\d{3})*(?:[,.]\d{2})|(?:\d{1,3}(?:[.]\d{3})+(?:[,]\d{2})?)|\d+[,.]\d{2})'

    def _clean_amount(raw):
        raw = raw.strip()
        raw = re.sub(r'[\s](?=\d{3}(?:[,.]|$))', '', raw)
        raw = re.sub(r'[.](?=\d{3}[,])', '', raw)
        return raw

    m_ttc = re.search(r'(?i)(?:Total\s*TTC|Net\s*[àa]\s*payer|Solde\s*[àa]\s*payer)\D{0,15}' + _AMOUNT, text)
    if m_ttc:
        data["montant_ttc"] = _clean_amount(m_ttc.group(1))
    else:
        m_restant = re.search(r'(?i)Restant\s*d[uûü]\D{0,15}' + _AMOUNT, text)
        if m_restant:
            val = _clean_amount(m_restant.group(1))
            cleaned = val.replace(',', '.').replace(' ', '')
            if float(cleaned) > 0:
                data["montant_ttc"] = val
        if not data["montant_ttc"]:
            m_mnt_kw = re.search(r'(?i)Montant\s*(?:TTC)?\D{0,15}' + _AMOUNT, text)
            if m_mnt_kw:
                data["montant_ttc"] = _clean_amount(m_mnt_kw.group(1))
        if not data["montant_ttc"]:
            m_eur = re.search(_AMOUNT + r'\s*[€eE]', text)
            if m_eur:
                data["montant_ttc"] = _clean_amount(m_eur.group(1))

    if data["is_avoir"] and data["montant_ttc"] and not str(data["montant_ttc"]).startswith("-"):
        data["montant_ttc"] = "-" + str(data["montant_ttc"])

    # Échéance par défaut si absente : date facture + ECHEANCE_JOURS
    data["_echeance_calculee"] = False
    if not data["date_echeance"] and data["date_facture"]:
        d = parse_date(data["date_facture"])
        if isinstance(d, datetime.datetime):
            data["date_echeance"] = (d + datetime.timedelta(days=ECHEANCE_JOURS)).strftime('%d/%m/%Y')
            data["_echeance_calculee"] = True

    return data

def calculate_confidence(data):
    score = 10
    if not data.get("num_facture"):    score -= 3
    if not data.get("client"):         score -= 2
    if not data.get("date_facture"):   score -= 2
    if not data.get("date_echeance"):  score -= 2
    if not data.get("montant_ttc"):    score -= 3
    return max(0, score)

# ---------------------------------------------------------------------------
# SAUVEGARDE EXCEL — FIX ROBUST-01
# ---------------------------------------------------------------------------
def backup_excel():
    try:
        import shutil as _sh
        _sh.copy2(EXCEL_FILE, EXCEL_FILE + ".bak")
    except Exception as e:
        logging.warning(f"Sauvegarde Excel impossible : {e}")

# ---------------------------------------------------------------------------
# VÉRIFICATION DOUBLON
# ---------------------------------------------------------------------------
def check_duplicate(ws, num_facture):
    if not num_facture:
        return False
    for row in range(2, ws.max_row + 2):
        val = ws[f"A{row}"].value
        if val and str(val).strip() == str(num_facture).strip():
            return True
    return False

# ---------------------------------------------------------------------------
# INJECTION EXCEL — FIX FUNC-01, FUNC-02, ROBUST-01
# ---------------------------------------------------------------------------
def inject_to_excel(data):
    try:
        backup_excel()
        wb = load_workbook(EXCEL_FILE)
        ws = wb["Ventes_Factures"]

        if check_duplicate(ws, data.get("num_facture")):
            wb.close()
            return "DUPLICATE"

        next_row = ws.max_row + 1
        for row in range(2, ws.max_row + 2):
            if not ws[f"A{row}"].value:
                next_row = row
                break

        ws[f"A{next_row}"] = data.get("num_facture", "")
        ws[f"B{next_row}"] = data.get("client", "")
        ws[f"C{next_row}"] = data.get("type_facture", "B2B")
        ws[f"E{next_row}"] = data.get("session", "")
        ws[f"F{next_row}"] = parse_date(data.get("date_facture", ""))
        ws[f"G{next_row}"] = parse_date(data.get("date_echeance", ""))

        mnt_raw = data.get("montant_ttc", "")
        if mnt_raw:
            try:
                ws[f"H{next_row}"] = float(str(mnt_raw).replace(',', '.').replace(' ', ''))
            except ValueError:
                ws[f"H{next_row}"] = mnt_raw

        wb.save(EXCEL_FILE)
        wb.close()
        return "SUCCESS"
    except Exception as e:
        logging.error(f"Erreur injection Excel : {e}")
        return "ERROR"

# ---------------------------------------------------------------------------
# INTERFACE DE VALIDATION — FIX UX-02 : score affiché + champs colorés
# ---------------------------------------------------------------------------
class ValidationUI:
    def __init__(self, root, pdf_path, extracted_data, score, img_preview):
        self.root = root
        self.root.title("Validation Facture - WorkflowFactures")
        self.root.geometry("1050x720")
        self.root.resizable(True, True)

        self.pdf_path = pdf_path
        self.data = extracted_data
        self.score = score
        self.img_preview = img_preview
        self.result = False
        self.final_data = {}

        self._setup_ui()

    def _score_color(self):
        if self.score >= 7:   return "green"
        if self.score >= 4:   return "orange"
        return "red"

    def _setup_ui(self):
        # Cadre gauche : aperçu PDF
        left = tk.Frame(self.root, bg="#2b2b2b")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        if self.img_preview:
            img_w, img_h = self.img_preview.size
            ratio = 660 / img_h
            img_resized = self.img_preview.resize((int(img_w * ratio), 660), Image.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(img_resized)
            tk.Label(left, image=self.tk_img, bg="#2b2b2b").pack(padx=8, pady=8)
        else:
            tk.Label(left, text="Aperçu indisponible", bg="#2b2b2b", fg="white").pack(expand=True)

        # Cadre droit : formulaire
        right = tk.Frame(self.root, width=420, padx=20, pady=15)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(right, text="Vérification des Données", font=("Arial", 15, "bold")).pack(pady=10)

        score_txt = f"Score de confiance : {self.score}/10"
        tk.Label(
            right, text=score_txt,
            font=("Arial", 11, "bold"),
            fg=self._score_color()
        ).pack(pady=(0, 4))

        # Légende des champs manquants
        tk.Label(
            right,
            text="Les cases en rouge indiquent les champs manquants.",
            font=("Arial", 9), fg="gray"
        ).pack(pady=(0, 10))

        self.entries = {}
        fields = [
            ("Numéro Facture *",   "num_facture"),
            ("Client *",           "client"),
            ("Type (CPF/B2B/B2C)*","type_facture"),
            ("Date Facture *",     "date_facture"),
            ("Date Échéance *",    "date_echeance"),
            ("Session",            "session"),
            ("Montant TTC *",      "montant_ttc"),
        ]
        for label_text, key in fields:
            row_f = tk.Frame(right)
            row_f.pack(fill=tk.X, pady=4)
            tk.Label(row_f, text=label_text, width=20, anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
            var = tk.StringVar(value=self.data.get(key, ""))
            ent = tk.Entry(row_f, textvariable=var, width=26, font=("Arial", 9))
            ent.pack(side=tk.LEFT, padx=6)
            if not var.get():
                ent.config(bg="#ffcccc")   # rouge = vide / non extrait
            elif key == "date_echeance" and self.data.get("_echeance_calculee"):
                ent.config(bg="#ffe0a0")   # orange = J+30 calculé automatiquement
            self.entries[key] = var

        btn_frame = tk.Frame(right)
        btn_frame.pack(fill=tk.X, pady=30)
        tk.Button(
            btn_frame, text="Valider & Injecter",
            command=self._on_validate,
            bg="#90EE90", font=("Arial", 10, "bold"), height=2
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        tk.Button(
            btn_frame, text="Rejeter",
            command=self._on_reject,
            bg="#FA8072", font=("Arial", 10, "bold"), height=2
        ).pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)

    def _on_validate(self):
        self.final_data = {key: var.get() for key, var in self.entries.items()}
        self.result = True
        self.root.destroy()

    def _on_reject(self):
        self.result = False
        self.root.destroy()

# ---------------------------------------------------------------------------
# ENTRY POINT UI — FIX BUG-01 : injection faite ici (une seule fois)
# ---------------------------------------------------------------------------
def process_with_ui(pdf_path, pre_data=None, pre_score=None):
    """
    Lance l'UI de validation pour pdf_path.
    Si pre_data / pre_score sont fournis (depuis main_watcher), on évite un double OCR.
    Retourne True si injection réussie, False sinon.
    """
    if pre_data is not None:
        data = pre_data
        score = pre_score if pre_score is not None else calculate_confidence(data)
        # Image preview uniquement (150 dpi, pas d'OCR) — BUG-E : log si échec
        first_page_img = None
        try:
            doc = fitz.open(pdf_path)
            pix = doc.load_page(0).get_pixmap(dpi=PREVIEW_DPI)
            img = Image.open(io.BytesIO(pix.tobytes()))
            # Vérifie que la page n'est pas vide (page blanche ou sans contenu)
            min_page_px = 10
            if pix.width > min_page_px and pix.height > min_page_px:
                first_page_img = img.copy()
            else:
                logging.warning(f"[UI] Page vide ou trop petite pour {os.path.basename(pdf_path)}")
            doc.close()
        except Exception as e:
            logging.warning(f"[UI] Aperçu indisponible pour {os.path.basename(pdf_path)} : {e}")
    else:
        text, first_page_img = extract_text_and_first_page_image(pdf_path)
        data = parse_invoice_text(text)
        score = calculate_confidence(data)

    root = tk.Tk()
    app = ValidationUI(root, pdf_path, data, score, first_page_img)
    root.mainloop()
    time.sleep(0.3)

    err_path = os.path.join(FOLDER_ERR, os.path.basename(pdf_path))

    if app.result:
        status = inject_to_excel(app.final_data)
        if status == "SUCCESS":
            logging.info("[UI] Injection Excel réussie.")
            notify("Succès", f"Facture {app.final_data.get('num_facture', '')} injectée.")
            try:
                os.remove(os.path.abspath(pdf_path))
            except Exception as e:
                logging.warning(f"Fichier temp non supprimé : {e}")
            return True
        elif status == "DUPLICATE":
            logging.info("[UI] Doublon détecté, injection annulée.")
            # Nouvelle fenêtre temporaire pour le messagebox (root est détruit)
            _tmp = tk.Tk(); _tmp.withdraw()
            messagebox.showwarning("Doublon", "Cette facture existe déjà dans l'échéancier.", parent=_tmp)
            _tmp.destroy()
            try: shutil.move(os.path.abspath(pdf_path), os.path.abspath(err_path))
            except Exception as mv_err: logging.warning(f"[UI] Déplacement échoué (doublon) : {mv_err}")
            return False
        else:
            logging.warning("[UI] Echec injection.")
            _tmp = tk.Tk(); _tmp.withdraw()
            messagebox.showerror("Erreur", "Une erreur est survenue lors de l'injection.", parent=_tmp)
            _tmp.destroy()
            try: shutil.move(os.path.abspath(pdf_path), os.path.abspath(err_path))
            except Exception as mv_err: logging.warning(f"[UI] Déplacement échoué (erreur) : {mv_err}")
            return False
    else:
        logging.info("[UI] Rejet par l'utilisateur.")
        try: shutil.move(os.path.abspath(pdf_path), os.path.abspath(err_path))
        except Exception as mv_err: logging.warning(f"[UI] Déplacement échoué (rejet) : {mv_err}")
        return False

# ---------------------------------------------------------------------------
# LANCEMENT AUTONOME (tests / standalone)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if os.path.exists(pdf_path):
            process_with_ui(pdf_path)
        else:
            print(f"Fichier introuvable : {pdf_path}")
    else:
        test_file = os.path.join(BASE_DIR, "References", "Factures ventes non réglées part.3.pdf")
        if os.path.exists(test_file):
            import shutil as _sh
            test_copy = os.path.join(FOLDER_IN, "Test_UI_standalone.pdf")
            _sh.copy(test_file, test_copy)
            process_with_ui(test_copy)
        else:
            print("Aucun fichier de test trouvé. Passez un chemin PDF en argument.")
