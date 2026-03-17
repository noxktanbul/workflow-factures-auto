import os
import time
import queue
import traceback
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import re
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter
import io
from openpyxl import load_workbook
import shutil
import logging
import json
import datetime
from validation_ui import process_with_ui
from ocr_engine import extract_text
from client_dictionary import match_client

# File d'attente thread-safe : watchdog → thread principal
# Tkinter DOIT s'exécuter depuis le thread principal (contrainte Windows).
# Le thread watchdog enfile les chemins PDF ; le thread principal les traite.
_pdf_queue = queue.Queue()
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

DPI_HIGH = 150

# Détection automatique du nommage des dossiers (deux conventions possibles)
def _find_folder(base, *candidates):
    for name in candidates:
        p = os.path.join(base, name)
        if os.path.isdir(p):
            return p
    # Aucun existant : créer le premier candidat
    p = os.path.join(base, candidates[0])
    os.makedirs(p, exist_ok=True)
    return p

FOLDER_IN  = _find_folder(BASE_DIR, "1_Entrant_Deposer_PDF", "Entrant")
FOLDER_OUT = _find_folder(BASE_DIR, "2_Traite_Succes", "Traite")
FOLDER_ERR = _find_folder(BASE_DIR, "3_Erreur_A_Verifier", "Erreur")

# Recherche du fichier Excel dans plusieurs emplacements candidats
_excel_candidates = [
    os.path.join(os.path.dirname(BASE_DIR), "\u00e9ch\u00e9ancier factures ventes", "Echeancier_cible.xlsx"),  # z:\NZBG\échéanciers\échéancier factures ventes\ (PROD)
    os.path.join(BASE_DIR, "Echeancier_cible.xlsx"),                          # à côté de l'EXE
    os.path.join(os.path.dirname(BASE_DIR), "Echeancier_cible.xlsx"),          # dossier parent
    os.path.join(BASE_DIR, "References", "Echeancier_cible.xlsx"),             # sous-dossier References/
]
EXCEL_FILE = next((p for p in _excel_candidates if os.path.exists(p)), _excel_candidates[0])

# Log config
logging.basicConfig(filename=os.path.join(BASE_DIR, "workflow.log"), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# OCR Engine (EasyOCR via ocr_engine.py)

# ─────────────────────────────────────────────────────────────
# MOTS-CLES POUBELLE pour filtrer l'entête Pôle Tauroentum
# ─────────────────────────────────────────────────────────────
JUNK_WORDS = [
    "tauroentum", "centre louis", "delacour", "la ciotat",
    "siret", "tél", "tel :", "tel.", "facture", "numéro",
    "description", "date", "n° client", "échéance", "echeance",
    "éditeur", "editeur", "enrichi", "courrier", "http",
    "rcs", "marseille", "paca", "cgr", "cgi", "tvA",
    "déclaration", "declaration", "agrément", "agrement",
    "exonéra", "exonera", "capital", "sarl au",
    "1 sur 1", "l sur 1", "sur 1",
    "generateur", "gst2015",
]

# ─────────────────────────────────────────────────────────────
# LIGNES PARASITES à supprimer du texte avant extraction montant
# (ex: "SARL au capital de 7500€" apparaît sur chaque page)
# ─────────────────────────────────────────────────────────────
FOOTER_PATTERNS = [
    r'(?i)capital\s+de\s+[\d\s.,]+[€ëé]',
    r'(?i)siret\s+n.*\d{5}',
    r'(?i)d[ée]claration\s+d.*activit',
    r'(?i)ne\s+vaut\s+pas\s+agr[ée]ment',
    r'(?i)exon[ée]ra.*TVA',
    r'(?i)article.*L?5362',
    r'(?i)article.*261',
    r'(?i)pr[ée]fet\s+de\s+la\s+r[ée]gion',
]


def preprocess_image(img):
    img = img.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def extract_invoices_by_page(pdf_path):
    """
    Parcourt TOUTES les pages du PDF.
    Retourne une liste de (num_page, texte_ocr) pour les pages avec un TAU_.
    Pages sans TAU_ (convocations, programmes) ignorees.

    Stratégie en deux passes :
    1) Texte natif PyMuPDF (quasi instantané) — suffit pour PDFs éditeur web.
    2) EasyOCR uniquement si le texte natif est trop court ou ne contient pas TAU_
       sur AUCUNE page (PDF scanné).
    """
    invoices = []
    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        logging.info(f"  -> PDF de {total} pages, scan complet...")

        # Passe 1 : texte natif sur toutes les pages (rapide)
        native_texts = []
        any_tau_native = False
        for page_num in range(total):
            page = doc.load_page(page_num)
            native = page.get_text("text").strip()
            native_texts.append(native)
            if re.search(r'TAU_\d{4}[-_]\d+', native):
                any_tau_native = True

        for page_num in range(total):
            native = native_texts[page_num]
            native_has_tau = bool(re.search(r'TAU_\d{4}[-_]\d+', native))

            # Décision : utiliser texte natif ou OCR ?
            # - Si le PDF entier a au moins un TAU_ natif (PDF éditeur) :
            #     → utiliser natif pour toutes les pages (y compris les pages
            #       sans TAU_ pour éviter faux positifs OCR)
            # - Si aucun TAU_ natif (PDF scanné) : toujours OCR
            if any_tau_native:
                if native_has_tau:
                    logging.info(f"  -> Page {page_num + 1}/{total} (natif) — TAU_ détecté")
                    invoices.append((page_num + 1, native))
                else:
                    logging.info(f"  -> Page {page_num + 1}/{total} (natif) — pas de TAU_, ignorée")
            else:
                # PDF scanné : OCR nécessaire
                logging.info(f"  -> Page {page_num + 1}/{total} (OCR)...")
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=DPI_HIGH)
                pil_img = Image.open(io.BytesIO(pix.tobytes()))
                img_processed = preprocess_image(pil_img)
                text = extract_text(img_processed)
                if re.search(r'TAU_\d{4}[-_]\d+', text):
                    logging.info(f"  -> TAU_ détecté page {page_num + 1}")
                    invoices.append((page_num + 1, text))

        doc.close()
        logging.info(f"  -> {len(invoices)} page(s) avec facture detectee(s)"
                     + (" [mode natif]" if any_tau_native else " [mode OCR]"))
    except Exception as e:
        logging.error(f"Erreur OCR sur {pdf_path}: {e}")
    return invoices


def string_to_date(date_str):
    # Supporte "10/02/2026", "10 / 02 / 2026", "10.02.2026", etc.
    m = re.match(r'(\d{2})\s*[/.\-]\s*(\d{2})\s*[/.\-]\s*(\d{4})', date_str.strip())
    if m:
        try:
            dt = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if 2000 <= dt.year <= 2100:
                return dt
        except Exception:
            pass
    return None


def clean_montant(m_str):
    s = str(m_str).replace(' ', '').replace('€', '').replace('EUR', '')
    # Correction artefacts OCR : lettres O/o lues à la place de 0 dans les décimales
    # ex: "465.OO" -> "465.00", "0.0o" -> "0.00"
    s = re.sub(r'(?<=[.,\d])[Oo]', '0', s)
    s = re.sub(r'[Oo](?=[.,\d])', '0', s)
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        return None


def _is_junk_line(line):
    """Retourne True si la ligne fait partie de l'entête Pôle Tauroentum ou est une adresse."""
    lower = line.lower()
    for junk in JUNK_WORDS:
        if junk in lower:
            return True
    # Code postal (5 chiffres + espace)
    if re.search(r'\d{5}\s', line):
        return True
    # Adresse (rue, avenue, etc.)
    if re.search(r'\b(rue|avenue|boulevard|chemin|route|allée|impasse|zi|z\.i|za|z\.a|bp)\b', lower):
        return True
    # Ligne trop courte (<4 lettres utiles)
    if len(re.sub(r'[^A-Za-zÀ-ÿ]', '', line)) < 4:
        return True
    # Date seule
    if re.match(r'^\d{2}[/.\-]\d{2}[/.\-]\d{4}', line.strip()):
        return True
    return False


def parse_invoice_text(text):
    data = {
        "num_facture": "",
        "client": "",
        "date_facture": None,
        "date_echeance": None,
        "montant_ttc": None,
        "session": "",
        "type_facture": "B2B",
    }

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # ─── 1) N° Facture ──────────────────────────────────────────
    m_facture = re.search(r'(?i)(TAU_\d{4}[\-\_]\d+)', text)
    if m_facture:
        data["num_facture"] = m_facture.group(1).strip()

    # ─── 2) Dates ────────────────────────────────────────────────
    # Priorité : chercher la ligne contenant TAU_ qui a le format :
    # "TAU_XXXX-YYY  DATE_FACTURE  N_CLIENT  DATE_ECHEANCE"
    tau_line_dates = None
    for line in lines:
        if "TAU_" in line:
            ds = re.findall(r'\d{2}[\-/\.]\d{2}[\-/\.]\d{4}', line)
            if len(ds) >= 2:
                tau_line_dates = ds
                break
            elif len(ds) == 1:
                tau_line_dates = ds
                break

    if tau_line_dates and len(tau_line_dates) >= 2:
        data["date_facture"] = string_to_date(tau_line_dates[0])
        data["date_echeance"] = string_to_date(tau_line_dates[1])
    elif tau_line_dates and len(tau_line_dates) == 1:
        data["date_facture"] = string_to_date(tau_line_dates[0])
        if data["date_facture"]:
            data["date_echeance"] = data["date_facture"] + datetime.timedelta(days=30)
    else:
        # Fallback : première date valide du document
        valid_dates = []
        for d_str in re.findall(r'\d{2}\s*[/.\-]\s*\d{2}\s*[/.\-]\s*\d{4}', text):
            dt = string_to_date(d_str)
            if dt:
                valid_dates.append(dt)
        if valid_dates:
            data["date_facture"] = valid_dates[0]
            data["date_echeance"] = valid_dates[0] + datetime.timedelta(days=30)

    # ─── 3) Session ──────────────────────────────────────────────
    m_session = re.search(
        r'(?i)Session(?:\s*du)?\s*(\d{2}[/.\-]\d{2}[/.\-]\d{4}\s*au\s*\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_session:
        data["session"] = m_session.group(1).strip()

    # ─── 4) TYPE (CPF / CDC / B2B) — détecté SUR TOUT LE TEXTE ─
    text_lower = text.lower()
    if re.search(r'compte\s+personnel\s+de\s+formation', text_lower):
        data["type_facture"] = "CPF"
    elif re.search(r'caisse\s+des\s+d.p.ts', text_lower):
        data["type_facture"] = "CDC"

    # ─── 5) CLIENT — recherche inversée depuis le TAU_ ──────────
    client_name = None
    tau_index = -1
    for i, l in enumerate(lines):
        if "TAU_" in l:
            tau_index = i
            break

    if tau_index > 0:
        # Remonter les lignes au-dessus du TAU_ pour trouver le nom du client
        for i in range(tau_index - 1, max(-1, tau_index - 10), -1):
            candidate = lines[i].strip()
            if _is_junk_line(candidate):
                continue
            # C'est probablement le client
            # Nettoyage des artefacts OCR courants
            candidate = re.sub(r'[_\(\)\[\]{}]', '', candidate).strip()
            candidate = re.sub(r'\beŸ\b', '', candidate).strip()
            if len(candidate) >= 3:
                client_name = candidate
                break

    # Fallback A: forme juridique sur les lignes avant TAU_ (même celles avec adresse)
    if not client_name and tau_index > 0:
        for i in range(tau_index - 1, max(-1, tau_index - 15), -1):
            candidate = lines[i].strip()
            # Chercher NOM + forme juridique (ex: "FT MARINE SAS") ou forme juridique + NOM (ex: "SARL BOYER")
            m_soc = re.search(
                r'([A-Z][A-Z0-9 &\-\.]{1,30}\s+(?:SARL|SAS|SA|EURL|SASU|ASSOCIATION|SNC|SCOP|GIE)\b'
                r'|(?:SARL|SAS|EURL|SASU|ASSOCIATION|SNC)\s+[A-Z][A-Z0-9 &\-\.]{2,30})',
                candidate)
            if m_soc:
                client_name = m_soc.group(0).strip().rstrip('&- ')
                if len(re.sub(r'[^A-Za-z]', '', client_name)) >= 4:
                    break
                client_name = None

    # Fallback B: forme juridique n'importe où dans le texte
    if not client_name:
        m_soc = re.search(r'\b((?:SARL|SAS|SA|EURL|SASU|ASSOCIATION)\s+[A-Z][A-Z &\-\.]+)', text)
        if m_soc:
            client_name = m_soc.group(1).strip()

    # Si le type est CPF, le client est "CPF" (Caisse des Dépôts)
    if data["type_facture"] == "CPF":
        data["client"] = "CPF"
    elif data["type_facture"] == "CDC":
        data["client"] = "CDC"
    elif client_name:
        # Piste A : Fuzzy matching avec le dictionnaire de clients connus
        corrected, score, was_corrected = match_client(client_name)
        if was_corrected:
            logging.info(f"Client corrige: '{client_name}' -> '{corrected}' (score={score:.2f})")
        data["client"] = corrected

    # ─── 6) MONTANT TTC — Extraction en 4 passes ────────────────
    montant_val = None

    # NETTOYAGE : Supprimer les lignes de footer avant extraction
    # pour éviter que "capital de 7500€" pollue les résultats
    clean_lines = []
    for line in lines:
        is_footer = False
        for pattern in FOOTER_PATTERNS:
            if re.search(pattern, line):
                is_footer = True
                break
        if not is_footer:
            clean_lines.append(line)
    clean_text = '\n'.join(clean_lines)
    # Corriger les O/o OCR dans les montants du texte nettoyé (ex: "465.OO€" -> "465.00€")
    clean_text = re.sub(r'(\d)[Oo]([Oo€\s])', lambda m: m.group(0).replace('O','0').replace('o','0'), clean_text)
    clean_text = re.sub(r'(\d\.[Oo0][Oo])', lambda m: m.group(0).replace('O','0').replace('o','0'), clean_text)

    # Passe 1 : "Total TTC" / "Net à payer" / "Montant" / "Restant du" explicite
    m1 = re.search(
        r'(?i)(?:Total\s*TTC|Net\s*[àa]\s*payer|Montant\s+TTC|Tarif|Restant\s+du|^Montant)\s*[:\-]?\s*([\d\s]+[,.\-OoZzlI]+\d*)\s*(?:€|EUR|[eë])?',
        clean_text, re.MULTILINE)
    if m1:
        montant_val = clean_montant(m1.group(1))

    # Passe 2 : Nombres suivis de "€" ou "EUR" n'importe où (hors footer)
    if not montant_val:
        amounts = []
        for m2 in re.finditer(r'([\d\s.,]+)\s*(?:€|EUR)', clean_text):
            v = clean_montant(m2.group(1))
            if v is not None and v > 10:
                amounts.append(v)
        if amounts:
            montant_val = max(amounts)

    # Passe 3 : Nombres comme "2800€" mal lus comme "2800ë"
    if not montant_val:
        amounts = []
        for m3 in re.finditer(r'(\d{2,})\s*[€ëé]', clean_text):
            v = clean_montant(m3.group(1))
            if v is not None and v > 50:
                amounts.append(v)
        if amounts:
            montant_val = max(amounts)

    # Passe 4 : Dernier recours — le plus gros nombre décimal dans le corps
    if not montant_val:
        amounts = []
        for line in clean_lines[-15:]:
            for m4 in re.findall(r'(\d{2,}[,.]\d{2})', line):
                v = clean_montant(m4)
                if v is not None and v > 50:
                    amounts.append(v)
        if amounts:
            montant_val = max(amounts)

    data["montant_ttc"] = montant_val
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
    if not os.path.exists(EXCEL_FILE):
        logging.error("Fichier Excel introuvable.")
        return "ERROR"

    try:
        wb = load_workbook(EXCEL_FILE)
        ws = wb["Ventes_Factures"]

        num_facture_val = data.get("num_facture")
        if check_duplicate(ws, num_facture_val):
            logging.warning(f"Facture {num_facture_val} déjà présente - ignorée.")
            wb.close()
            return "DUPLICATE"

        # Trouver la première ligne vide
        target_row = ws.max_row + 1
        for r in range(2, ws.max_row + 2):
            if not ws[f"A{r}"].value:
                target_row = r
                break

        ws[f"A{target_row}"] = num_facture_val
        ws[f"B{target_row}"] = data.get("client", "")
        ws[f"C{target_row}"] = data.get("type_facture", "B2B")
        ws[f"E{target_row}"] = data.get("session", "")

        dfact = data.get("date_facture")
        if dfact and isinstance(dfact, datetime.date):
            ws[f"F{target_row}"] = dfact
            ws[f"F{target_row}"].number_format = 'DD/MM/YYYY'

        dech = data.get("date_echeance")
        if dech and isinstance(dech, datetime.date):
            ws[f"G{target_row}"] = dech
            ws[f"G{target_row}"].number_format = 'DD/MM/YYYY'

        mnt = data.get("montant_ttc")
        if mnt is not None:
            ws[f"H{target_row}"] = float(mnt)

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
            time.sleep(2)
            if not os.path.exists(filepath):
                return
            # Éviter double-enfilage (watchdog déclenche parfois deux événements)
            if filepath in list(_pdf_queue.queue):
                return
            logging.info(f"Nouveau fichier détecté (enfilé) : {filepath}")
            _pdf_queue.put(filepath)


def log_to_json(filepath, data, score, status):
    log_file = os.path.join(BASE_DIR, "workflow.json")

    # Safe dump for datetime objects
    safe_data = {}
    for k, v in data.items():
        if isinstance(v, datetime.date):
            safe_data[k] = v.isoformat()
        else:
            safe_data[k] = v

    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "file": os.path.basename(filepath),
        "data_extracted": safe_data,
        "confidence_score": score,
        "status": status,
        "user": os.getlogin()
    }
    try:
        logs_list = []
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                try:
                    logs_list = json.load(f)
                except ValueError:
                    logs_list = []
        logs_list.append(entry)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs_list, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Erreur ecriture log JSON : {e}")


def calculate_confidence(data):
    conf_score = 10
    if not data.get("num_facture"):
        conf_score -= 3
    if not data.get("client"):
        conf_score -= 2
    if not data.get("date_facture"):
        conf_score -= 2
    if not data.get("date_echeance"):
        conf_score -= 2
    if not data.get("montant_ttc"):
        conf_score -= 3
    return max(0, conf_score)


def process_pdf(filepath):
    filename = os.path.basename(filepath)
    try:
        logging.info(f"Extraction du texte pour {filename}...")
        invoice_pages = extract_invoices_by_page(filepath)

        if not invoice_pages:
            logging.warning(f"Aucune facture TAU_ détectée dans {filename} - fichier ignoré")
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
            return

        success_count = 0
        error_count = 0
        skip_count = 0

        for page_num, text in invoice_pages:
            data = parse_invoice_text(text)
            score = calculate_confidence(data)
            num = data.get('num_facture', f'page_{page_num}')
            logging.info(
                f"  [p.{page_num}] {num} | client={data.get('client', '?')} | "
                f"montant={data.get('montant_ttc', '?')} | score={score}/10")

            if data.get("type_facture") == "CPF":
                # Factures CPF : injection directe sans validation UI
                # (client = "CPF", données standardisées)
                logging.info(f"  [p.{page_num}] Facture CPF — injection directe (sans UI)")
                status = inject_to_excel(data)
            elif score < 7:
                # Score insuffisant : soumettre à validation manuelle
                logging.info(
                    f"  [p.{page_num}] Score {score}/10 < 7 — envoi vers UI de validation")
                ui_status, ui_data = process_with_ui(filepath, prefilled_data=data)
                if ui_status == "SUCCESS" and ui_data:
                    # L'utilisateur a corrigé les données — on injecte ses corrections
                    status = inject_to_excel(ui_data)
                    data = ui_data  # pour log_to_json
                else:
                    # Rejet ou fermeture fenêtre — on skip cette page
                    logging.info(f"  [p.{page_num}] Rejet UI — page ignorée")
                    skip_count += 1
                    log_to_json(filepath, data, score, "REJECTED_BY_USER")
                    continue
            else:
                status = inject_to_excel(data)

            if status == "SUCCESS":
                success_count += 1
                log_to_json(filepath, data, score, "SUCCESS")
            elif status == "DUPLICATE":
                skip_count += 1
                log_to_json(filepath, data, score, "DUPLICATE")
            else:
                error_count += 1
                log_to_json(filepath, data, score, "ERROR")

        # Résumé global du fichier
        logging.info(f"BILAN {filename}: {success_count} injectées, {skip_count} doublons, {error_count} erreurs")
        if toaster:
            try:
                # La notification Windows (win10toast) provoque un "hard-crash" silencieux
                # lorsqu'elle est exécutée depuis un thread d'arrière-plan (watchdog) dans l'exécutable compilé.
                # Nous désactivons temporairement ceci pour éviter la boucle de plantage.
                # toaster.show_toast("Traitement terminé",
                #    f"{filename}: {success_count} factures injectées, {skip_count} doublons, {error_count} erreurs",
                #    duration=8, threaded=True)
                pass
            except Exception as e:
                logging.warning(f"Erreur notification : {e}")

        # Déplacement du fichier
        if error_count == 0:
            shutil.move(filepath, os.path.join(FOLDER_OUT, filename))
        else:
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))

    except Exception as e:
        logging.error(f"Erreur globale sur {filename} : {e}")
        try:
            shutil.move(filepath, os.path.join(FOLDER_ERR, filename))
        except Exception as mv_err:
            logging.error(f"Failed to move file to error folder: {mv_err}")


def process_existing_files():
    """Enfile les PDFs déjà présents dans FOLDER_IN au démarrage."""
    existing = [f for f in os.listdir(FOLDER_IN) if f.lower().endswith('.pdf')]
    if existing:
        logging.info(f"Scan démarrage : {len(existing)} PDF(s) déjà présents dans {FOLDER_IN}")
        for filename in existing:
            filepath = os.path.join(FOLDER_IN, filename)
            logging.info(f"Enfilé au démarrage : {filename}")
            _pdf_queue.put(filepath)
    else:
        logging.info(f"Scan démarrage : aucun PDF en attente dans {FOLDER_IN}")


def start_watcher():
    """
    Lance watchdog dans un thread daemon, puis tourne en boucle principale
    pour dépiler _pdf_queue et appeler process_pdf.
    Tkinter DOIT s'exécuter depuis le thread principal → cette boucle tourne
    dans le thread principal, watchdog dans un thread séparé.
    """
    logging.info(f"Démarrage surveillance sur {FOLDER_IN}")
    print(f"Watchdog actif. Déposez un PDF dans {FOLDER_IN}")

    # Watchdog dans un thread daemon (ne bloque pas le thread principal)
    event_handler = InvoiceHandler()
    observer = Observer()
    observer.schedule(event_handler, FOLDER_IN, recursive=False)
    observer.start()

    # Enfile les PDFs déjà présents
    process_existing_files()

    # Boucle principale — dépile la queue et traite les PDFs
    try:
        while True:
            try:
                filepath = _pdf_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                process_pdf(filepath)
            except Exception as e:
                logging.error(f"Erreur non gérée dans process_pdf : {e}\n{traceback.format_exc()}")
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    start_watcher()
