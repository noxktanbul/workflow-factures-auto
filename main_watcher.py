import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import re
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import io
from openpyxl import load_workbook
import shutil
import logging
import json
import datetime
import subprocess
from validation_ui import process_with_ui
try:
    from win10toast import ToastNotifier
    toaster = ToastNotifier()
except ImportError:
    toaster = None

import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FOLDER_IN = os.path.join(BASE_DIR, "Entrant")
FOLDER_OUT = os.path.join(BASE_DIR, "Traite")
FOLDER_ERR = os.path.join(BASE_DIR, "Erreur")
EXCEL_FILE = os.path.join(BASE_DIR, "References", "Echeancier_cible.xlsx")

# Log config
logging.basicConfig(filename=os.path.join(BASE_DIR, "workflow.log"), level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Tesseract 
pytesseract.pytesseract.tesseract_cmd = r'C:\Tesseract-OCR\tesseract.exe'

def preprocess_image(img):
    img = img.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    return img

def extract_text_from_scanned_pdf(pdf_path):
    texts = []
    try:
        doc = fitz.open(pdf_path)
        # Check maximum 3 pages to find data, avoiding 35-page OCRs for nothing
        max_pages = min(len(doc), 3)
        for page_num in range(max_pages):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=300)
            pil_img = Image.open(io.BytesIO(pix.tobytes()))
            img_processed = preprocess_image(pil_img)
            text = pytesseract.image_to_string(img_processed, lang='fra')
            texts.append(text)
        doc.close()
        full_text = "\n".join(texts) + "\n" if texts else ""
    except Exception as e:
        logging.error(f"Erreur OCR sur {pdf_path}: {e}")
    return full_text

def parse_invoice_text(text):
    data = {"num_facture": "", "client": "", "date_facture": "", "date_echeance": "", "montant_ttc": "", "session": ""}
    
    # TAU_2026-413
    m_facture = re.search(r'(?i)(TAU_\d{4}[\-\_]\d+)', text)
    if m_facture: data["num_facture"] = m_facture.group(1).strip()
        
    all_dates = re.findall(r'(\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if all_dates:
        data["date_facture"] = all_dates[0]
        
    m_echeance = re.search(r'(?i)(?:échéance|echeance|règlement|limite)\s*.*?(?:\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_echeance:
         dates = re.findall(r'(\d{2}[/.\-]\d{2}[/.\-]\d{4})', m_echeance.group(0))
         if dates: data["date_echeance"] = dates[-1]
    elif len(all_dates) > 1:
         data["date_echeance"] = all_dates[-1]
             
    m_session = re.search(r'(?i)Session(?:\s*du)?\s*(\d{2}[/.\-]\d{2}[/.\-]\d{4}\s*au\s*\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_session: data["session"] = m_session.group(1).strip()
    
    m_client = re.search(r'(?i)SOCIETE\s*([^\n\r]+)', text)
    if m_client: data["client"] = m_client.group(1).strip()
             
    m_ttc_explicit = re.search(r'(?i)(?:Total\s*TTC|TTC|Net\s*à\s*payer).*?([\d\s]+[,.]\d{2})(?:\s*€|\s*EUR)?', text)
    if m_ttc_explicit:
        data["montant_ttc"] = m_ttc_explicit.group(1).replace(' ', '').strip()
    else:
        amounts = re.findall(r'([\d\s]+[,.]\d{2})\s*(?:€|EUR)', text)
        if amounts:
            try:
                clean_amounts = [float(a.replace(' ', '').replace(',', '.')) for a in amounts]
                data["montant_ttc"] = f"{max(clean_amounts):.2f}".replace('.', ',')
            except ValueError:
                data["montant_ttc"] = amounts[-1].replace(' ', '').strip()
        
    return data

def check_duplicate(ws, num_facture):
    if not num_facture:
        return False
    for row in range(2, ws.max_row + 2):
        cell_val = ws[f"A{row}"].value
        if cell_val and str(cell_val).strip() == str(num_facture).strip():
            return True
    return False

def inject_to_excel(data):
    try:
        wb = load_workbook(EXCEL_FILE)
        ws = wb["Ventes_Factures"]
        
        if check_duplicate(ws, data.get("num_facture")):
            wb.close()
            return "DUPLICATE"
        
        # Trouver la première ligne vide
        target_row = ws.max_row + 1
        for r in range(2, ws.max_row + 2):
            if not ws[f"A{r}"].value:
                target_row = r
                break
                
        # N° Facture (col A), Client (B), Type (C=defaut B2B), Référence (D), Session (E)
        # Date Facture (F), Date Échéance (G), Montant TTC (H)
        ws[f"A{target_row}"] = data["num_facture"]
        ws[f"B{target_row}"] = data["client"]
        ws[f"C{target_row}"] = "B2B"  # Défaut
        ws[f"E{target_row}"] = data["session"]
        ws[f"F{target_row}"] = data["date_facture"]
        ws[f"G{target_row}"] = data["date_echeance"]
        
        # Casting montant to float
        if data["montant_ttc"]:
            try:
                mnt = float(data["montant_ttc"].replace(',', '.'))
                ws[f"H{target_row}"] = mnt
            except ValueError:
                ws[f"H{target_row}"] = data["montant_ttc"]
        
        wb.save(EXCEL_FILE)
        wb.close()
        return "SUCCESS"
    except Exception as e:
        logging.error(f"Erreur d'injection Excel : {e}")
        return "ERROR"

class InvoiceHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
             return
             
        filepath = event.src_path
        if filepath.lower().endswith(".pdf"):
            logging.info(f"Nouveau fichier détecté : {filepath}")
            time.sleep(2) # Attendre que la copie soit finie
            process_pdf(filepath)

def log_to_json(filepath, data, score, status):
    log_file = os.path.join(BASE_DIR, "workflow.json")
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "file": os.path.basename(filepath),
        "data_extracted": data,
        "confidence_score": score,
        "status": status,
        "user": os.getlogin()
    }
    try:
        logs = []
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                try: logs = json.load(f)
                except ValueError: logs = []
        logs.append(entry)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Erreur ecriture log JSON : {e}")

def calculate_confidence(data):
    score = 10
    if not data.get("num_facture"): score -= 3
    if not data.get("client"): score -= 2
    if not data.get("date_facture"): score -= 2
    if not data.get("date_echeance"): score -= 2
    if not data.get("montant_ttc"): score -= 3
    return max(0, score)

def process_pdf(filepath):
    filename = os.path.basename(filepath)
    try:
        logging.info(f"Extraction du texte pour {filename}...")
        text = extract_text_from_scanned_pdf(filepath)
        data = parse_invoice_text(text)
        
        score = calculate_confidence(data)
        logging.info(f"Données extraites : {data} (Score: {score}/10)")
        
        if score < 7:
            logging.info(f"Score insuffisant. Lancement UI pour {filename}")
            if toaster: toaster.show_toast("Validation Requise", f"La facture {filename} nécessite une validation manuelle.", duration=5, threaded=True)
            
            log_to_json(filepath, data, score, "PASSED_TO_UI")
            try:
                process_with_ui(filepath)
            except Exception as e:
                logging.error(f"Erreur UI dynamique : {e}")
            return
        
        status = inject_to_excel(data)
        if status == "SUCCESS":
            logging.info(f"Injection Excel réussie pour {filename}")
            shutil.move(filepath, os.path.join(FOLDER_OUT, filename))
            log_to_json(filepath, data, score, "SUCCESS")
            if toaster: toaster.show_toast("Facture Traitée", f"{filename} a été injectée avec succès.", duration=5, threaded=True)
        elif status == "DUPLICATE":
            logging.warning(f"Doublon détecté pour {filename}")
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
            log_to_json(filepath, data, score, "DUPLICATE")
            if toaster: toaster.show_toast("Doublon Facture", f"{filename} est un doublon et n'a pas été injectée.", duration=5, threaded=True)
        else:
            logging.warning(f"Echec injection pour {filename}")
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
            log_to_json(filepath, data, score, "ERROR")
            if toaster: toaster.show_toast("Erreur Facture", f"Erreur d'injection pour {filename}.", duration=5, threaded=True)
            
    except Exception as e:
        logging.error(f"Erreur globale sur {filename} : {e}")
        try:
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
        except Exception:
             pass

def start_watcher():
    logging.info(f"Démarrage surveillance sur {FOLDER_IN}")
    print(f"Watchdog actif. Déposez un PDF dans {FOLDER_IN}")
    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, FOLDER_IN, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_watcher()
