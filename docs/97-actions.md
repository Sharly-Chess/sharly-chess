**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Actions

Cette page sur la branche ``doc-actions`` propose un synopsis des actions des 'onglets Tournois, Joueur·euses et Appariements.

## Définition du statut des rondes

| Ronde                                | Définition                                                                                                                            |
|--------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| Ronde en cours                       | La dernière ronde avec des appariements.                                                                                              |
| Ronde précédente                     | La ronde qui précéde immédiatement la ronde en cours (N-1).                                                                           |
| Rondes passées                       | Les rondes qui précédent la ronde précédente (N-2, N-3, ...).                                                                         |
| Ronde suivante                       | La ronde qui suit immédiatement la ronde en cours (N+1).                                                                              |
| Rondes futures                       | Les rondes qui suivent la ronde suivante (N+2, N+3, ...).                                                                             |
| Dernière ronde publiée               | La dernière ronde publiée est la dernière ronde pour laquelle l'arbitre principal·e a passé le statut de « brouillon » à « publiée ». |

> [!NOTE]
>
> > **Ronde en cours** : la définition jusque-là de la ronde en cours était : la première ronde avec des joueur·euses non apparié·es ou des appariements sans résultat.
> C'est exactement ce qui est implémenté par ``Tournament.current_round()``.
> Avec cette définition, la ronde en cours changeait lors des appariements sont défaits sur une ronde précédente, ce qui était complètement contre-intuitif.
>
> **Dernière ronde publiée** : Cette notion n'existe pas encore et sera implémentée lorsque le stockage Access sera abandonné.
> Dans la version actuelle, toutes les rondes avec appariements sont considérées comme publiées (le statut de brouillon n'existe pas).
>
> Les notions du tableau ci-dessous sont relatives au tournoi. la notion de ronde affichée (ou sélectionnée, ou courante) est relative à l'interface web, c'est la ronde active l'onglet Appariements.

## Légende

|       Icône        | Respect des règlements de la FIDE |
|:------------------:|-----------------------------------|
|   :white_circle:   | _Action non pertinente_           |
|  :no_entry_sign:   | Action non autorisée par la FIDE  |
| :white_check_mark: | Action autorisée par la FIDE      |

### Messages d'alerte aux arbitres

|      Icône      | Messages d'alerte aux arbitres                                                                      |
|:---------------:|-----------------------------------------------------------------------------------------------------|
| :white_circle:  | _Action non proposée_                                                                               |
|      :ok:       | Action sans message d'alerte                                                                        |
| :grey_question: | Modal : L'action que vous souhaitez réaliser n’est pas « standard », continuer ?                    |
|  :exclamation:  | Modal : L'action que vous souhaitez réaliser n’est pas n’est pas autorisée par la FIDE, continuer ? |

### Enregistrement des actions non standard

|           Icône            | Enregistrement<br/>(si confirmation du modal par l'utilisateur)                             |
|:--------------------------:|---------------------------------------------------------------------------------------------|
|       :white_circle:       | Aucun modal                                                                                 |
| :one:, :two:, :three:, ... | Enregistrement dans la base de données                                                      |

## Modification des Tournois

A compléter (certaines modifications des tournois ne devraient pas être autorisées après le démarrage d'un tournoi).

## Modification des Joueur·euses

> [!NOTE]
>
> Papi recalcule les numéros d’appariement à chaque ronde (contrairement aux règlements FIDE).
>
> Dans un certain délai après la publication des résultats de la ronde N (ou avant publication des résultats), le changement prend effet pour le classement de la ronde N, et les appariements de la ronde N+1.
>
> Après la publication de la ronde N+1, les classements sont changés à partir de la ronde N+2

| Moment                                          | Modification           | Autorisée FIDE | Enregistrement | Recalcul<br/>>numéros<br/>appariement |    Modification<br/>classement     |
|-------------------------------------------------|------------------------|:--------------:|:--------------:|:-------------------------------------:|:----------------------------------:|
| Avant publication appariements ronde 1          | Elo, titre FIDE ou nom |      :white_check_mark:      | :white_circle: |                ronde 1                |                                    |
| Avant fin délai publication résultats ronde 1   | Elo, titre FIDE ou nom |      :white_check_mark:      | :orange_book:  |                ronde 2                |              ronde 1               |
| Après publication appariements ronde 2          | Elo, titre FIDE ou nom |      :white_check_mark:      | :orange_book:  |                ronde 3                |              ronde 3               |
| Avant fin délai publication résultats ronde 2   | Elo, titre FIDE ou nom |      :white_check_mark:      | :orange_book:  |                ronde 3                |              ronde 2               |
| Après publication appariements ronde 3          | Elo, titre FIDE ou nom |      :white_check_mark:      | :orange_book:  |                ronde 4                |              ronde 4               |
| Avant fin délai publication résultats ronde 3   | Elo, titre FIDE ou nom |      :white_check_mark:      | :orange_book:  |                ronde 4                |                                    |
| À partir de la publication appariements ronde 4 | Elo, titre FIDE ou nom |      :white_check_mark:      | :orange_book:  |                  non                  | ronde N+1 ou N+2<br/>selon les cas |
| N'importe quand                                 | Autres                 |      :white_check_mark:      | :white_circle: |                                       |           Sans influence           |

> [!NOTE]
>
> Sammy doit confirmer auprès de la DNA que le classement peut être modifié à n'importe quel moment car cela peut influer sur les départages.

## Modification des appariements et résultats

> [!NOTE] (règlement FIDE)
>
> Un résultat ou une couleur erronée à la ronde N peut être signalée :
> - Dans un certain délai après la publication des résultats de la ronde N
>   - Le classement de la ronde N et l’appariement de la ronde N+1 utilisent cette correction
> - Après la publication des appariements de la ronde N+1, mais avant la fin de la ronde N+1
>   - Les appariements de la ronde N+2 utilisent cette correction (probablement aussi le classement de la ronde N+1)
> - Après la fin de la ronde N+1
>   - Le résultat n’est utilisé que pour l’export FIDE, ni pour le classement final ni pour les appariements suivants.

### Description des actions

| Ronde                     | Action                         | Autorisée FIDE  |      Modal      | Enregistrement | Remarque                                                             |
|---------------------------|--------------------------------|:---------------:|:---------------:|:--------------:|----------------------------------------------------------------------|
| ~~Passée~~                | ~~Appariement total~~          | :white_circle:  | :white_circle:  | :white_circle: | Aucun·e joueur·euse non apparié·e                                    |
| ~~Passée~~                | ~~Appariement complémentaire~~ | :white_circle:  | :white_circle:  | :white_circle: | Aucun·e joueur·euse non apparié·e                                    |
| ~~Passée~~                | ~~Appariement manuel~~         | :white_circle:  | :white_circle:  | :white_circle: | Aucun·e joueur·euse non apparié·e                                    |
| Passée                    | Désappariement complet         | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Passée                    | Désappariement manuel          | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Passée                    | Permutation                    | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Passée                    | Modification d’un résultat     | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Passée                    | Modification des byes/forfaits | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Appariement total              | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Précédente                | Appariement complémentaire     | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Précédente                | Appariement manuel             | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Désappariement complet         | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Précédente                | Désappariement manuel          | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Permutation                    | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Modification d’un résultat     | :no_entry_sign: | :grey_question: | :orange_book:  |                                                                      |
| Précédente                | Modification des byes/forfaits | :no_entry_sign: |   :question:    | :orange_book:  |                                                                      |
| ~~En cours~~              | ~~Appariement total~~          | :white_circle:  | :white_circle:  | :white_circle: |                                                                      |
| En cours                  | Appariement complémentaire     |      :ok:       | :white_circle:  | :white_circle: |                                                                      |
| En cours                  | Appariement manuel             |      :ok:       | :grey_question: | :orange_book:  |                                                                      |
| En cours                  | Désappariement complet         |      :ok:       | :grey_question: | :orange_book:  | Action dangereuse qui peut faire perdre des données => super warning |
| En cours                  | Désappariement manuel          |      :ok:       | :grey_question: | :orange_book:  |                                                                      |
| En cours                  | Permutation                    |      :ok:       | :grey_question: | :orange_book:  |                                                                      |
| En cours                  | Modification d’un résultat     |      :ok:       | :white_circle:  | :white_circle: |                                                                      |
| En cours                  | Modification des byes/forfaits |      :ok:       | :white_circle:  | :white_circle: | Si autorisé par le règlement.                                        |
| Première non appariée     | Appariement total              |      :ok:       | :white_circle:  | :white_circle: |                                                                      |
| ~~Première non appariée~~ | ~~Appariement complémentaire~~ | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| Première non appariée     | Appariement manuel             |      :ok:       |   :question:    | :closed_book:  |                                                                      |
| ~~Première non appariée~~ | ~~Désappariement complet~~     | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| ~~Première non appariée~~ | ~~Désappariement manuel~~      | :white_circle:  |                 | :white_circle: | Aucun appariement.                                                   |
| ~~Première non appariée~~ | ~~Permutation~~                | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| ~~Première non appariée~~ | ~~Modification d’un résultat~~ | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| Première non appariée     | Modification des byes/forfaits |      :ok:       | :white_circle:  | :white_circle: | Si autorisé par le règlement.                                        |
| Future                    | Appariement total              | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Future                    | Appariement complémentaire     | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Future                    | Appariement manuel             | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| ~~Future~~                | ~~Désappariement complet~~     | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| ~~Future~~                | ~~Désappariement manuel~~      | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| ~~Future~~                | ~~Permutation~~                | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| ~~Future~~                | ~~Modification d’un résultat~~ | :white_circle:  | :white_circle:  | :white_circle: | Aucun appariement.                                                   |
| Future                    | Modification des byes/forfaits |      :ok:       | :white_circle:  | :white_circle: | Si autorisé par le règlement.                                        |

| Action / Ronde                 |                    Passée                     |                    Précédente                    |                     En cours                     |        Première<br/>non<br/>appariée         |                    Future                     |
|--------------------------------|:---------------------------------------------:|:------------------------------------------------:|:------------------------------------------------:|:--------------------------------------------:|:---------------------------------------------:|
| Appariement total              | :no_entry_sign: :white_circle: :white_circle: |  :no_entry_sign: :white_circle: :white_circle:   |   :white_circle: :white_circle: :white_circle:   |    :white_check_mark: :ok: :white_circle:    | :no_entry_sign: :white_circle: :white_circle: |
| Appariement complémentaire     | :no_entry_sign: :white_circle: :white_circle: |  :no_entry_sign: :white_circle: :white_circle:   | :white_check_mark: :grey_question: :orange_book: |   :no_entry_sign: :warning: :closed_book:    | :no_entry_sign: :white_circle: :white_circle: |
| Appariement manuel             |    :no_entry_sign: :warning: :closed_book:    | :white_check_mark: :white_circle: :white_circle: | :white_check_mark: :grey_question: :orange_book: |   :no_entry_sign: :warning: :closed_book:    | :no_entry_sign: :white_circle: :white_circle: |
| Désappariement complet         | :no_entry_sign: :white_circle: :white_circle: |  :no_entry_sign: :white_circle: :white_circle:   | :white_check_mark: :grey_question: :orange_book: | :white_circle: :white_circle: :white_circle: | :no_entry_sign: :white_circle: :white_circle: |
| Désappariement manuel          |    :no_entry_sign: :warning: :closed_book:    |    :white_check_mark: :warning: :closed_book:    | :white_check_mark: :grey_question: :orange_book: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Permutation                    |    :no_entry_sign: :warning: :closed_book:    |    :white_check_mark: :warning: :closed_book:    | :white_check_mark: :grey_question: :orange_book: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Modification d’un résultat     |    :no_entry_sign: :warning: :closed_book:    | :white_check_mark: :grey_question: :orange_book: |      :white_check_mark: :ok: :white_circle:      | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Modification des byes/forfaits |    :no_entry_sign: :warning: :closed_book:    | :white_check_mark: :grey_question: :orange_book: |      :white_check_mark: :ok: :white_circle:      |    :white_check_mark: :ok: :white_circle:    |    :white_check_mark: :ok: :white_circle:     |
