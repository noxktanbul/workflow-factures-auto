# Changelog

Toutes les modifications notables de ce projet sont documentées ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [Unreleased]

---

## [4.3.0] - 2026-03-06

### Corrigé
- **BUG-MONTANT-PERSIST** : regex `_AMOUNT` réécrite pour capturer les montants avec point décimal sans séparateur de milliers (`260.00`, `465.00`) — l'ancien pattern `(?:[\s.]\d{3})*` exigeait 3 chiffres après le point et ratait tous ces cas
- **BUG-NUM-PERSIST** : Tier 0 utilise désormais une fenêtre de contexte (±200 chars) pour trouver les dates autour du numéro, même si elles sont sur des lignes séparées (layout tableau HTML extrait colonne par colonne par PyMuPDF)
- **BUG-NUM-FAUX-POSITIF** : Tier 4 valide que l'année capturée est dans la plage 2020–2040 — empêche `Numéro de commande : MC30031699` d'être interprété comme `TAU_0031-699`
- **BUG-SESSION-CONFUSION** : la détection de session exige que les deux dates soient différentes — empêche `25-02-2026 au 25-02-2026` (date facture = date échéance dans le tableau) d'être capturé comme session et de bloquer la date facture

### Ajouté
- 7 nouveaux tests unitaires couvrant les montants à point décimal, la session à dates identiques et le filtre année Tier 4

---

## [4.2.0] - 2026-03-06

### Corrigé
- **BUG-NUM** : Ajout d'un Tier 0 avec regex littérale `TAU_\d{4}-\d{3,}` — résout l'échec d'extraction sur les PDFs natifs (tableaux HTML) où `TAU_2026-557` n'était pas capturé par les tiers permissifs
- **BUG-DATE** : Restructuration du bloc de fallback dates — les dates sont maintenant cherchées même quand Tier 0 a trouvé le numéro mais pas les dates
- **BUG-AMOUNT-ZERO** : Priorité des mots-clés montant réordonnée : `Total TTC` / `Net à payer` → `Restant dû` (non nul) → `Montant` → fallback `€` ; évite de capturer un sous-montant nul (encaissement)
- **BUG-CLIENT-CPF** : `clients_connus.json` — `CAISSE DES DEPOTS` retourne désormais `"CAISSE DES DEPOTS"` comme client (au lieu de `"CPF"`) ; le type CPF reste correctement détecté par `detect_type`

### Ajouté
- 10 nouveaux tests unitaires couvrant Tier 0, la priorité des montants et la séparation client/type CPF

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
