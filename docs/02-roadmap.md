**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Roadmap

- LAN = usage en réseau local (sur un serveur local)
- SaaS = usage en ligne (sur un serveur distant)

|                                     | 1.19<br>jan 23 | 2.0<br/>nov 23 | 2.1<br/>déc 23 | 2.2<br/>mar 24 | 2.3<br/>avr 24 | 2.4<br/>oct 24 |    2.x<br/>-    |    3.0<br/>-    |   Cible<br/>-   |
|-------------------------------------|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|:---------------:|:---------------:|:---------------:|
| **LAN**                             |    **1.19**    |    **2.0**     |    **2.1**     |    **2.2**     |    **2.3**     |    **2.4**     |     **2.x**     |     **3.0**     |    **Cible**    |
| Open source                         |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Logiciel libre                      |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |   :ok: AGPL    |    :ok: AGPL    |    :ok: AGPL    |    :ok: AGPL    |
| Serveur web inclus                  |   :x: XAMPP    |  :ok: Django   |  :ok: Django   | :ok: LiteStar  | :ok: Litestar  | :ok: Litestar  |  :ok: Litestar  |  :ok: Litestar  |  :ok: Litestar  |
| Pilote BDD inclus                   |    :x: ODBC    |    :x: ODBC    |    :x: ODBC    |    :x: ODBC    |    :x: ODBC    |    :x: ODBC    | :grey_question: |   :ok: SQLite   |   :ok: SQLite   |
| Support Windows                     |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Exécutable Windows                  |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Support Linux                       |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |       :x:       | :grey_question: |      :ok:       |
| Support Mac                         |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |       :x:       | :grey_question: |      :ok:       |
| Config. Papi-web                    |    :x: PHP     |    :ok: INI    |    :ok: INI    |    :ok: INI    |    :ok: INI    |    :ok: INI    |    :ok: INI     |    :ok: INI     |    :ok: INI     |
| Config. évènements                  |    :x: PHP     |    :x: INI     |    :x: INI     |    :x: INI     |    :x: INI     |    :ok: web    |    :ok: web     |    :ok: web     |    :ok: web     |
| Stockage tournois                   |   :x: Access   |   :x: Access   |   :x: Access   |   :x: Access   |   :x: Access   |   :x: Access   | :grey_question: |   :ok: SQLite   |   :ok: SQLite   |
| Stockage évènements                 |       -        |    :x: File    |    :x: File    |    :x: File    |    :x: File    |  :ok: SQLite   |   :ok: SQLite   |   :ok: SQLite   |   :ok: SQLite   |
| **SAAS**                            |    **1.19**    |    **2.0**     |    **2.1**     |    **2.2**     |    **2.3**     |    **2.4**     |     **2.x**     |     **3.0**     |    **Cible**    |
| Disponibilité                       |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |       :x:       | :grey_question: |      :ok:       |
| Open source                         |       -        |       -        |       -        |       -        |       -        |       -        |        -        | :grey_question: |      :ok:       |
| Logiciel libre                      |       -        |       -        |       -        |       -        |       -        |       -        |        -        | :grey_question: | :grey_question: |
| Stockage                            |       -        |       -        |       -        |       -        |       -        |       -        |        -        | :grey_question: |  :ok: Postgres  |
| **APPARIEMENTS**                    |    **1.19**    |    **2.0**     |    **2.1**     |    **2.2**     |    **2.3**     |    **2.4**     |     **2.x**     |     **3.0**     |    **Cible**    |
| Moteur                              |    :x: Papi    |    :x: Papi    |    :x: Papi    |    :x: Papi    |    :x: Papi    |    :x: Papi    | :grey_question: |    :ok: bbp     |    :ok: bbp     |
| Support Papi                        |     3.3.6      |     3.3.6      |     3.3.7      |     3.3.7      |     3.3.7      |     3.3.8      | :grey_question: |        -        |        -        |
| **INTERNATIONALISATION**            |    **1.19**    |    **2.0**     |    **2.1**     |    **2.2**     |    **2.3**     |    **2.4**     |     **2.x**     |     **3.0**     |    **Cible**    |
| FR                                  |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Multilingual support                |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |  :ok: 2.4.19   |      :ok:       |      :ok:       |      :ok:       |
| EN                                  |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |  :ok: 2.4.19   |      :ok:       |      :ok:       |      :ok:       |
| **HOMOLOGATION FIDE**               |    **1.19**    |    **2.0**     |    **2.1**     |    **2.2**     |    **2.3**     |    **2.4**     |     **2.x**     |     **3.0**     |    **Cible**    |
|                                     |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |       :x:       | :grey_question: |      :ok:       |
| **UTILISATION**                     |    **1.19**    |    **2.0**     |    **2.1**     |    **2.2**     |    **2.3**     |    **2.4**     |     **2.x**     |     **3.0**     |    **Cible**    |
| HTMX                                |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Multi-écrans                        |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Multi-colonnes                      |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Appariements alphabétiques          |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Écrans rotatifs                     |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Enregistrement Coups illégaux       |      :x:       |      :x:       |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Pointage                            |      :x:       |      :x:       |      :x:       |      :x:       |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| Modification des résultats          |      :x:       |      :x:       |      :x:       |      :x:       |      :x:       |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| FFE - Envoi tournois                |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| FFE - Protection données            |      :x:       |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
| ChessEvent - Téléchargement données |      :x:       |      :x:       |      :ok:      |      :ok:      |      :ok:      |      :ok:      |      :ok:       |      :ok:       |      :ok:       |
