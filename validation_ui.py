import os
import time
import re
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageTk
import io
import tkinter as tk
from tkinter import messagebox, filedialog
from openpyxl import load_workbook
import shutil
import logging

import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FOLDER_IN = os.path.join(BASE_DIR, "Entrant")
FOLDER_OUT = os.path.join(BASE_DIR, "Traite")
FOLDER_ERR = os.path.join(BASE_DIR, "Erreur")
EXCEL_FILE = os.path.join(BASE_DIR, "References", "Echeancier_cible.xlsx")

logging.basicConfig(filename=os.path.join(BASE_DIR, "workflow.log"), level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

pytesseract.pytesseract.tesseract_cmd = r'C:\Tesseract-OCR\tesseract.exe'

def preprocess_image(img):
    img = img.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    return img

def extract_text_and_first_page_image(pdf_path):
    texts = []
    first_page_img = None
    doc = fitz.open(pdf_path)
    try:
        max_pages = min(len(doc), 3)
        for page_num in range(max_pages):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=150) # lower DPI for UI preview
            pil_img = Image.open(io.BytesIO(pix.tobytes()))
            if page_num == 0:
                first_page_img = pil_img.copy()
            
            # OCR is done on 300dpi internally usually, but 150dpi here for speed during UI
            img_ocr = preprocess_image(pil_img)
            text = pytesseract.image_to_string(img_ocr, lang='fra')
            texts.append(text)
    except Exception as e:
        logging.error(f"Erreur OCR sur {pdf_path}: {e}")
    finally:
        try:
            doc.close()
        except Exception:
            pass
        full_text = "\n".join(texts) + "\n" if texts else ""
    return full_text, first_page_img

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
            except:
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
        
        target_row = ws.max_row + 1
        for r in range(2, ws.max_row + 2):
            if not ws[f"A{r}"].value:
                target_row = r
                break
                
        ws[f"A{target_row}"] = data["num_facture"]
        ws[f"B{target_row}"] = data["client"]
        ws[f"C{target_row}"] = "B2B"  
        ws[f"E{target_row}"] = data["session"]
        ws[f"F{target_row}"] = data["date_facture"]
        ws[f"G{target_row}"] = data["date_echeance"]
        
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

class ValidationUI:
    def __init__(self, root, pdf_path, extracted_data, img_preview):
        self.root = root
        self.root.title("Validation Facture - Google Antigravity")
        self.root.geometry("1000x700")
        
        self.pdf_path = pdf_path
        self.data = extracted_data
        self.img_preview = img_preview
        self.result = False
        self.final_data = {}
        
        self.setup_ui()
        
    def setup_ui(self):
        # Left frame: Image preview
        left_frame = tk.Frame(self.root, width=500, bg="gray")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        if self.img_preview:
            # Resize image to fit height
            img_w, img_h = self.img_preview.size
            ratio = 650 / img_h
            new_size = (int(img_w * ratio), 650)
            img_resized = self.img_preview.resize(new_size, Image.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(img_resized)
            
            lbl_img = tk.Label(left_frame, image=self.tk_img)
            lbl_img.pack(padx=10, pady=10)
        
        # Right frame: Form
        right_frame = tk.Frame(self.root, width=400, padx=20, pady=20)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        tk.Label(right_frame, text="Vérification des Données", font=("Arial", 16, "bold")).pack(pady=20)
        
        self.entries = {}
        fields = [
            ("Numéro Facture", "num_facture"),
            ("Client", "client"),
            ("Date Facture", "date_facture"),
            ("Date Échéance", "date_echeance"),
            ("Session", "session"),
            ("Montant TTC", "montant_ttc")
        ]
        
        for label_text, key in fields:
            frame = tk.Frame(right_frame)
            frame.pack(fill=tk.X, pady=5)
            
            lbl = tk.Label(frame, text=label_text, width=15, anchor="w")
            lbl.pack(side=tk.LEFT)
            
            ent_var = tk.StringVar(value=self.data.get(key, ""))
            ent = tk.Entry(frame, textvariable=ent_var, width=30)
            ent.pack(side=tk.LEFT, padx=10)
            
            # Highlight missing fields
            if not ent_var.get():
                ent.config(bg="lightcoral")
                
            self.entries[key] = ent_var
            
        btn_frame = tk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=40)
        
        tk.Button(btn_frame, text="Valider & Injecter", command=self.on_validate, bg="lightgreen", height=2).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        tk.Button(btn_frame, text="Rejeter", command=self.on_reject, bg="salmon", height=2).pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)

    def on_validate(self):
        self.final_data = {key: var.get() for key, var in self.entries.items()}
        self.result = True
        self.root.destroy()
        
    def on_reject(self):
        self.result = False
        self.root.destroy()

def process_with_ui(pdf_path):
    print(f"Demarrage OCR pour UI: {pdf_path}")
    text, first_page_img = extract_text_and_first_page_image(pdf_path)
    data = parse_invoice_text(text)
    
    # Lancement de l'UI
    root = tk.Tk()
    app = ValidationUI(root, pdf_path, data, first_page_img)
    root.mainloop()
    
    # After UI is closed, wait a tiny bit to ensure resources free up
    time.sleep(0.5)
    
    out_path = os.path.join(FOLDER_OUT, os.path.basename(pdf_path))
    err_path = os.path.join(FOLDER_ERR, os.path.basename(pdf_path))

    if app.result:
        print("Validation manuelle confirmée.")
        status = inject_to_excel(app.final_data)
        if status == "SUCCESS":
            try:
                # Need absolute path move for windows sometimes
                shutil.move(os.path.abspath(pdf_path), os.path.abspath(out_path))
                print("Injection et déplacement OK.")
            except Exception as e:
                print(f"Injection ok mais erreur move : {e}")
        elif status == "DUPLICATE":
            print("Doublon détecté après validation. Fichier déplacé en erreur.")
            try:
                shutil.move(os.path.abspath(pdf_path), os.path.abspath(err_path))
            except Exception as e:
                print(f"Erreur move pour doublon : {e}")
        else:
            try:
                shutil.move(os.path.abspath(pdf_path), os.path.abspath(err_path))
                print("Injection Echouée, fichier déplacé en erreur.")
            except Exception as e:
                print(f"Injection echouee et erreur move : {e}")
    else:
        print("Rejet par l'utilisateur.")
        try:
             shutil.move(os.path.abspath(pdf_path), os.path.abspath(err_path))
        except Exception:
             pass

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if os.path.exists(pdf_path):
            process_with_ui(pdf_path)
        else:
            print(f"Fichier introuvable : {pdf_path}")
    else:
        # Test file for UI
        test_file = os.path.join(BASE_DIR, "References", "Factures ventes non réglées part.3.pdf")
        if os.path.exists(test_file):
            test_copy = os.path.join(FOLDER_IN, "Test_UI_3.pdf")
            shutil.copy(test_file, test_copy)
            process_with_ui(test_copy)
        else:
            print("Fichier de test introuvable.")
