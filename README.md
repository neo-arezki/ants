# ANTs v0.5.0

ANTs est un compagnon financier personnel local. Les données restent dans :

`C:\Users\VOTRE_NOM\Documents\ANTs\ants.db`

## Installation / mise à jour

1. Fermez ANTs.
2. Décompressez le dossier où vous voulez.
3. Double-cliquez sur `lancer_ants.bat`.

Au premier lancement, la base existante est sauvegardée dans `Documents\ANTs\backups`, puis migrée automatiquement vers la v0.5.0.

## Nouveautés principales

- les dépenses confirmées et prévisionnelles sont désormais séparées dans les projets ;
- affichage distinct de **Dépensé**, **Prévu**, **Engagement total** et **Reste prévisionnel** ;
- un projet peut recevoir une description générale et des notes ;
- chaque projet dispose d'un dossier détaillé regroupant les achats associés ;
- les commentaires saisis sur les écritures sont visibles dans ce dossier ;
- un double-clic sur un projet ouvre désormais son dossier ;
- les anciennes bases v0.4.0 sont migrées automatiquement sans perte de données.

## Exemple

Pour le projet « Études de droit » :

- CVEC confirmée : 178 € ;
- frais Assas prévisionnels : 500 € ;
- dépensé réellement : 178 € ;
- prévu : 500 € ;
- engagement total : 678 €.

## Important

Le fichier `ants.db` ne doit jamais être ajouté sur GitHub.
