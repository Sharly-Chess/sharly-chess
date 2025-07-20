# French
English version below

## Fonctionnement

- Ajout de paramètres de log et mise à jour dynamique de la configuration (2.8.0)
- Suppression de l'option ``--experimental`` et activation des fonctionnalités expérimentales depuis l'interface web (2.8.0)
- Récupération des bases de données des joueur·euses lors des mises à jour (2.8.0)

## Interface web

- Passage d'une barre de navigation horizontale à une barre latérale (2.8.0)
- Simplification de la page d'accueil et ajout d'un QR code pour faciliter la connexion des clients (2.8.0)
- Ajout de boutons « Créer et ajouter à nouveau » pour réduire nombre de clics lors de la création d'objets (2.8.0)
- Rechargement des ressources statiques après les mises à jour (2.8.1)

### Gestion des tournois

- Correction du formulaire d'édition des tournois (2.8.3)

### Gestion des joueur·euses

- Ajout du genre sur les impressions des joueur·euses (2.8.0)
- Ajout des listes de pointage (2.8.0)
- Mise à jour des drapeaux des fédérations (2.8.0)
- Calcul de la catégorie des joueur·euses relativement à la date du tournoi (2.8.0)
- Clarification des sources de données de joueur·euses (2.8.0)

### Gestion des appariements

- Support officiel du moteur interne d'appariement (_bbpPairings_) (2.8.0)
- Génération d'appariements complémentaires (2.8.0)
- Exécution des opérations non-sécurisées lors du passage en mode non-sécurisé (2.8.0)
- Correction de la navigation entre les rondes (2.8.1)

### Gestion des écrans

- Ajout de la possibilité de ne pas afficher les adversaires sur les écrans d'appariements par ordre alphabétique (2.8.0)
- Correction de la suppression des résultats (2.8.2)

### Gestion des prix

- Ajout de l'onglet Prix avec la définition et le calcul des prix (2.8.0)

### Impression de documents

- Nouveaux documents (2.8.0)
  - Pointage des joueur·euses
  - Indicateurs de performance pour la ronde
  - Liste des prix
  - Attribution des prix

## Exports

- Correction des titres FIDE des joueur·euses dans les exports PGN (2.8.3)

## FFE

- Correction du téléversement manuel des résultats (2.8.2)

---

# English

## Usage

- Added logging parameters and dynamically update the logging configuration (2.8.0)
- Removed the ``--experimental`` option and activate the experimental features from the web UI (2.8.0)
- Recover the players database files when upgrading (2.8.0)

## Web interface

- Switch from a top navbar to a side navbar (2.8.0)
- Simplified the home page and added a QR code to ease the connection of devices (2.8.0)
- 'Create and add another' buttons added to reduce click count when creating objects (2.8.0)
- Reload static resources after upgrading (2.8.1)

### Tournaments management

- Fixed tournament editing form (2.8.3)

### Players management

- Added the gender on the player views (2.8.0)
- Added check-in lists (2.8.0)
- Updated federation flags (2.8.0)
- Calculation of the players' category relative to the date of the tournament (2.8.0)
- Clarification of player data sources (2.8.0)

### Pairings management

- Official support for the internal pairing engine (_bbpPairings_) (2.8.0)
- Complementary pairings generation (2.8.0)
- Unsafe operations execution when switching to unsafe mode (2.8.0)
- Fixed navigation between rounds (2.8.1)

### Screens management

- Added the possibility not to show the opponents on pairings screens by alphabetical order (2.8.0)
- Fixed deletion of results (2.8.2)

### Prizes management

- Added the Prizes tab with the definition and calculation of prizes (2.8.0)

### Print documents

- New documents (2.8.0)
  - Player check-in list
  - Round performance indicators
  - Prize list
  - Prize assignment

## Exports

- Fixed PGN export players' title (2.8.3)

## FFE

- Fixed the manual results upload (2.8.2)
