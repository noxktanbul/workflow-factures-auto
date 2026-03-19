"""
ocr_engine.py — Module OCR centralisé
Remplace pytesseract par EasyOCR pour une meilleure lecture des PDFs
générés par éditeur web (tables CSS) et du texte petit/gris anti-aliasé.

Singleton : le modèle EasyOCR est chargé une seule fois au premier appel.
Fallback  : si EasyOCR échoue, tente pytesseract si disponible.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Singleton EasyOCR Reader
# ─────────────────────────────────────────────────────────────
_reader = None


def get_reader():
    """Initialise et retourne le reader EasyOCR (singleton)."""
    global _reader
    if _reader is None:
        try:
            import easyocr
            logger.info("Initialisation EasyOCR (première utilisation)...")
            _reader = easyocr.Reader(['fr'], gpu=False, verbose=False)
            logger.info("EasyOCR initialisé avec succès.")
        except ImportError:
            logger.error("EasyOCR non installé. Installez avec: pip install easyocr")
            raise
        except Exception as e:
            logger.error(f"Erreur initialisation EasyOCR: {e}")
            raise
    return _reader


def extract_text(pil_image):
    """
    Extrait le texte d'une image PIL.
    Remplaçant direct de pytesseract.image_to_string(img, lang='fra').
    
    Args:
        pil_image: Image PIL (peut être en mode L, RGB, ou RGBA)
    
    Returns:
        str: Texte extrait de l'image
    """
    try:
        # EasyOCR attend un array numpy
        img_array = np.array(pil_image)
        
        reader = get_reader()
        
        # detail=1 retourne [(bbox, text, confidence), ...]
        # On trie par position verticale (top-to-bottom) puis horizontale
        results = reader.readtext(img_array, detail=1, paragraph=False)
        
        if not results:
            logger.warning("EasyOCR: aucun texte détecté dans l'image")
            return _fallback_tesseract(pil_image)
        
        # Trier par position Y (haut en bas), puis X (gauche à droite)
        # bbox format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))
        
        # Regrouper les résultats en lignes (même hauteur Y ± tolérance)
        lines = _group_into_lines(results)
        
        return '\n'.join(lines)
        
    except Exception as e:
        logger.error(f"Erreur EasyOCR: {e}")
        return _fallback_tesseract(pil_image)


def _group_into_lines(results, y_tolerance=25):
    """
    Regroupe les détections EasyOCR en lignes de texte cohérentes.
    EasyOCR retourne des mots/blocs individuels qu'il faut ré-assembler.

    Args:
        results: Liste de (bbox, text, confidence) depuis EasyOCR
        y_tolerance: Tolérance verticale pour considérer deux textes sur la même ligne.
                     25px par défaut — calibré pour les PDFs de facturation Tauroentum
                     (compense les légers décalages verticaux de l'OCR sur texte scanné).

    Returns:
        Liste de strings (une par ligne)
    """
    if not results:
        return []

    # Prétraitement : Nettoyage des dates mal lues (espaces au milieu des "/" ou ".")
    import re
    cleaned_results = []
    for bbox, text, conf in results:
        # Fusion des dates comme "05 / 03 / 2026" ou "05 . 10 . 25"
        text = re.sub(r'(\d{2})\s*([/.\-])\s*(\d{2})\s*([/.\-])\s*(\d{4}|\d{2})', r'\1\2\3\4\5', text)
        cleaned_results.append((bbox, text, conf))
    results = cleaned_results

    lines = []
    current_line = []
    current_y = results[0][0][0][1]  # Y du premier résultat

    for bbox, text, conf in results:
        y = bbox[0][1]  # Y du coin supérieur gauche

        if abs(y - current_y) > y_tolerance:
            # Nouvelle ligne
            if current_line:
                # Trier par X dans la ligne
                current_line.sort(key=lambda item: item[0])
                lines.append(' '.join(t for _, t in current_line))
            current_line = [(bbox[0][0], text)]  # (x, text)
            current_y = y
        else:
            current_line.append((bbox[0][0], text))
    
    # Dernière ligne
    if current_line:
        current_line.sort(key=lambda item: item[0])
        lines.append(' '.join(t for _, t in current_line))
    
    return lines


def _fallback_tesseract(pil_image):
    """Fallback vers pytesseract si EasyOCR échoue."""
    try:
        import pytesseract
        logger.warning("Fallback vers Tesseract OCR...")
        pytesseract.pytesseract.tesseract_cmd = r'C:\Tesseract-OCR\tesseract.exe'
        return pytesseract.image_to_string(pil_image, lang='fra')
    except ImportError:
        logger.error("Ni EasyOCR ni pytesseract ne sont disponibles.")
        return ""
    except Exception as e:
        logger.error(f"Fallback Tesseract échoué: {e}")
        return ""
