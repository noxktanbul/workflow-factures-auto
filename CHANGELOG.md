# Changelog

Toutes les modifications notables de ce projet sont documentées ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [Unreleased]

---

## [4.1.0] - 2026-03-06

### Ajouté
- `config.ini` : centralise tous les chemins et paramètres (plus de valeurs hardcodées)
- `clients_connus.json` : dictionnaire externe de patterns clients (modifiable sans recompiler)
- `launcher.bat` : démarrage automatique, boucle de redémarrage en cas de crash, raccourci bureau
- Constantes nommées `OCR_DPI`, `PREVIEW_DPI`, `MAX_PDF_PAGES`, `MIN_NATIVE_CHARS`, `ECHEANCE_JOURS`
- Échéance J+30 par défaut quand absente (affichée en orange dans l'UI)
- Champ `type_facture` (B2B / CPF / CDC) détecté automatiquement et injecté dans l'Excel
- Score de confiance affiché en couleur dans la fenêtre de validation (vert/orange/rouge)

### Corrigé
- **BUG-A** : regex `num_facture` — 4 niveaux de fallback avec séparateur `_SEP` permissif pour les artefacts OCR
- **BUG-B** : dates de session exclues de la détection de `date_facture`
- **BUG-C** : support des séparateurs de milliers dans les montants (`1.234,56` → `1234,56`)
- **BUG-D** : filtre `_TAUROENTUM_ADDR` empêche de confondre l'adresse de l'émetteur avec le client
- **BUG-E** : aperçu PDF avec gestion d'erreur silencieuse et log
- Double injection supprimée : `_on_validate` ne fait plus l'injection, `process_with_ui` s'en charge
- Tkinter exécuté uniquement dans le thread principal via `queue.Queue`
- Backup Excel (`.xlsx.bak`) avant chaque écriture
- Rotation automatique du log JSON (`MAX_ENTREES_LOG`)
- Encoding UTF-8 forcé sur les logs fichier
- `except Exception: pass` remplacés par `logging.warning(...)` sur les `shutil.move` de secours
- `full_text +=` dans les boucles remplacé par `parts.append()` + `"\n".join(parts)`

### Amélioré
- Extraction texte natif PyMuPDF en priorité, OCR Tesseract uniquement en fallback
- Notifications Windows avec fallback log si `win10toast` indisponible
- Détection client multi-niveaux : JSON → regex SOCIETE → bloc adresse postal

---

## [4.0.0] - 2026-03-04

### Ajouté
- Gestion des PDF multi-factures (découpage page par page)
- Interface de validation Tkinter avec aperçu PDF
- Détection automatique CPF / B2B / CDC
- Anti-doublon avant injection Excel
- CI GitHub Actions (lint + tests)

### Corrigé
- Suppression des chemins hardcodés
- Gestion des erreurs d'accès fichier Excel

---

## [1.0.0] - 2026-03-03

### Ajouté
- Version initiale : surveillance dossier Watchdog + OCR Tesseract + injection openpyxl
