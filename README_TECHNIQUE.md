# Guide Technique Simplifié : Comment fonctionne le système sous le capot ?

Ce document explique le fonctionnement technique du workflow automatisé de factures. Il est rédigé de manière simple pour qu'une personne non-informaticienne puisse comprendre *"comment la magie opère"*.

## L'Architecture Générale (Les Pièces du Puzzle)

Le système est désormais compilé sous la forme d'un **exécutable autonome (`WorkflowFactures.exe`)** pour Windows. Sous le capot, il contient des scripts Python qui agissent comme des employés virtuels spécialisés :

1. **Le Veilleur (`main_watcher.py`)** : C'est le chef d'orchestre. Il surveille le dossier "Entrant" sans jamais s'arrêter. Dès qu'un fichier PDF est posé, il réveille les autres.
2. **Le Lecteur (L'OCR)** : C'est la brique qui lit le PDF. Elle transforme l'image de la facture en un long texte brut compréhensible par l'ordinateur.
3. **L'Analyseur (L'Intelligence)** : Il lit le texte brut et joue au "Cherche et Trouve" pour isoler les dates, les montants, le numéro de facture, etc.
4. **L'Interface de Validation (`validation_ui.py`)** : Une fenêtre intégrée au programme, qui se lance uniquement si l'analyseur a eu du mal à lire le document.
5. **L'Écrivain** : C'est la brique chargée de remplir le fichier Excel de destination.

---

## Le Cycle de Vie d'une Facture (Étape par Étape)

Voici la séquence exacte qui s'exécute en une fraction de seconde lorsqu'un PDF arrive dans le dossier :

### Étape 1 : La Détection
Le script Python utilise une librairie appelée `watchdog` (le "chien de garde"). Elle est directement connectée à Windows et est alertée instantanément quand un fichier est copié. Cela consomme très peu d'énergie (pas besoin de vérifier le dossier manuellement toutes les secondes).

### Étape 2 : Le Nettoyage de l'Image (Pré-traitement)
Si c'est un scan papier, l'image peut être grise, floue ou un peu de travers. Le code utilise la technologie `Pillow` (une librairie de traitement d'image) pour :
- Transformer l'image en Noir & Blanc pur (pour faire ressortir le texte).
- Augmenter artificiellement la netteté (le contraste).

### Étape 3 : L'Extraction du Texte (OCR)
Le code transmet cette belle image nettoyée à `Tesseract OCR` (un moteur Open Source créé par Google). Tesseract "lit" l'image et renvoie tout le texte trouvé, mot pour mot.

### Étape 4 : L'Analyse Intelligente (Les Regex)
Comment le robot sait-il quel nombre est le montant et quel nombre est le code postal ?
Le système utilise des **Expressions Régulières (Regex)**. Ce sont des "règles de recherche" ultra-précises.
*Exemple de logique pour le montant : "Cherche les mots 'Total TTC' ou 'Net à payer', et prend les chiffres qui suivent juste après. Si ces mots n'existent pas, liste tous les montants de la page et sélectionne automatiquement le plus élevé".*

### Étape 5 : Le Système de Confiance (Le Score)
Le bot est prudent. Il démarre avec une note de 10/10. 
S'il ne trouve pas le numéro de facture, il se retire des points (-3). S'il ne trouve pas de date (-2). 
- **Si la note tombe en dessous de 7/10** : Le script se met en pause et affiche une interface visuelle pour demander de l'aide à l'humain.
- **Si la note est bonne** : Il passe à l'étape suivante en toute autonomie.

### Étape 6 : L'Écriture dans Excel
Le système utilise une librairie appelée `openpyxl`. Contrairement à vous qui devez ouvrir Excel, attendre qu'il charge, cliquer sur la cellule, etc... l'ordinateur lit et modifie le code source du fichier `.xlsx` directement à la vitesse de l'éclair, de manière silencieuse. 
*Important : avant d'écrire, le système vérifie strictement (même après une validation manuelle de l'humain) qu'il n'inscrit pas un doublon ! S'il détecte un numéro de facture existant, il s'arrête instantanément.*

### Étape 7 : Le Compte-Rendu (Traces et Notifications)
Le script utilise le module Windows natif (`win10toast`) pour faire popper la petite cloche de notification en bas à droite de votre écran. 
En même temps, il écrit un rapport dans le journal de bord `workflow.json`, pour que les administrateurs informatiques puissent comprendre exactement ce qu'il a fait.

---

## Résumé des Technologies Clés

- **Langage de base :** Python 3 (Compilé via `PyInstaller`)
- **Surveillance dossier :** `watchdog`
- **Traitement PDF & Image :** `PyMuPDF (fitz)` + `Pillow (PIL)`
- **Moteur de lecture OCR :** `Tesseract` via `pytesseract`
- **Recherche de mots :** Natif Python (`re` pour Regex)
- **Manipulation Excel :** `openpyxl`
- **Interface visuelle :** `tkinter` (Natif Python)
- **Notifications :** `win10toast`

**Tout ce processus tourne 100% en local sur votre machine.** Aucune de vos factures n'est envoyée sur les serveurs de Google ou sur le Cloud, garantissant une sécurité et une confidentialité maximales de vos données financières et clients.
