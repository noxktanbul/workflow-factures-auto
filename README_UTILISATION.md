# Guide d'Utilisation Pratique : Traitement Automatique des Factures

Ce guide vous explique comment utiliser le système d'automatisation des factures au quotidien. Il a été conçu pour être le plus simple possible : **le système travaille pour vous en arrière-plan.**

## 1. Comment traiter une facture ?

0. **Démarrez le programme** : Double-cliquez sur `WorkflowFactures.exe` (situé dans le dossier `Z:\NZBG\workflow factures\`). Le logiciel tournera alors silencieusement en tâche de fond.
1. **Recevez votre facture** (par email, ou scannez une facture papier).
2. **Glissez-déposez** le fichier PDF de la facture dans le dossier suivant :
   👉 `...\workflow_factures\Entrant`
   *(Astuce : créez un raccourci de ce dossier sur votre Bureau !)*
3. **C'est tout !** Le système détecte automatiquement le nouveau fichier dans les 2 à 3 secondes.

## 2. Que se passe-t-il ensuite ?

Le système va lire la facture tout seul (via une intelligence artificielle de reconnaissance de texte) pour extraire :
- Le Numéro de la facture
- Le Nom du Client
- Les Dates (émission et échéance)
- Le Montant

### Scénario A : La facture est parfaitement lisible (Cas le plus fréquent)
Si le système est très sûr de ce qu'il a lu, il va **directement ajouter une nouvelle ligne dans votre fichier Excel** des échéances.
- Vous verrez passer une **notification Windows** (en bas à droite de l'écran) pour vous confirmer le succès de l'opération.
- Le fichier PDF est automatiquement déplacé du dossier `Entrant` vers le dossier `Traite`.

### Scénario B : La facture est floue ou complexe (Validation requise)
Si le système a un doute (par exemple, s'il n'arrive pas à lire le montant ou une date), il préfère ne pas se tromper.
- Une **notification Windows** vous avertit qu'une validation est requise.
- Une **fenêtre s'ouvre sur votre écran**.
- À gauche de cette fenêtre, vous verrez l'image de la facture.
- À droite, vous verrez les informations que le système a trouvées. Les cases **rouges** indiquent ce qui manque.
- **Votre action :** Corrigez ou complétez les informations manquantes au clavier, puis cliquez sur le bouton vert **"Valider & Injecter"**.

### Scénario C : Le système détecte un doublon
Si vous glissez une facture dont le numéro (ex: TAU_2026-559) a **déjà été rentré** dans votre tableau Excel :
- Le système bloque tout pour éviter d'avoir deux fois la même facture dans votre tableau.
- Même si le système passe par la fenêtre de Validation Visuelle et que vous choisissez de cliquer sur "Valider", il appliquera son garde-fou et bloquera l'injection.
- La fenêtre de validation se fermera d'elle-même instantanément.
- Vous recevez une alerte Windows indiquant qu'il s'agit d'un doublon.
- Le fichier PDF est placé dans le dossier `Erreur` (pour que vous puissiez vérifier pourquoi il a été envoyé deux fois).

## 3. L'Échéancier Excel

- Le fichier Excel cible (celui qui est mis à jour) se trouve ici : `...\References\Echeancier_cible.xlsx`.
- **Vous n'avez pas besoin de le fermer** pour que le système fonctionne, mais il est préférable de ne pas être en train de modifier la cellule exacte où le système essaie d'écrire.

## 4. Où sont mes fichiers PDF ?
Pour garder le dossier `Entrant` propre, le système range les fichiers une fois qu'il a terminé :
- **Succès** : Le PDF est rangé dans le dossier `Traite`.
- **Doublon ou Erreur** : Le PDF est rangé dans le dossier `Erreur`. Vous pouvez toujours le récupérer.

## 5. Historique
Besoin de savoir ce qui s'est passé ? Un fichier `workflow.json` (ainsi qu'un fichier texte `workflow.log`) situé dans le dossier principal garde une trace écrite de tout ce que le système a fait, à la seconde près.
