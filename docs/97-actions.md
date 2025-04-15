**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Actions

Cette page sur la branche ``doc-actions`` propose un synopsis des actions des 'onglets Tournois, Joueur·euses et Appariements.

## Définitions

### Respect des règlements de la FIDE

| Action autorisée FIDE | Explication                      |
|:---------------------:|----------------------------------|
|    :no_entry_sign:    | Action non autorisée par la FIDE |
|         :ok:          | Action autorisée par la FIDE     |

### Statut des rondes

| Ronde                 | Explication                                                                                                                                                                                                  |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Passée                | En cours – 2, en cours - 3, ...                                                                                                                                                                              |
| Précédente            | En cours - 1                                                                                                                                                                                                 |
| En cours              | La première ronde avec des joueur·euses non apparié·es ou des appariements sans résultat (en général la dernière ronde appariée sauf dans le cas où des appariements sont défaits surt uen ronde précédente) |
| Première non appariée | En cours + 1                                                                                                                                                                                                 |
| Future                | En cours + 2, en cours + 3, ...                                                                                                                                                                              |

### Messages d'alerte aux arbitres et enregistrement des actions non standard

|      Modal      | Explication                                                                                 | Enregistrement<br/>(si confirmation) |
|:---------------:|---------------------------------------------------------------------------------------------|:------------------------------------:|
|        -        | Aucun modal                                                                                 |            :white_circle:            |
| :grey_question: | L'action que vous souhaitez réaliser n’est pas « standard », continuer ?                    |            :orange_book:             |
|   :question:    | L'action que vous souhaitez réaliser n’est pas n’est pas autorisée par la FIDE, continuer ? |            :closed_book:             |
|       :x:       | L'action que vous souhaitez réaliser n’est pas est impossible                               |            :white_circle:            |

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

| Moment                                          | Modification           | Autorisée FIDE | Enregistrement | Recalcul<br/>>numéros<br/>appariement |      Modification<br/>classement      |
|-------------------------------------------------|------------------------|:--------------:|:--------------:|:-------------------------------------:|:-------------------------------------:|
| Avant publication appariements ronde 1          | Elo, titre FIDE ou nom |      :ok:      | :white_circle: |                ronde 1                |                                       |
| Avant fin délai publication résultats ronde 1   | Elo, titre FIDE ou nom |      :ok:      | :orange_book:  |                ronde 2                |                ronde 1                |
| Après publication appariements ronde 2          | Elo, titre FIDE ou nom |      :ok:      | :orange_book:  |                ronde 3                |                ronde 3                |
| Avant fin délai publication résultats ronde 2   | Elo, titre FIDE ou nom |      :ok:      | :orange_book:  |                ronde 3                |                ronde 2                |
| Après publication appariements ronde 3          | Elo, titre FIDE ou nom |      :ok:      | :orange_book:  |                ronde 4                |                ronde 4                |
| Avant fin délai publication résultats ronde 3   | Elo, titre FIDE ou nom |      :ok:      | :orange_book:  |                ronde 4                |                                       |
| À partir de la publication appariements ronde 4 | Elo, titre FIDE ou nom |      :ok:      | :orange_book:  |                  non                  |  ronde N+1 ou N+2<br/>>selon les cas  |
| N'importe quand                                 | Autres                 |      :ok:      | :white_circle: |                                       |            Sans influence             |

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
| Passée                    | Désappariement manuel          | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Passée                    | Permutation                    | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Passée                    | Modification d’un résultat     | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Passée                    | Modification des byes/forfaits | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Précédente                | Appariement total              | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Précédente                | Appariement complémentaire     | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Précédente                | Appariement manuel             | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Désappariement complet         | :no_entry_sign: |       :x:       | :white_circle: |                                                                      |
| Précédente                | Désappariement manuel          | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Permutation                    | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Modification d’un résultat     | :no_entry_sign: | :grey_question: | :orange_book:  |                                                                      |
| Précédente                | Modification des byes/forfaits | :no_entry_sign: |   :question:    | :closed_book:  | Si autorisé par le règlement., vraiment un warning ?                 |
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

| Action / Ronde                 |                    Passée                    |                  Précédente                   |                   En cours                   |        Première<br/>non<br/>appariée         |                    Future                    |
|--------------------------------|:--------------------------------------------:|:---------------------------------------------:|:--------------------------------------------:|:--------------------------------------------:|:--------------------------------------------:|
| Appariement total              | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  | :white_circle: :white_circle: :white_circle: |      :ok: :white_circle: :white_circle:      |      :no_entry_sign: :x: :white_circle:      |
| Appariement complémentaire     | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |      :ok: :white_circle: :white_circle:      | :white_circle: :white_circle: :white_circle: |      :no_entry_sign: :x: :white_circle:      |
| Appariement manuel             | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |      :ok: :grey_question: :orange_book:      |        :ok: :question: :closed_book:         |      :no_entry_sign: :x: :white_circle:      |
| Désappariement complet         |      :no_entry_sign: :x: :white_circle:      |      :no_entry_sign: :x: :white_circle:       |      :ok: :grey_question: :orange_book:      | :white_circle: :white_circle: :white_circle: |      :no_entry_sign: :x: :white_circle:      |
| Désappariement manuel          |      :no_entry_sign: :x: :white_circle:      |   :no_entry_sign: :question: :closed_book:    |      :ok: :grey_question: :orange_book:      | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle: |
| Permutation                    |      :no_entry_sign: :x: :white_circle:      |   :no_entry_sign: :question: :closed_book:    |      :ok: :grey_question: :orange_book:      | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle: |
| Modification d’un résultat     |      :no_entry_sign: :x: :white_circle:      | :no_entry_sign: :grey_question: :orange_book: |      :ok: :white_circle: :white_circle:      | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle: |
| Modification des byes/forfaits |      :no_entry_sign: :x: :white_circle:      |   :no_entry_sign: :question: :closed_book:    |      :ok: :white_circle: :white_circle:      |      :ok: :white_circle: :white_circle:      |      :ok: :white_circle: :white_circle:      |
