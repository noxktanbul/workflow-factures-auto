"""
client_dictionary.py — Piste A : Dictionnaire de clients connus + fuzzy matching
Corrige les noms de clients B2B bruités par l'OCR en les comparant
à la liste officielle des clients.

Utilise RapidFuzz (Levenshtein optimisé, bien plus performant pour les erreurs OCR).
"""

import logging
from rapidfuzz import fuzz, process as rf_process

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# DICTIONNAIRE DES CLIENTS CONNUS
# Noms canoniques tels qu'ils apparaissent dans la comptabilité.
# On stocke aussi les formes courtes (acronymes, raccourcis) comme alias.
# ─────────────────────────────────────────────────────────────

CLIENTS_CONNUS = [
    "ACPM",
    "ACTION MER",
    "BLEU EVASION",
    "BOLUDA MARSEILLE FOS",
    "BRITTANY FERRIES",
    "BTMF",
    "CALANQUES BLEU MISTRAL",
    "Calm Yachting Limited",
    "CARRODANO-POISSONS VIVANTS",
    "CEFCM CONCARNEAU",
    "CFEMF",
    "CHANTIER NAVAL DE MARSEILLE",
    "CLINIQUE LA PHOCEANNE",
    "CLINIQUE PHOCEANNE SUD",
    "CMAR PACA",
    "COOPERATIVE DU LAMANAGE DE MARSEILLE",
    "CORSICA LINEA",
    "DGA",
    "DNGCD",
    "EDGE CREW",
    "ESPMER",
    "EXAIL",
    "FOSELEV MARINE",
    "FRANCE TRAVAIL POEI",
    "FUNSEAKER",
    "GAZ OCEAN",
    "GENAVIR",
    "GHJULIA Shipping",
    "GPMM",
    "ICARD MARITIME",
    "IME ESTEREL",
    "INSEIT",
    "INTERSUB",
    "JIFMAR",
    "LA MERIDIONALE",
    "LES AMIS DES CALANQUES",
    "Les Bateliers de la Cote d'Azur",
    "M/Y EUPHORIA II",
    "MARITIMA",
    "MEDITERRANEENNE DE SERVICES MARITIMES",
    "METROPOLE",
    "NAVY SERVICE",
    "NEKTON",
    "OLYMPIQUE LYONNAIS SASU",
    "OPCO 2i",
    "OPCO MOBILITES",
    "PHARES ET BALISES",
    "POLE TAUROENTUM",
    "PONCHARREAU-AMSELLEM",
    "PORQUEROLLES MARINE SERVICES",
    "REGION",
    "RTM/Campus",
    "SAAS OFFSHORE",
    "SAPIENS",
    "SARL BOYER",
    "SARL LE CALENDAL",
    "SAS EMC - LES BATEAUX VERTS",
    "SAS VILDOR",
    "SEANERGIES OCEANE",
    "SERMAP SHIPPING",
    "SMVI",
    "SNC TRANSRADES",
    "SNRTM",
    "SOCIETE FRANCAISE DE MARREE",
    "SOCIETE NOUVELLOISE DE REMORQUAGE",
    "SOCIETE PAUL RICARD",
    "Syndicat Professionnel des Pilotes de Marseille et du Golfe de Fos",
    "THALES - SYSTEMGIE",
    "THALIA SHIPPING",
    "TLV Transports Maritimes et Terrestres du Littoral Varois",
    "UVEA MARINE SERVICE",
    "UVEA MARINE SERVICE UMS",
]

# Seuil de similarité (0.0 à 1.0)
# 0.65 = assez permissif pour corriger les erreurs OCR courantes
# tout en évitant les faux positifs
FUZZY_THRESHOLD = 0.65

# Seuil haut : au-dessus, on corrige automatiquement sans hésiter
FUZZY_HIGH_CONFIDENCE = 0.85


def _normalize(name):
    """Normalise un nom pour comparaison (majuscules, espaces, tirets)."""
    if not name:
        return ""
    # Majuscules, nettoyer espaces multiples
    s = name.upper().strip()
    # Remplacer tirets, underscores, slashes par des espaces
    for char in ['-', '_', '/', '.']:
        s = s.replace(char, ' ')
    # Supprimer espaces multiples
    while '  ' in s:
        s = s.replace('  ', ' ')
    return s


def match_client(ocr_name):
    """
    Tente de corriger un nom de client OCR bruité en le comparant
    au dictionnaire des clients connus.
    
    Args:
        ocr_name: Nom du client tel qu'extrait par l'OCR
    
    Returns:
        tuple: (nom_corrigé, score_confiance, was_corrected)
            - nom_corrigé : le nom canonique si match trouvé, sinon l'original
            - score_confiance : 0.0 à 1.0
            - was_corrected : True si le nom a été corrigé
    """
    if not ocr_name or len(ocr_name.strip()) < 2:
        return ocr_name, 0.0, False

    ocr_clean = ocr_name.strip()

    # 0) Filtre anti-adresse : rejeter sans fuzzy si ressemble à une adresse
    import re as _re
    _addr_pattern = _re.compile(
        r'(?i)\b(\d+\s+(rue|avenue|boulevard|chemin|route|all[eé]e|impasse|zi|za|bp)\b'
        r'|\b\d{5}\b)',
        _re.IGNORECASE
    )
    if _addr_pattern.search(ocr_clean):
        logger.debug(f"match_client: adresse détectée, rejet sans fuzzy '{ocr_clean}'")
        return ocr_clean, 0.0, False

    # 1) Match exact (insensible à la casse)
    for client in CLIENTS_CONNUS:
        if _normalize(ocr_clean) == _normalize(client):
            return client, 1.0, False  # Pas de correction nécessaire
    
    # 2) Le nom OCR contient-il un nom de client connu ? (ou vice-versa)
    ocr_norm = _normalize(ocr_clean)
    for client in CLIENTS_CONNUS:
        client_norm = _normalize(client)
        if client_norm in ocr_norm or ocr_norm in client_norm:
            score = len(min(client_norm, ocr_norm, key=len)) / len(max(client_norm, ocr_norm, key=len))
            if score > FUZZY_THRESHOLD:
                logger.info(f"Client match (contenu): '{ocr_clean}' → '{client}' (score={score:.2f})")
                return client, score, True
    
    # 3) Fuzzy matching — trouver le meilleur candidat via RapidFuzz
    normalized_clients = [_normalize(c) for c in CLIENTS_CONNUS]
    result = rf_process.extractOne(
        _normalize(ocr_clean),
        normalized_clients,
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_THRESHOLD * 100
    )

    if result is None:
        logger.debug(f"Aucun match client pour '{ocr_clean}'")
        return ocr_clean, 0.0, False

    best_match = CLIENTS_CONNUS[result[2]]
    best_score = result[1] / 100.0

    if best_score >= FUZZY_HIGH_CONFIDENCE:
        logger.info(f"Client corrigé (haute confiance): '{ocr_clean}' → '{best_match}' (score={best_score:.2f})")
        return best_match, best_score, True
    else:
        logger.info(f"Client corrigé (confiance moyenne): '{ocr_clean}' → '{best_match}' (score={best_score:.2f})")
        return best_match, best_score, True


def get_all_clients():
    """Retourne la liste complète des clients connus."""
    return list(CLIENTS_CONNUS)
