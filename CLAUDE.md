# Rapport de Passation : WorkflowFactures (V5.6)

Ce document est destiné à **Claude Code** pour une reprise immédiate du projet avec tout le contexte nécessaire.

## 🎯 Objectif du Projet
Automatiser l'extraction de données depuis des factures PDF (format TAU_) et les injecter dans un fichier Excel de suivi (`Echeancier_cible.xlsx`).

## 🏗️ Architecture Technique
- **Orchestration** : `main_watcher.py` (utilise `watchdog` pour surveiller le dossier `Entrant/`).
- **Moteur OCR** : `ocr_engine.py` (basé sur **EasyOCR**). Lecture robuste des tableaux et du texte gris.
- **Logique Métier** :
    - `client_dictionary.py` : Dictionnaire de noms de clients et logique de **Fuzzy Matching** (RapidFuzz — `fuzz.WRatio` via `rapidfuzz`).
    - `validation_ui.py` : Interface de validation (Tkinter) pour les cas ambigus.
- **Workflow de fichiers** :
    1. `Entrant/` ⮕ Scan OCR automatique.
    2. `Traite/` ⮕ Si extraction OK et injection Excel réussie.
    3. `Erreur/` ⮕ Si erreur critique ou aucune facture TAU_ détectée.

## 🛠️ Commandes Utiles
- **Exécuter en dev** : `python main_watcher.py`
- **Lancer les tests** : `python run_tests.py`
- **Compiler l'EXE** : `pyinstaller --noconfirm --clean main_watcher.spec`
  (le spec produit directement `WorkflowFactures.exe`)

## 📈 État Actuel (V5.8) — 18/03/2026
- **Stabilité** : `win10toast` désactivé. Thread Tkinter via `queue.Queue`. Double-enfilage watchdog corrigé (`threading.Lock` + `Set`).
- **Fiabilité données** :
    - Faux positifs fuzzy : bruit OCR (alpha_ratio < 60%) force l'UI même à score élevé.
    - Montants aberrants (< 10€) forcent l'UI — artefacts SIRET/numéros de page interceptés.
    - `Restant du` / `Encaissement` retirés des mots-clés montant et ajoutés aux FOOTER_PATTERNS (solde ≠ TTC).
    - `POLE TAUROENTUM` supprimé du dictionnaire clients (était l'émetteur, jamais un client).
    - Dates issues de l'UI Tkinter désormais correctement injectées dans Excel (conversion str → datetime.date).
    - **V5.8** : `montant_ttc is None` force l'UI même si score ≥ 7 (injection auto bloquée sans montant).
    - **V5.8** : Feuille Excel absente → `ERROR` immédiat avec log explicite (plus de `KeyError` silencieux).
    - **V5.8** : Détection doublons insensible à la casse (`.upper()`).
    - **V5.8** : Validation de types dans l'UI (`on_validate`) : montant float et dates JJ/MM/AAAA vérifiés avant soumission.
    - **V5.8** : Confirmation de rejet dans l'UI (bouton "Rejeter" → boîte askyesno).
- **UI** : L'aperçu image affiche la page de la facture concernée. `basicConfig` dans `validation_ui.py` conditionnel (évite double handler avec `RotatingFileHandler`).
- **Logs** : `RotatingFileHandler` sur `workflow.log` (5 MB × 3 fichiers). `basicConfig` de `validation_ui.py` ignoré si logger déjà configuré.
- **OCR** : DPI production = 200. `y_tolerance=25` dans `ocr_engine.py`.
- **Architecture** : `parse_invoice_text` source unique dans `main_watcher.py`.
- **Dossiers** : `_find_folder` dans `main_watcher.py` ET `validation_ui.py`.
- **Dernier déploiement** : `WorkflowFactures.exe` à recompiler (V5.8).

## 📝 Conventions & Points d'attention
- **Identifiant Facture** : Regex `TAU_\d{4}[-_]\d+`.
- **Fuzzy Matching** : Seuil auto-correction 0.65–1.0. Si bruit OCR détecté (`_client_noise=True`) → UI forcée.
- **Montant suspect** : `_montant_suspect=True` si < 10€ → UI forcée.
- **Montant absent** : `montant_ttc is None` → UI forcée (indépendamment du score).
- **Logs** : `workflow.log` (RotatingFileHandler, 5 MB × 3) + `workflow.json` (audit structuré). Surveiller `WARNING` pour les corrections suspectes.
- **Score confiance** : seuil UI = score < 7/10. Score 7 sans montant → UI forcée (V5.8, ancien comportement corrigé).
- **Feuille Excel** : nom `"Ventes_Factures"` obligatoire. Si absent → ERROR + log explicite.

---
*Document mis à jour le 18/03/2026 suite aux patches V5.8 (sécurisation injection) par Claude Code.*
