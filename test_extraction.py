import os
import re
import fitz  # PyMuPDF
import json
import pytesseract
from PIL import Image
import io

# Configurer le chemin de tesseract (vu dans l'audit)
pytesseract.pytesseract.tesseract_cmd = r'C:\Tesseract-OCR\tesseract.exe'

def extract_text_from_scanned_pdf(pdf_path):
    """Extrait le texte d'un PDF scanné via OCR avec Tesseract."""
    texts = []
    try:
        doc = fitz.open(pdf_path)
        print(f"  -> PDF avec {len(doc)} pages.")
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=300) # Rendu haute résolution
            img = Image.open(io.BytesIO(pix.tobytes()))

            # OCR en français
            text = pytesseract.image_to_string(img, lang='fra')
            texts.append(text)
        doc.close()
        full_text = "\n".join(texts) + "\n" if texts else ""
    except Exception as e:
        print(f"Erreur OCR sur {pdf_path}: {e}")
    return full_text

def parse_invoice_text(text):
    """Analyse le texte pour extraire les champs clés."""
    data = {
        "num_facture": None,
        "client": None,
        "date_facture": None,
        "date_echeance": None,
        "montant_ttc": None,
        "session": None
    }

    # Numéro de facture
    m_facture = re.search(r'(?i)facture\s*n[°º]?\s*[:\-]?\s*([A-Z0-9\-]+)', text)
    if not m_facture:
        m_facture_alt = re.search(r'(?i)n[°º]\s*facture\s*[:\-]?\s*([A-Z0-9\-]+)', text)
        if m_facture_alt:
            data["num_facture"] = m_facture_alt.group(1).strip()
    else:
        data["num_facture"] = m_facture.group(1).strip()

    # Date
    m_date = re.search(r'(\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_date:
        data["date_facture"] = m_date.group(1).strip()

    # Echéance
    m_echeance = re.search(r'(?i)(?:échéance|echeance|règlement)\s*.*?(?:\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_echeance:
         # extraction plus robuste de la date proche "échéance"
         dates = re.findall(r'(\d{2}[/.\-]\d{2}[/.\-]\d{4})', m_echeance.group(0))
         if dates:
             data["date_echeance"] = dates[-1]

    # Montant
    m_montant = re.search(r'(?i)(?:total\s*ttc|net\s*à\s*payer|montant\s*ttc)\s*[:\-]?\s*([\d\s]+[,.]\d{2})', text)
    if m_montant:
        data["montant_ttc"] = m_montant.group(1).replace(' ', '').strip()

    return data

def main():
    folder_path = r"C:\Users\TAUROENTUM1\.gemini\antigravity\scratch\workflow_factures\References"
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(folder_path, filename)
            print(f"\n--- OCR Traitement de : {filename} ---")

            text = extract_text_from_scanned_pdf(pdf_path)

            print("EXTRACTION BRUTE (200 premiers chars):")
            print(text[:200].replace('\n', ' ') + "...\n")

            data = parse_invoice_text(text)
            print("DONNEES IDENTIFIEES :")
            print(json.dumps(data, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    main()
