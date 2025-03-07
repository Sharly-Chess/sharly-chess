**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Roadmap

## Roadmap macroscopique

| Version |   Date    | Fonctionnalités                                                                                                                                                                                                                      |
|:-------:|:---------:|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|   1.x   | 2013-2023 | Version initiale                                                                                                                                                                                                                     |
|   2.0   | Nov 2023  | Amélioration des écrans d'affichage                                                                                                                                                                                                  |
|   2.1   | Déc 2023  | Connexion à chessEvent                                                                                                                                                                                                               |
|   2.2   | Mar 2024  | Amélioration des performances, coups illégaux                                                                                                                                                                                        |
|   2.3   | Avr 2024  | Pointage                                                                                                                                                                                                                             |
|   2.4   | Oct 2024  | Logiciel libre<br/>Support multilingue<br/>Configuration web<br/>Stockage SQLite                                                                                                                                                     |
|   2.5   | Mar 2025  | Amélioration de l'interface<br/>Gestion des joueur·euses<br/>Calcul, affichage et impression des classements                                                                                                                         |
|   2.6   |   2025    | **Iso-fonctionnalité avec Papi 3.3.8**<br/>Appariements suisse, toutes rondes et manuel, brouillon/publié<br/>Calcul des prix<br/>Calcul des normes et certificats<br/>Statistiques, performances FIDE, import/export TRF, chevalets |
|   3.0   |  2025 ?   | **Ajout des fonctionnalités non supportées par papi**<br/>Abandon du format Access<br/>Résultats, départages                                                                                                                         |

## Roadmap détaillée

- LAN = usage en réseau local (sur un serveur local)
- SaaS = usage en ligne (sur un serveur distant)

|                                     | 1.19<br>jan 23  | 2.0<br/>nov 23  | 2.1<br/>déc 23  | 2.2<br/>mar 24  | 2.3<br/>avr 24  | 2.4<br/>oct 24  | 2.5<br/>mar 25  |    2.6<br/>-    |    3.0<br/>-    |
|-------------------------------------|:---------------:|:---------------:|:---------------:|:---------------:|:---------------:|:---------------:|:---------------:|:---------------:|:---------------:|
| **LAN**                             |    **1.19**     |     **2.0**     |     **2.1**     |     **2.2**     |     **2.3**     |     **2.4**     |     **2.5**     |     **2.6**     |     **3.0**     |
| Open source                         |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Logiciel libre                      |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |    :ok: AGPL    |    :ok: AGPL    |    :ok: AGPL    |    :ok: AGPL    |
| Serveur web inclus                  |    :x: XAMPP    |   :ok: Django   |   :ok: Django   |  :ok: LiteStar  |  :ok: Litestar  |  :ok: Litestar  |  :ok: Litestar  |  :ok: Litestar  |  :ok: Litestar  |
| Pilote BDD inclus                   |    :x: ODBC     |    :x: ODBC     |    :x: ODBC     |    :x: ODBC     |    :x: ODBC     |    :x: ODBC     |    :x: ODBC     |    :x: ODBC     |   :ok: SQLite   |
| Support Windows                     |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Exécutable Windows                  |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Signature de l'exécutable Windows   |        -        |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       | :grey_question: | :grey_question: |
| Support Linux                       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |
| Support Mac                         |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |
| Config. Papi-web                    |     :x: PHP     |    :ok: INI     |    :ok: INI     |    :ok: INI     |    :ok: INI     |    :ok: INI     |    :ok: INI     |    :ok: INI     | :ok: INI/SQLite |
| Config. évènements                  |     :x: PHP     |     :x: INI     |     :x: INI     |     :x: INI     |     :x: INI     |    :ok: web     |    :ok: web     |    :ok: web     |    :ok: web     |
| Stockage tournois                   |   :x: Access    |   :x: Access    |   :x: Access    |   :x: Access    |   :x: Access    |   :x: Access    |   :x: Access    |   :x: Access    |   :ok: SQLite   |
| Stockage évènements                 |        -        |    :x: File     |    :x: File     |    :x: File     |    :x: File     |   :ok: SQLite   |   :ok: SQLite   |   :ok: SQLite   |   :ok: SQLite   |
| **SAAS**                            |    **1.19**     |     **2.0**     |     **2.1**     |     **2.2**     |     **2.3**     |     **2.4**     |     **2.5**     |     **2.6**     |     **3.0**     |
| Disponibilité                       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       | :grey_question: |
| Open source                         |        -        |        -        |        -        |        -        |        -        |        -        |        -        |        -        | :grey_question: |
| Logiciel libre                      |        -        |        -        |        -        |        -        |        -        |        -        |        -        |        -        | :grey_question: |
| Stockage                            |        -        |        -        |        -        |        -        |        -        |        -        |        -        |        -        | :grey_question: |
| **APPARIEMENTS**                    |    **1.19**     |     **2.0**     |     **2.1**     |     **2.2**     |     **2.3**     |     **2.4**     |     **2.5**     |     **2.6**     |     **3.0**     |
| Appariement suisse                  | :ok: Papi 3.3.6 | :ok: Papi 3.3.6 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.8 | :ok: Papi 3.3.8 | :ok: bbp 5.0.1  | :ok: bbp 5.0.1  |
| Conformité Fide Handbook C.04       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |   :ok: PW 2.5   |   :ok: PW 2.6   |   :ok: PW 3.0   |
| Appariement toutes rondes           | :ok: Papi 3.3.6 | :ok: Papi 3.3.6 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.8 | :ok: Papi 3.3.8 |   :ok: PW 2.6   |   :ok: PW 3.0   |
| Appariements manuels                | :ok: Papi 3.3.6 | :ok: Papi 3.3.6 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.8 | :ok: Papi 3.3.8 |   :ok: PW 2.6   |   :ok: PW 3.0   |
| Statut brouillon/publié             |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |
| Import/export TRF16                 |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |
| Import/export TRF25                 |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |
| **CLASSEMENTS**                     |    **1.19**     |     **2.0**     |     **2.1**     |     **2.2**     |     **2.3**     |     **2.4**     |     **2.5**     |     **2.6**     |     **3.0**     |
| Calcul des classements              | :ok: Papi 3.3.6 | :ok: Papi 3.3.6 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 | :ok: Papi 3.3.8 |   :ok: PW 2.5   |   :ok: PW 2.6   |   :ok: PW 3.0   |
| Conformité FIDE parties non jouées  | :ok: Papi 3.3.6 | :ok: Papi 3.3.6 | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 |       :x:       |       :x:       |   :ok: PW 2.5   |   :ok: PW 2.6   |   :ok: PW 3.0   |
| Conformité FIDE performances        |       :x:       |       :x:       | :ok: Papi 3.3.7 | :ok: Papi 3.3.7 |       :x:       |       :x:       |       :x:       |   :ok: PW 2.6   |   :ok: PW 3.0   |
| **INTERNATIONALISATION**            |    **1.19**     |     **2.0**     |     **2.1**     |     **2.2**     |     **2.3**     |     **2.4**     |     **2.5**     |     **2.6**     |     **3.0**     |
| FR                                  |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Multilingual support                |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |   :ok: 2.4.19   |      :ok:       |      :ok:       |      :ok:       |
| EN                                  |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |   :ok: 2.4.19   |      :ok:       |      :ok:       |      :ok:       |
| **HOMOLOGATION FIDE**               |    **1.19**     |     **2.0**     |     **2.1**     |     **2.2**     |     **2.3**     |     **2.4**     |     **2.5**     |     **2.6**     |     **3.0**     |
|                                     |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       | :grey_question: |      :ok:       |
| **UTILISATION**                     |    **1.19**     |     **2.0**     |     **2.1**     |     **2.2**     |     **2.3**     |     **2.4**     |     **2.5**     |     **2.6**     |     **3.0**     |
| HTMX                                |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Multi-écrans                        |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Multi-colonnes                      |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Appariements alphabétiques          |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Écrans rotatifs                     |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Enregistrement Coups illégaux       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Pointage                            |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Modification des résultats          |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| FFE - Envoi tournois                |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| FFE - Protection données            |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| ChessEvent - Téléchargement données |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |      :ok:       |
| Gestion des joueur·euses            |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |
| Impression des appariements         |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |
| Impression des classements          |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |
| Impression des grilles américaines  |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |      :ok:       |
| Performances FIDE                   |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |
| Calcul des prix                     |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |
| Calcul des normes joueur·euses      |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |
| Chevalets                           |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |      :ok:       |      :ok:       |
| Tombola                             |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       | :grey_question: | :grey_question: |
| Certificats normes arbitrage        |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       | :grey_question: |
| compétitions par équipe             |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       |       :x:       | :grey_question: |

