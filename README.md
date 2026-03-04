# Google Antigravity - Workflow Factures Auto

Bienvenue sur le dépôt du projet de **Workflow Automatisé de Traitement de Factures**. Ce projet utilise Python, Tesseract OCR et Regex pour lire, analyser et injecter intelligemment des factures PDF dans un fichier Excel partagé.

> **Note :** Ce projet a bénéficié d'un audit de qualité de code garantissant d'excellentes performances et de bonnes pratiques (A+ Grade).

## Documentation

Ce dépôt contient deux guides détaillés pour mieux comprendre l'environnement :

1. 📖 **[Guide d'Utilisation](README_UTILISATION.md)** : Comment utiliser le logiciel au quotidien, l'exécutable (`.exe`), et la gestion des cas pratiques (doublons, erreurs).
2. 🛠️ **[Guide Technique](README_TECHNIQUE.md)** : Comment le code fonctionne sous le capot (Watchdog, Regex de secours, Extraction, PyInstaller).

## Lancer le Projet

Un exécutable standalone pour machine Windows (`WorkflowFactures.exe`) est habituellement généré pour ne pas avoir à installer d'environnement Python complet chez l'utilisateur final.

**Dépendances de développement** :
- Python 3+
- Tesseract OCR (C:\Tesseract-OCR\)
- `pip install PyMuPDF Pillow pytesseract openpyxl watchdog win10toast`
