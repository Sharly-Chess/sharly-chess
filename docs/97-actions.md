**[Retour au sommaire de la documentation](../README.md)**

# Sharly Chess - Actions

Cette page propose un synopsis des actions des onglets Tournois, Joueur·euses et Appariements.

## Définition du statut des rondes

| Ronde                              | Définition                                                                                                                            |
|------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| Ronde courante (ou ronde en cours) | La dernière ronde avec des appariements.                                                                                              |
| Ronde précédente                   | La ronde qui précéde immédiatement la ronde en cours (N-1).                                                                           |
| Rondes passées                     | Les rondes qui précédent la ronde précédente (N-2, N-3, ...).                                                                         |
| Ronde suivante                     | La ronde qui suit immédiatement la ronde en cours (N+1).                                                                              |
| Rondes futures                     | Les rondes qui suivent la ronde suivante (N+2, N+3, ...).                                                                             |
| Dernière ronde publiée             | La dernière ronde publiée est la dernière ronde pour laquelle l'arbitre principal·e a passé le statut de « brouillon » à « publiée ». |

> [!NOTE]
>
> **Ronde courante** : la définition jusque-là de la ronde courante était : la première ronde avec des joueur·euses non apparié·es ou des appariements sans résultat.
> Avec cette définition, la ronde en cours changeait lorsque des appariements étaient défaits sur une ronde précédente, ce qui était complètement contre-intuitif.
>
> **Dernière ronde publiée** : Cette notion n'existe pas encore et sera implémentée lorsque le stockage Access sera abandonné.
> Dans la version actuelle, toutes les rondes avec appariements sont considérées comme publiées (le statut de brouillon n'existe pas).
>
> Les notions du tableau ci-dessous sont relatives au tournoi. La notion de ronde affichée ou sélectionnée est relative à l'interface web, c'est la ronde active sur l'onglet Appariements.

## Modification des Tournois

A compléter (certaines modifications des tournois ne devraient pas être autorisées après le démarrage d'un tournoi).

## Modification des Joueur·euses (Elo, tiitre FIDE ou nom)

> [!NOTE]
> Les modifications des informations des joueur·euses ne portant pas sur le Elo, le titre FIDE ou le nom n'ont pas d'impact sur les appariements et les classements.

> [!NOTE]
> Papi recalcule les numéros d’appariement à chaque ronde (contrairement aux règlements FIDE).
> Dans un certain délai après la publication des résultats de la ronde N (ou avant publication des résultats), le changement prend effet pour le classement de la ronde N, et les appariements de la ronde N+1.
> Après la publication de la ronde N+1, les classements sont changés à partir de la ronde N+2.

| Moment                                          |   Autorisée FIDE   | Enregistrement | Recalcul<br/>numéros<br/>appariement |    Modification<br/>classement     |
|-------------------------------------------------|:------------------:|:--------------:|:-------------------------------------:|:----------------------------------:|
| Avant publication appariements ronde 1          | :white_check_mark: | :white_circle: |                ronde 1                |                                    |
| Avant fin délai publication résultats ronde 1   | :white_check_mark: |   :pushpin:    |                ronde 2                |              ronde 1               |
| Après publication appariements ronde 2          | :white_check_mark: |   :pushpin:    |                ronde 3                |              ronde 3               |
| Avant fin délai publication résultats ronde 2   | :white_check_mark: |   :pushpin:    |                ronde 3                |              ronde 2               |
| Après publication appariements ronde 3          | :white_check_mark: |   :pushpin:    |                ronde 4                |              ronde 4               |
| Avant fin délai publication résultats ronde 3   | :white_check_mark: |   :pushpin:    |                ronde 4                |                                    |
| À partir de la publication appariements ronde 4 | :white_check_mark: |   :pushpin:    |                  non                  | ronde N+1 ou N+2<br/>selon les cas |

> [!NOTE]
> Les modifications des informations des joueur·euses ne portant pas sur le Elo, le titre FIDE ou le nom n'ont pas d'impact sur les appariements et les classements.
>
> Respect des règlements de la FIDE :
> - :white_check_mark: Action autorisée par la FIDE
>
> Enregistrement des actions non standard :
> - :white_circle: Aucun enregistrement
> - :pushpin: Enregistrement dans la base de données

> [!NOTE]
>
> Sammy doit confirmer auprès de la DNA que le classement peut être modifié à n'importe quel moment car cela peut influer sur les départages.

## Modification des appariements et résultats

> [!NOTE]
> Un résultat ou une couleur erronée à la ronde N peut être signalée (règlement FIDE) :
> - Dans un certain délai après la publication des résultats de la ronde N
>   - Le classement de la ronde N et l’appariement de la ronde N+1 utilisent cette correction
> - Après la publication des appariements de la ronde N+1, mais avant la fin de la ronde N+1
>   - Les appariements de la ronde N+2 utilisent cette correction (probablement aussi le classement de la ronde N+1)
> - Après la fin de la ronde N+1
>   - Le résultat n’est utilisé que pour l’export FIDE, ni pour le classement final ni pour les appariements suivants.

### Description des actions

| Action / Ronde                 |                    Passée                     |                    Précédente                     |                   Courante                   |        Première<br/>non<br/>appariée         |                    Future                     |
|--------------------------------|:---------------------------------------------:|:-------------------------------------------------:|:--------------------------------------------:|:--------------------------------------------:|:---------------------------------------------:|
| Appariement total              | :no_entry_sign: :white_circle: :white_circle: |   :no_entry_sign: :white_circle: :white_circle:   | :white_circle: :white_circle: :white_circle: |      :white_check_mark: :ok: :pushpin:       | :no_entry_sign: :white_circle: :white_circle: |
| Appariement complémentaire     | :no_entry_sign: :white_circle: :white_circle: |   :no_entry_sign: :white_circle: :white_circle:   | :white_check_mark: :grey_question: :pushpin: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Appariement manuel             |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    | :white_check_mark: :grey_question: :pushpin: |     :no_entry_sign: :warning: :pushpin:      | :no_entry_sign: :white_circle: :white_circle: |
| Désappariement complet         | :no_entry_sign: :white_circle: :white_circle: |   :no_entry_sign: :white_circle: :white_circle:   |  :no_entry_sign: :grey_question: :pushpin:   | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Désappariement manuel          |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    | :white_check_mark: :grey_question: :pushpin: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Permutation                    |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    | :white_check_mark: :grey_question: :pushpin: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Modification d’un résultat     |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    |    :white_check_mark: :ok: :white_circle:    | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Modification des byes/forfaits |      :no_entry_sign: :warning: :pushpin:      | :ballot_box_with_check: :grey_question: :pushpin: | :ballot_box_with_check: :ok: :white_circle:  | :ballot_box_with_check: :ok: :white_circle:  |  :ballot_box_with_check: :ok: :white_circle:  |

> [!NOTE]
> Respect des règlements de la FIDE :
> - :white_circle: _Action non pertinente_
> - :no_entry_sign: Action non autorisée par la FIDE
> - :white_check_mark: Action autorisée par la FIDE
> - :ballot_box_with_check: Action autorisée par la FIDE, doit être autorisée par le règlement
>
> Messages d'alerte aux arbitres :
> - :white_circle: _Action non proposée_
> - :ok: Action sans message d'alerte
> - :grey_question: Modal : L'action que vous souhaitez réaliser n’est pas « standard », continuer ?
> - :warning: Modal : L'action que vous souhaitez réaliser n’est pas n’est pas autorisée par la FIDE, continuer ?
>
> Enregistrement des actions non standard :
> - :white_circle: Aucun enregistrement
> - :pushpin: Enregistrement dans la base de données
