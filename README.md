# Google Antigravity - Workflow Factures Auto

Bienvenue sur le dépôt du projet de **Workflow Automatisé de Traitement de Factures**. Ce projet utilise Python, Tesseract OCR et Regex pour lire, analyser et injecter intelligemment des factures PDF dans un fichier Excel partagé.

> **Mise à jour (V4)** : Le système gère désormais nativement les **PDF Multi-Factures** (1 page = 1 facture), ignorant automatiquement les pages de type "convocation" ou "devis". Il intègre aussi une détection intelligente du contexte (Client en position inversée par rapport au `TAU_`) et renseigne dynamiquement le champ "Type" (`B2B`, `CPF`, `CDC`) de l'échéancier. (A+ Grade Code Quality).

## Documentation

Ce dépôt contient deux guides détaillés pour mieux comprendre l'environnement :

1. 📖### 2. Guide Utilisateur (`README_UTILISATION.md`)
Destiné aux personnes qui vont utiliser l'application au quotidien. Il explique où déposer les fichiers, comment lire les notifications et comment réagir en cas d'erreur.
2. 🛠️ **[Guide Technique](README_TECHNIQUE.md)** : Comment le code fonctionne sous le capot (Watchdog, Regex de secours, Extraction, PyInstaller).

## Installation

1. Assurez-vous d'avoir Python 3.12+ installé.
2. Clonez ce dépôt localement.
3. Installez les dépendances: `pip install -r requirements.txt`.
4. Installez Tesseract OCR et Poppler (nécessaires pour l'extraction de texte et d'images PDF).

## Usage

Le système peut être exécuté de deux façons :
- **Mode développement :** Lancez `python main_watcher.py` pour démarrer la surveillance du dossier `Entrant/`.
- **Mode production :** Compilez le projet avec PyInstaller et lancez l'exécutable généré.

Déposez un fichier PDF dans le dossier `Entrant/`. S'il est reconnu, il sera traité automatiquement. S'il y a un doute, une interface utilisateur de validation s'ouvrira.

## API

Le projet n'expose pas d'API web publique. Les différentes briques (OCR, Regex, GUI) fonctionnent comme des modules importables en Python. Pour l'intégration, référez-vous au code de `main_watcher.py` (orchestrateur).

---
*Ce projet est une solution automatisée locale pour garantir la confidentialité des données.*

## Lancer le Projet

Un exécutable standalone pour machine Windows (`WorkflowFactures.exe`) est habituellement généré pour ne pas avoir à installer d'environnement Python complet chez l'utilisateur final.

**Dépendances de développement** :
- Python 3+
- Tesseract OCR (C:\Tesseract-OCR\)
- `pip install PyMuPDF Pillow pytesseract openpyxl watchdog win10toast`
