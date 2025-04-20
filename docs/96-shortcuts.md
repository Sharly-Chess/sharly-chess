**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Raccourcis clavier

Cette page est un document de travail sur les raccourcis clavier utilisables dans l'application, à destination des développeur·euses.

## Onglet Joueur·euses

### Raccourcis globaux

**Aucun raccourci clavier n'est implémenté sur la l'onglet Joueur·euses.**

| Raccourci Papi | Action                   | Proposition SC | Note                |
|----------------|--------------------------|----------------|---------------------|
| ``F3``         | Ajouter un·e joueur·euse | ``A``          | ~~Non implémentée~~ |
| ``F5``         | Créer un·e joueur·euse   | ``A``          | ~~Non implémentée~~ |

## Onglet Appariements

### Partie gauche (joueur·euses non apparié·es)

**Aucun raccourci clavier n'est implémenté pour la gestion des joueur·euses non apparié·es.**

Toutes les actions ne sont pas possibles en fonction de l'état du·de la joueur·euse.

| Raccourci Papi | Action                                   | Proposition SC | Note                                               |
|----------------|------------------------------------------|----------------|----------------------------------------------------|
| ``C``          | Copier                                   |                |                                                    |
| ``V``          | Coller                                   |                |                                                    |
| ``M``          | Modifier                                 |                |                                                    |
| ``Suppr``      | Suppression                              | ``Suppr``      | Confirmation                                       |
|                | Retour ronde en cours                    | ``R``          | Demande ronde en cours ou définitif                |
| ``R``          | Retour définitif                         | ``R``          | Demande ronde en cours ou définitif                |
|                | Forfait ronde en cours                   | ``F``          | Demande ronde en cours ou définitif                |
| ``F``          | Forfait définitif                        | ``F``          | Demande ronde en cours ou définitif                |
| ``4``          | Point joker                              |                | Menu contextuel                                    |
| ``6``          | Demi point joker                         |                | Menu contextuel                                    |
| ``0``          | Annuler joker                            |                | Menu contextuel                                    |
| ``=``          | Bye                                      | ``=``          | TA : besoin d'une raccourci ?                      |
| ``B``          | Apparier Blancs                          | ``B``          | TA : juste apparier, le premier B et le deuxième N |
| ``N``          | Apparier Noirs                           | ``N``          | TA : juste apparier, le premier B et le deuxième N |
| ``X``          | Apparier Exempt                          | ``X``          | Internationaliser ?                                |
| ``Down``       | Joueur·euse suivant·e                    | ``Down``       |                                                    |
| ``Up``         | Joueur·euse précédent·e                  | ``Up``         |                                                    |
|                | Premier·e joueur·euse                    | ``Home``       | TA : pas sur tous les claviers                     |
|                | Dernier·e joueur·euse                    | ``End``        | TA : pas sur tous les claviers                     |
|                | Passage sur la partie droite (échiquier) | ``Right``      |                                                    |

### Partie droite (échiquiers)

**Seuls les raccourcis en gras sont implémentés.**

| Raccourci Papi | Action                                      | Proposition SC | Note                           |
|----------------|---------------------------------------------|----------------|--------------------------------|
| ``0``          | **Pas de résultat**                         | ``0``          |                                |
| ``1``          | **Gain Blancs**                             | ``1``          |                                |
| ``2``          | **Gain Noirs**                              | ``2``          |                                |
| ``3``          | **Nulle**                                   | ``3``          |                                |
| ``P``          | Permuter                                    | ``P``          |                                |
| ``D``          | Désapparier                                 | ``D``          | Confirmation                   |
| ``4``          | Gain Blancs forfait                         |                | Action rare                    |
| ``5``          | Gain Noirs forfait                          |                | Action rare                    |
| ``7``          | Double forfait                              |                | Action rare                    |
| ``Down``       | Échiquier suivant                           | ``Down``       |                                |
| ``Up``         | Échiquier précédent                         | ``Up``         |                                |
|                | Premier échiquier                           | ``Home``       | TA : pas sur tous les claviers |
|                | Dernier échiquier                           | ``End``        | TA : pas sur tous les claviers |
|                | Passage sur la partie gauche (joueur·euses) | ``Left``       |                                |

### Raccourcis globaux

**Aucun raccourci clavier global n'est implémenté sur l'onglet Appariements.**

| Raccourci Papi | Action                   | Proposition SC      | Note                                              |
|----------------|--------------------------|---------------------|---------------------------------------------------|
| ``F3``         | Ajouter un·e joueur·euse | ``A``               |                                                   |
| ``F5``         | Créer un·e joueur·euse   | ``A``               | Browser refresh                                   |
|                | Ronde suivante           | ``PgDown``          |                                                   |
|                | Ronde précédent          | ``PgUp``            |                                                   |
|                | Première ronde           | ``Ctrl-PgUp``       | YA : faisabilité ? TA : pas sur tous les claviers |
|                | Dernière ronde           | ``Ctrl-PgDown``     | YA : faisabilité ? TA : pas sur tous les claviers |
|                | Tournoi suivant          | ``Ctrl-Alt-PgDown`` | YA : faisabilité ? TA : pas sur tous les claviers |
|                | Tournoi précédent        | ``Ctrl-Alt-PgUp``   | YA : faisabilité ? TA : pas sur tous les claviers |
|                | Défaire                  | ``Ctrl-Z``          | TA : pas aujourd'hui                              |
|                | Refaire                  | ``Ctrl-Y``          | TA : pas aujourd'hui                              |
