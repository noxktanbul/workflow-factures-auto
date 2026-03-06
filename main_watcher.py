import os
import sys
import time
import shutil
import re
import json
import queue
import threading
import logging
import datetime
import configparser

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import io
from openpyxl import load_workbook
import validation_ui

# ---------------------------------------------------------------------------
# CONFIG — FIX CONFIG-01 / CONFIG-02
# Charge config.ini depuis le dossier du script ou de l'exe.
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
BASE_DIR    = _base if _base else SCRIPT_DIR
EXCEL_FILE  = _cfg.get('CHEMINS', 'EXCEL_FILE',    fallback=r'Z:\NZBG\échéanciers\Echeancier_cible.xlsx')
TESS_PATH   = _cfg.get('CHEMINS', 'TESSERACT_PATH', fallback=r'C:\Tesseract-OCR\tesseract.exe')
SEUIL       = _cfg.getint('PARAMETRES', 'SEUIL_CONFIANCE',  fallback=7)
MAX_LOG     = _cfg.getint('PARAMETRES', 'MAX_ENTREES_LOG',   fallback=500)

FOLDER_IN   = os.path.join(BASE_DIR, _cfg.get('CHEMINS', 'FOLDER_ENTRANT', fallback='Entrant'))
FOLDER_OUT  = os.path.join(BASE_DIR, _cfg.get('CHEMINS', 'FOLDER_TRAITE',  fallback='Traite'))
FOLDER_ERR  = os.path.join(BASE_DIR, _cfg.get('CHEMINS', 'FOLDER_ERREUR',  fallback='Erreur'))

# FIX LOG-01 : ajout encoding='utf-8'
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "workflow.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

pytesseract.pytesseract.tesseract_cmd = TESS_PATH

# FIX BUG-02 : queue pour passer les tâches UI au thread principal
ui_queue = queue.Queue()

# ---------------------------------------------------------------------------
# NOTIFICATIONS — FIX COMPAT-01 : fallback si win10toast indisponible
# ---------------------------------------------------------------------------
def notify(title, message, duration=5):
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
    # Tier 1 : clients connus (JSON)
    for entry in CLIENTS_CONNUS:
        if re.search(entry["pattern"], text_up, re.IGNORECASE):
            return entry["client"]
    # Tier 2 : mot-clé SOCIETE
    m = re.search(r'(?i)SOCIETE\s+(.*)', text)
    if m:
        return m.group(1).strip()
    # Tier 3 : bloc adresse avec code postal — BUG-D : exclut l'adresse Tauroentum elle-même
    for m_addr in re.finditer(r'(?m)^([A-Z][A-Z0-9\s\-\.]{3,})\r?\n(?:.*\r?\n){0,3}\d{5}', text):
        block = m_addr.group(0)
        name  = m_addr.group(1).strip()
        if _TAUROENTUM_ADDR.search(block):
            continue   # C'est l'adresse de l'émetteur, pas du client
        if re.search(r'(?i)facture|description|formation|stagiaire|tél|siret|^[0-9]', name):
            continue   # Faux positif (ligne de tableau ou données techniques)
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
    return date_str  # fallback : reste en string si format inconnu

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
# EXTRACTION TEXTE — FIX PERF-01 : texte natif d'abord, OCR en fallback
# ---------------------------------------------------------------------------
def extract_text_from_pdf(pdf_path):
    parts = []
    try:
        doc = fitz.open(pdf_path)
        max_pages = min(len(doc), 3)
        for page_num in range(max_pages):
            page = doc.load_page(page_num)
            # Tentative extraction texte natif
            native = page.get_text("text").strip()
            if native and len(native) > 50:
                parts.append(native)
            else:
                # Fallback OCR sur image
                pix = page.get_pixmap(dpi=300)
                page_img = Image.open(io.BytesIO(pix.tobytes()))
                page_img = preprocess_image(page_img)
                ocr_text = pytesseract.image_to_string(page_img, lang='fra', config='--psm 6')
                parts.append(ocr_text)
        doc.close()
    except Exception as e:
        logging.error(f"Erreur extraction texte sur {pdf_path}: {e}")
    return "\n".join(parts)

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
    # Séparateur OCR permissif : tiret, underscore, espace, point, tiret long, pipe...
    _SEP  = r'[^a-zA-Z0-9]{0,4}'

    # 1. Session (extraite EN PREMIER pour pouvoir exclure ses dates ensuite — BUG-B)
    m_sess = re.search(r'(?i)Session(?:\s*du)?\s*(\d{2}[/.\-]\d{2}[/.\-]\d{4}\s*au\s*\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_sess: data["session"] = m_sess.group(1).strip()
    _session_dates = set(re.findall(r'\d{2}[/.\-]\d{2}[/.\-]\d{4}', data["session"])) if data["session"] else set()

    # 2. Numéro de facture — BUG-A : 3 niveaux de fallback
    # Tier 1 : ligne de tableau complète num+date+n°client+echeance
    m_row = re.search(
        r'TAU' + _SEP + r'(\d{4})' + _SEP + r'(\d{3,})\s+' + _DATE + r'(?:\s+\S+)?\s+' + _DATE,
        text, re.IGNORECASE
    )
    if m_row:
        data["num_facture"]   = f"TAU_{m_row.group(1)}-{m_row.group(2)}"
        data["date_facture"]  = m_row.group(3).strip()
        data["date_echeance"] = m_row.group(4).strip()
    else:
        # Tier 2 : num + date (table sans colonne échéance)
        m_row2 = re.search(
            r'TAU' + _SEP + r'(\d{4})' + _SEP + r'(\d{3,})\s+' + _DATE,
            text, re.IGNORECASE
        )
        if m_row2:
            data["num_facture"]  = f"TAU_{m_row2.group(1)}-{m_row2.group(2)}"
            data["date_facture"] = m_row2.group(3).strip()
        else:
            # Tier 3 : num seul avec séparateurs très permissifs
            m_fac = re.search(r'TAU' + _SEP + r'(\d{4})' + _SEP + r'(\d{3,})', text, re.IGNORECASE)
            if m_fac:
                data["num_facture"] = f"TAU_{m_fac.group(1)}-{m_fac.group(2)}"
            else:
                # Tier 4 : cherche YYYY-NNN ou YYYY_NNN près du mot "Numéro"
                m_near = re.search(
                    r'(?i)num[eé]ro.{0,200}?(\d{4})[^a-zA-Z0-9]{1,4}(\d{3,})',
                    text, re.DOTALL
                )
                if m_near:
                    data["num_facture"] = f"TAU_{m_near.group(1)}-{m_near.group(2)}"

        # Fallback date facture — BUG-B : exclut lignes session ET lignes "du ... au"
        if not data["date_facture"]:
            for line in text.splitlines():
                if re.search(r'(?i)session|\bdu\b.+\bau\b', line):
                    continue
                m_d = re.search(_DATE, line)
                if m_d and m_d.group(1) not in _session_dates:
                    data["date_facture"] = m_d.group(1).strip()
                    break

        # Fallback date échéance via mot-clé
        if not data["date_echeance"]:
            m_ech = re.search(r'(?i)(?:[eé]ch[eé]ance|r[eè]glement)\D{0,30}' + _DATE, text)
            if m_ech:
                data["date_echeance"] = re.findall(_DATE, m_ech.group(0))[-1]

    # 3. Client
    data["client"] = detect_client(text)

    # 4. Type CPF/B2B/B2C
    data["type_facture"] = detect_type(text, data["client"])

    # 5. Montant TTC — BUG-C : séparateurs de milliers (5 600,00 / 5.600,00)
    _AMOUNT = r'(\d{1,3}(?:[\s.]\d{3})*[,.]\d{2})'
    m_ttc = re.search(
        r'(?i)(?:Total\s*TTC|Net\s*[àa]\s*payer|Montant\s*(?:TTC)?|Restant\s*d[uûü]|Solde)\D{0,15}' + _AMOUNT,
        text
    )
    if m_ttc:
        amount_raw = m_ttc.group(1).strip()
        data["montant_ttc"] = re.sub(r'[\s.](?=\d{3})', '', amount_raw)  # retire séparateur milliers
    else:
        m_mnt = re.search(_AMOUNT + r'\s*[€eE]', text)
        if m_mnt:
            amount_raw = m_mnt.group(1).strip()
            data["montant_ttc"] = re.sub(r'[\s.](?=\d{3})', '', amount_raw)

    if data["is_avoir"] and data["montant_ttc"] and not str(data["montant_ttc"]).startswith("-"):
        data["montant_ttc"] = "-" + str(data["montant_ttc"])

    # 6. Échéance J+30 par défaut
    data["_echeance_calculee"] = False
    if not data["date_echeance"] and data["date_facture"]:
        d = parse_date(data["date_facture"])
        if isinstance(d, datetime.datetime):
            data["date_echeance"] = (d + datetime.timedelta(days=30)).strftime('%d/%m/%Y')
            data["_echeance_calculee"] = True

    return data

# ---------------------------------------------------------------------------
# SCORE DE CONFIANCE
# ---------------------------------------------------------------------------
def calculate_confidence(data):
    score = 10
    if not data.get("num_facture"):                              score -= 3
    if not data.get("client"):                                   score -= 2
    if not data.get("date_facture"):                             score -= 2
    if not data.get("date_echeance"):                            score -= 2  # pas de pénalité si J+30 calculé
    elif data.get("_echeance_calculee"):                         score -= 1  # pénalité réduite si J+30
    if not data.get("montant_ttc"):                              score -= 3
    return max(0, score)

# ---------------------------------------------------------------------------
# SAUVEGARDE EXCEL — FIX ROBUST-01
# ---------------------------------------------------------------------------
def backup_excel():
    try:
        shutil.copy2(EXCEL_FILE, EXCEL_FILE + ".bak")
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
        backup_excel()  # FIX ROBUST-01
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
        ws[f"C{next_row}"] = data.get("type_facture", "B2B")  # FIX FUNC-01
        ws[f"E{next_row}"] = data.get("session", "")
        ws[f"F{next_row}"] = parse_date(data.get("date_facture", ""))   # FIX FUNC-02
        ws[f"G{next_row}"] = parse_date(data.get("date_echeance", ""))  # FIX FUNC-02

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
# LOG JSON — FIX ROBUST-02 : rotation automatique
# ---------------------------------------------------------------------------
def log_to_json(filepath, data, score, status):
    log_file = os.path.join(BASE_DIR, "workflow.json")
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "file": os.path.basename(filepath),
        "data_extracted": {k: v for k, v in data.items() if k != "is_avoir"},
        "confidence_score": score,
        "status": status,
        "user": os.getlogin()
    }
    try:
        logs = []
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                try:
                    logs = json.load(f)
                except ValueError:
                    logs = []
        logs.append(entry)
        if len(logs) > MAX_LOG:               # FIX ROBUST-02
            logs = logs[-MAX_LOG:]
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Erreur écriture log JSON : {e}")

# ---------------------------------------------------------------------------
# TRAITEMENT D'UNE PAGE PDF
# FIX BUG-02 : les demandes UI sont envoyées dans ui_queue (thread principal)
# ---------------------------------------------------------------------------
def process_pdf(filepath, original_filename=None, page_num=None):
    filename = os.path.basename(filepath)
    display_name = f"Page {page_num} de {original_filename}" if original_filename else filename
    try:
        logging.info(f"Extraction texte pour {display_name}...")
        text = extract_text_from_pdf(filepath)
        data = parse_invoice_text(text)
        score = calculate_confidence(data)
        logging.info(f"Données extraites : {data} (Score: {score}/10)")

        # Vérification doublon préventive
        num = data.get("num_facture")
        if num:
            try:
                wb_r = load_workbook(EXCEL_FILE, data_only=True, read_only=True)
                if "Ventes_Factures" in wb_r.sheetnames:
                    if check_duplicate(wb_r["Ventes_Factures"], num):
                        wb_r.close()
                        logging.warning(f"Doublon ignoré pour {display_name}")
                        try: shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
                        except Exception as mv_err: logging.warning(f"Déplacement échoué (doublon) : {mv_err}")
                        log_to_json(filepath, data, score, "DUPLICATE_SKIPPED")
                        return False
                wb_r.close()
            except Exception as e:
                logging.error(f"Erreur vérif. doublon préventive : {e}")

        if score < SEUIL:
            logging.info(f"Score insuffisant ({score}/{SEUIL}). Envoi vers UI pour {display_name}")
            notify("Validation Requise", f"{display_name} nécessite une validation manuelle.")
            log_to_json(filepath, data, score, "PASSED_TO_UI")

            # FIX BUG-02 : on envoie la tâche UI dans la queue du thread principal
            done_event = threading.Event()
            result_holder = [False]

            def ui_task():
                result_holder[0] = validation_ui.process_with_ui(filepath, pre_data=data, pre_score=score)
                done_event.set()

            ui_queue.put(ui_task)
            done_event.wait()   # Le thread secondaire attend que l'UI se ferme
            return result_holder[0]

        status = inject_to_excel(data)
        if status == "SUCCESS":
            logging.info(f"Injection Excel réussie pour {display_name}")
            os.remove(filepath)
            log_to_json(filepath, data, score, "SUCCESS")
            notify("Succès", f"Facture {data.get('num_facture', filename)} injectée.")
            return True
        elif status == "DUPLICATE":
            logging.warning(f"Doublon détecté pour {display_name}")
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
            log_to_json(filepath, data, score, "DUPLICATE")
            notify("Doublon", f"{display_name} déjà présente dans l'échéancier.")
            return False
        else:
            logging.warning(f"Echec injection pour {display_name}")
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
            log_to_json(filepath, data, score, "ERROR")
            notify("Erreur", f"Erreur d'injection pour {display_name}.")
            return False

    except Exception as e:
        logging.error(f"Erreur processing sur {display_name} : {e}")
        try: shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
        except Exception as mv_err: logging.warning(f"Déplacement vers Erreur échoué : {mv_err}")
        return False

# ---------------------------------------------------------------------------
# DÉCOUPAGE MULTI-PAGES
# ---------------------------------------------------------------------------
def split_and_process_pdf(filepath):
    filename = os.path.basename(filepath)
    try:
        doc = fitz.open(filepath)
        num_pages = len(doc)
        logging.info(f"Fichier {filename} : {num_pages} page(s). Découpage en cours...")
        all_success = True
        for i in range(num_pages):
            temp_name = f"temp_page_{i+1}_of_{filename}"
            temp_path = os.path.join(FOLDER_IN, temp_name)
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=i, to_page=i)
            new_doc.save(temp_path)
            new_doc.close()
            if not process_pdf(temp_path, original_filename=filename, page_num=i + 1):
                all_success = False
        doc.close()
        dest = FOLDER_OUT if all_success else FOLDER_ERR
        shutil.move(filepath, os.path.join(dest, filename))
    except Exception as e:
        logging.error(f"Erreur globale sur {filename} : {e}")
        try: shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
        except Exception as mv_err: logging.warning(f"Déplacement vers Erreur échoué (split) : {mv_err}")

# ---------------------------------------------------------------------------
# WATCHDOG HANDLER — FIX BUG-02 : traitement dans un thread secondaire
# ---------------------------------------------------------------------------
class InvoiceHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        filepath = event.src_path
        if filepath.lower().endswith(".pdf") and not os.path.basename(filepath).startswith("temp_page_"):
            logging.info(f"Nouveau fichier détecté : {filepath}")
            time.sleep(2)
            threading.Thread(
                target=split_and_process_pdf,
                args=(filepath,),
                daemon=True
            ).start()

# ---------------------------------------------------------------------------
# DÉMARRAGE PRINCIPAL
# FIX BUG-02 : la boucle principale traite les UI requests dans le thread main
# ---------------------------------------------------------------------------
def start_watcher():
    for d in (FOLDER_IN, FOLDER_OUT, FOLDER_ERR):
        os.makedirs(d, exist_ok=True)

    logging.info(f"Démarrage surveillance sur {FOLDER_IN}")
    print(f"Robot Factures démarré. Dossier surveillé : {FOLDER_IN}")

    # Traitement des fichiers déjà présents au démarrage
    for fname in os.listdir(FOLDER_IN):
        if fname.lower().endswith(".pdf") and not fname.startswith("temp_page_"):
            threading.Thread(
                target=split_and_process_pdf,
                args=(os.path.join(FOLDER_IN, fname),),
                daemon=True
            ).start()

    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, FOLDER_IN, recursive=False)
    observer.start()

    try:
        while True:
            try:
                # FIX BUG-02 : exécute les tâches Tkinter dans le thread principal
                task = ui_queue.get(timeout=0.2)
                task()
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_watcher()
