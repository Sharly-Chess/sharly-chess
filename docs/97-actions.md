**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Actions

Cette page sur la branche ``doc-actions`` propose un synopsis des actions des 'onglets Joueur·euses et Appariements.

## Onglet Joueur·euses

> [!NOTE]
>
> Papi recalcule les numéros d’appariement à chaque ronde (contrairement aux règlements FIDE).
>
> Dans un certain délai après la publication des résultats de la ronde N (ou avant publication des résultats), le changement prend effet pour le classement de la ronde N, et les appariements de la ronde N+1.
>
> Après la publication de la ronde N+1, les classements sont changés à partir de la ronde N+2

| Moment                                          | Action                                  | Enregistrement | Remarque                                                                                      |
|-------------------------------------------------|-----------------------------------------|:--------------:|-----------------------------------------------------------------------------------------------|
| Avant publication appariements ronde 1          | Modification du Elo, titre FIDE ou nom  |                |                                                                                               |
| Avant fin délai publication résultats ronde 1   | Modification du Elo, titre FIDE ou nom  | :orange_book:  | Numéro d’appariement recalculé ronde 2, classement ronde 1 modifié                            |
| Après publication appariements ronde 2          | Modification du Elo, titre FIDE ou nom  | :orange_book:  | Numéro d’appariement recalculé ronde 3, classement ronde 3 modifié                            |
| Avant fin délai publication résultats ronde 2   | Modification du Elo, titre FIDE ou nom  | :orange_book:  | Numéro d’appariement recalculé ronde 3, classement ronde 2 modifié                            |
| Après publication appariements ronde 3          | Modification du Elo, titre FIDE ou nom  | :orange_book:  | Numéro d’appariement recalculé ronde 4, classement ronde 4 modifié                            |
| Avant fin délai publication résultats ronde 3   | Modification du Elo, titre FIDE ou nom  | :orange_book:  | Numéro d’appariement recalculé ronde 4                                                        |
| À partir de la publication appariements ronde 4 | Modification du Elo, titre FIDE ou nom  | :orange_book:  | Pas de changement du numéro d’appariement, classement ronde N+1 ou N+2 modifiés selon les cas |
| N'importe quand                                 | Autres modifications                    | :orange_book:  |                                                                                               |

> [!NOTE]
>
> Sammy doit confirmer auprès de la DNA que le classement peut être modifié à n'importe quel moment car cela peut influer sur les départages.


## Onglet Appariements

> [!NOTE] (règlement FIDE)
>
> Un résultat ou une couleur erronée à la ronde N peut être signalée :
> - Dans un certain délai après la publication des résultats de la ronde N
>   - Le classement de la ronde N et l’appariement de la ronde N+1 utilisent cette correction
> - Après la publication des appariements de la ronde N+1, mais avant la fin de la ronde N+1
>   - Les appariements de la ronde N+2 utilisent cette correction (probablement aussi le classement de la ronde N+1)
> - Après la fin de la ronde N+1
>   - Le résultat n’est utilisé que pour l’export FIDE, ni pour le classement final ni pour les appariements suivants.

### Définition du statut des rondes

| Ronde                 | Explication                                                                                                                                                                                                  |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Passée                | En cours – 2, en cours - 3, ...                                                                                                                                                                              |
| Précédente            | En cours - 1                                                                                                                                                                                                 |
| En cours              | La première ronde avec des joueur·euses non apparié·es ou des appariements sans résultat (en général la dernière ronde appariée sauf dans le cas où des appariements sont défaits surt uen ronde précédente) |
| Première non appariée | En cours + 1                                                                                                                                                                                                 |
| Future                | En cours + 2, en cours + 3, ...                                                                                                                                                                              |

### Respect des règlements de la FIDE

|  Autorisée FIDE   | Explication                      |
|:-----------------:|----------------------------------|
|  :no_entry_sign:  | Action non autorisée par la FIDE |
|       :ok:        | Action autorisée par la FIDE     |

### Avertissements aux arbitres et enregistrement des opérations non standard

|      Modal      | Enregistrement | Explication                                                                                 |
|:---------------:|:--------------:|---------------------------------------------------------------------------------------------|
|        -        |                | Aucun modal                                                                                 |
| :grey_question: | :orange_book:  | L'action que vous souhaitez réaliser n’est pas « standard », continuer ?                    |
|   :question:    | :closed_book:  | L'action que vous souhaitez réaliser n’est pas n’est pas autorisée par la FIDE, continuer ? |
|       :x:       |                | L'action que vous souhaitez réaliser n’est pas est impossible                               |

### Description des actions

| Ronde sélectionnée        | Action                         | Autorisée FIDE  |      Modal      | Enregistrement | Remarque                                                             |
|---------------------------|--------------------------------|:---------------:|:---------------:|:--------------:|----------------------------------------------------------------------|
| ~~Passée~~                | ~~Appariement total~~          |                 |                 |                | Aucun·e joueur·euse non apparié·e                                    |
| ~~Passée~~                | ~~Appariement complémentaire~~ |                 |                 |                | Aucun·e joueur·euse non apparié·e                                    |
| ~~Passée~~                | ~~Appariement manuel~~         |                 |                 |                | Aucun·e joueur·euse non apparié·e                                    |
| Passée                    | Désappariement complet         | :no_entry_sign: |       :x:       |                |                                                                      |
| Passée                    | Désappariement manuel          | :no_entry_sign: |       :x:       |                |                                                                      |
| Passée                    | Permutation                    | :no_entry_sign: |       :x:       |                |                                                                      |
| Passée                    | Modification d’un résultat     | :no_entry_sign: |       :x:       |                |                                                                      |
| Passée                    | Modification des byes/forfaits | :no_entry_sign: |       :x:       |                |                                                                      |
| Précédente                | Appariement total              | :no_entry_sign: |       :x:       |                |                                                                      |
| Précédente                | Appariement complémentaire     | :no_entry_sign: |       :x:       |                |                                                                      |
| Précédente                | Appariement manuel             | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Désappariement complet         | :no_entry_sign: |       :x:       |                |                                                                      |
| Précédente                | Désappariement manuel          | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Permutation                    | :no_entry_sign: |   :question:    | :closed_book:  |                                                                      |
| Précédente                | Modification d’un résultat     | :no_entry_sign: | :grey_question: | :orange_book:  |                                                                      |
| Précédente                | Modification des byes/forfaits | :no_entry_sign: |   :question:    | :closed_book:  | Si autorisé par le règlement., vraiment un warning ?                 |
| ~~En cours~~              | ~~Appariement total~~          |                 |                 |                |                                                                      |
| En cours                  | Appariement complémentaire     |      :ok:       |        -        |                |                                                                      |
| En cours                  | Appariement manuel             |      :ok:       | :grey_question: | :orange_book:  |                                                                      |
| En cours                  | Désappariement complet         |      :ok:       | :grey_question: | :orange_book:  | Action dangereuse qui peut faire perdre des données => super warning |
| En cours                  | Désappariement manuel          |      :ok:       | :grey_question: | :orange_book:  |                                                                      |
| En cours                  | Permutation                    |      :ok:       | :grey_question: | :orange_book:  |                                                                      |
| En cours                  | Modification d’un résultat     |      :ok:       |        -        |                |                                                                      |
| En cours                  | Modification des byes/forfaits |      :ok:       |        -        |                | Si autorisé par le règlement.                                        |
| Première non appariée     | Appariement total              |      :ok:       |        -        |                |                                                                      |
| ~~Première non appariée~~ | ~~Appariement complémentaire~~ |                 |                 |                | Aucun appariement.                                                   |
| Première non appariée     | Appariement manuel             |      :ok:       |   :question:    | :closed_book:  |                                                                      |
| ~~Première non appariée~~ | ~~Désappariement complet~~     |                 |                 |                | Aucun appariement.                                                   |
| ~~Première non appariée~~ | ~~Désappariement manuel~~      |                 |                 |                | Aucun appariement.                                                   |
| ~~Première non appariée~~ | ~~Permutation~~                |                 |                 |                | Aucun appariement.                                                   |
| ~~Première non appariée~~ | ~~Modification d’un résultat~~ |                 |                 |                | Aucun appariement.                                                   |
| Première non appariée     | Modification des byes/forfaits |      :ok:       |        -        |                | Si autorisé par le règlement.                                        |
| Future                    | Appariement total              | :no_entry_sign: |       :x:       |                |                                                                      |
| Future                    | Appariement complémentaire     | :no_entry_sign: |       :x:       |                |                                                                      |
| Future                    | Appariement manuel             | :no_entry_sign: |       :x:       |                |                                                                      |
| ~~Future~~                | ~~Désappariement complet~~     |                 |                 |                | Aucun appariement.                                                   |
| ~~Future~~                | ~~Désappariement manuel~~      |                 |                 |                | Aucun appariement.                                                   |
| ~~Future~~                | ~~Permutation~~                |                 |                 |                | Aucun appariement.                                                   |
| ~~Future~~                | ~~Modification d’un résultat~~ |                 |                 |                | Aucun appariement.                                                   |
| Future                    | Modification des byes/forfaits |      :ok:       |        -        |                | Si autorisé par le règlement.                                        |

| Ronde sélectionnée        | Action                         |        Passée         |                  Précédente                   |              En cours              | Première<br/>non<br/>appariée |       Future        |
|---------------------------|--------------------------------|:---------------------:|:---------------------------------------------:|:----------------------------------:|:-----------------------------:|:-------------------:|
| ~~Passée~~                | ~~Appariement total~~          | :white_circle:        |                :white_circle:                 |           :white_circle:           |            :ok: -             | :no_entry_sign: :x: |
| ~~Passée~~                | ~~Appariement complémentaire~~ |    :white_circle:     |                :white_circle:                 |               :ok: -               |        :white_circle:         | :no_entry_sign: :x: |
| ~~Passée~~                | ~~Appariement manuel~~         |    :white_circle:     |                :white_circle:                 | :ok: :grey_question: :orange_book: | :ok: :question: :closed_book: | :no_entry_sign: :x: |
| Passée                    | Désappariement complet         |  :no_entry_sign: :x:  |              :no_entry_sign: :x:              | :ok: :grey_question: :orange_book: |        :white_circle:         | :no_entry_sign: :x: |
| Passée                    | Désappariement manuel          |  :no_entry_sign: :x:  |   :no_entry_sign: :question: :closed_book:    | :ok: :grey_question: :orange_book: |        :white_circle:         |   :white_circle:    |
| Passée                    | Permutation                    |  :no_entry_sign: :x:  |   :no_entry_sign: :question: :closed_book:    | :ok: :grey_question: :orange_book: |        :white_circle:         |   :white_circle:    |
| Passée                    | Modification d’un résultat     |  :no_entry_sign: :x:  | :no_entry_sign: :grey_question: :orange_book: |               :ok: -               |        :white_circle:         |   :white_circle:    |
| Passée                    | Modification des byes/forfaits |  :no_entry_sign: :x:  |   :no_entry_sign: :question: :closed_book:    |               :ok: -               |            :ok: -             |       :ok: -        |
