# French
English version below

## Fonctionnement

- Suppression du script ``ffe.bat`` (2.7.0)
- Ajout de la tombola (2.7.0)
- Correction d'un bug sur les familles d'écran sans joueur·euse (2.7.1)
- Suppression d'un avertissement au lancement du programme (2.7.2)

## Interface web

- Optimisation du temps de chargement de la page des évènements (2.7.0)
- Ajout de notifications instantanées dans les onglets Joueur·euses et Appariements lors de nouveaux pointages ou résultats (2.7.0)
- Interdiction de l'accès aux pages d'arbitrage pour les clients non autorisés (2.7.1)
- Amélioration de la gestion des exceptions (2.7.6)

### Gestion des évènements

- Correction d'un bug sur l'édition des évènements (2.7.6)

### Gestion des tournois

- Ajout des exports PGN et TRF 16 (2.7.0)

### Gestion des joueur·euses

- Correction et ajout de champs dans l'export des joueur·euses au format ODS (2.7.1)
- Correction de l'affichage des joueur·euses non-FIDE lors de la mise à jour depuis les bases de données FIDE et FFE (2.7.3)
- Correction de la mise à jour des classements des joueur·euses (2.7.5)
- Correction des couleurs du modal de mise à jour des joueur·euses (2.7.5)

### Gestion des appariements

- Diminution des temps de réaction lors de la saisie des résultats (2.7.1)
- Correction de l'entrée de résultats au clavier sur des échiquiers fixes (2.7.5)
- Suppression du modal de configuration de l'appariement lorsque non opportun (2.7.5)

### Gestion des écrans

- Correction d'un bug à la création des écrans (2.7.2)

## FFE

- Intégration des opérations sur le site FFE sur l'interface web (2.7.0)
- Alignement du calcul de performance avec celui de Papi en cas de joueur·euses avec demi-point joker (2.7.0)
- Correction d'un bug de mise en ligne des résultats (2.7.3)
- Correction du test des identifiants FFE lors de l'édition des tournois (2.7.4)
- Utilisation de la base de données du serveur fédéral lors de la création des joueur·euses à partir de la base FIDE (2.7.5)

## ChessEvent

- Prise en compte correcte des dates de naissance antérieures au 01/01/1970 (2.7.0)
- Normalisation des noms des joueur·euses (2.7.1)
- Correction du type de classement Estimé/National des joueur·euses (2.7.4)

---

# English

## Usage

- Removal of script ``ffe.bat`` (2.7.0)
- Added the lottery (2.7.0)
- Fixed a bug caused by screen families with zero items (2.7.1)
- Removed a warning at server startup (2.7.2)

## Web interface

- Optimized the load time of the events page (2.7.0)
- Instant notifications on Players and Pairings tabs for new checkins or results from user screens (2.7.0)
- Forbid access to arbiters' pages for unauthorized clients (2.7.1)
- Improved exception handling (2.7.6)

### Event management

- Fixed a bug on event editing (2.7.6)

### Tournaments management

- Added PGN and TRF 16 exports (2.7.0)

### Players management

- Fixed and added columns to the players ODS export (2.7.1)
- Fixed the display of non-FIDE players when updating the players from FFE or FIDE databases (2.7.3)
- Update players when rating types differ in data sources (2.7.5)
- Fixed the colors of the players update modal (2.7.5)

### Pairings management

- Reduced reaction time when entering results (2.7.1)
- Fixed entering results with keyboard shortcuts on fixed boards (2.7.5)
- Removed pairing settings modal when not accurate (2.7.5)

### Screens management

- Fixed a bug on screen creation (2.7.2)

## FFE

- Integration of the FFE operations to the web UI (2.7.0)
- Alignment of performance calculation with Papi’s in the case of players with a full-point or half-point bye (2.7.0)
- Fixed a bug on FFE results upload (2.7.3)
- Fixed FFE auth test on the tournament editing form (2.7.4)
- Request the FFE SQL server when augmenting players created from the FIDE database (2.7.5)

## ChessEvent

- Fixed birth dates prior to 1970-01-01 (2.7.0)
- Normalized players' names (2.7.1)
- Fixed the players' Estimated/National rating type (2.7.4)
