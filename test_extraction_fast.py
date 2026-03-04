import os
import re
import fitz  # PyMuPDF
import json
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import io

pytesseract.pytesseract.tesseract_cmd = r'C:\Tesseract-OCR\tesseract.exe'

DPI_HIGH = 300

def preprocess_image(img):
    """Amélioration de base pour aider l'OCR"""
    # Convertir en niveaux de gris
    img = img.convert('L')
    # Augmenter le contraste
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    # Binarisation basique et légère netteté
    img = img.filter(ImageFilter.SHARPEN)
    return img

def parse_invoice_text(text):
    data = {
        "num_facture": None,
        "client": None,
        "date_facture": None,
        "date_echeance": None,
        "montant_ttc": None,
        "session": None
    }

    # Extract num facture logic here

    m_date = re.search(r'(\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_date:
        data["date_facture"] = m_date.group(1).strip()

    m_session = re.search(r'(?i)Session(?:\s*du)?\s*(\d{2}[/.\-]\d{2}[/.\-]\d{4}\s*au\s*\d{2}[/.\-]\d{2}[/.\-]\d{4})', text)
    if m_session:
        data["session"] = m_session.group(1).strip()

    # Essai de choper le client (ligne sous SOCIETE)
    m_client = re.search(r'(?i)SOCIETE\s*(.*)', text)
    if m_client:
        data["client"] = m_client.group(1).strip()

    # Montant logic here

    return data

pdf_path = r"C:\Users\TAUROENTUM1\.gemini\antigravity\scratch\workflow_factures\References\Factures ventes non réglées part.1.pdf"
try:
    doc = fitz.open(pdf_path)
    page = doc.load_page(1) # Page 2
    pix = page.get_pixmap(dpi=DPI_HIGH)
    img = Image.open(io.BytesIO(pix.tobytes()))
    text = pytesseract.image_to_string(img, lang='fra')
    doc.close()

    print("EXTRACTION BRUTE PAGE 1:")
    print(text)
    print("\nDONNEES IDENTIFIEES:")
    print(json.dumps(parse_invoice_text(text), indent=4, ensure_ascii=False))
except Exception as e:
    print(f"Erreur: {e}")
