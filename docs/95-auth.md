**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Rôles et autorisations

## Rôles en version 2.4

Dans la version actuelle (2.4), Papi-web distingue deux rôles :
- **le rôle arbitre**, qui s'obtient en se connectant depuis le serveur 127.0.0.1), qui peut accéder :
  - aux pages d'administration, ou pages d'arbitrage ;
  - aux pages publiques, avec quelques privilèges supplémentaires.
- **le rôle standard**, qui permet :
  - de visualiser les écrans publics ;
  - de pointer et saisir les résultats (avec ou sans protection par mot de passe).

## Proposition d'évolution

### Rôles

- **Administration** (de l'application)
- **Organisation** (d'un évènement)
- **Arbitrage en chef·fe** (d'un évènement ou d'un tournoi)
- **Arbitrage** (d'un évènement ou d'un tournoi)
- **Pointage** (d'un évènement)
- **Saisie** (d'un évènement)
- **Visualisation** (d'un évènement)

### Actions autorisées par rôle

|                                                  | Administration  | Organisation  | Arbitrage en chef |  Arbitrage  |   Pointage    |    Saisie     | Visualisation |
|--------------------------------------------------|:---------------:|:-------------:|:-----------------:|:-----------:|:-------------:|:-------------:|:-------------:|
| **Périmètre**                                    | **Application** | **Évènement** |    **Tournoi**    | **Tournoi** | **Évènement** | **Évènement** | **Évènement** |
| **GESTION DE L'APPLICATION**                     |                 |               |                   |             |               |               |               |
| Paramétrage de l'application                     |      :ok:       |      :x:      |        :x:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Gestion des administrateur·ices                  |      :ok:       |      :x:      |        :x:        |     :x:     |      :x:      |      :x:      |      :x:      |
| **GESTION DES ÉVÈNEMENTS**                       |                 |               |                   |             |               |               |               |
| Ajout d'un évènement                             |      :ok:       |      :x:      |        :x:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Suppression d'un évènement                       |      :ok:       |      :x:      |        :x:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Renommage d'un évènement                         |      :ok:       |      :x:      |        :x:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Édition d'un évènement                           |      :ok:       |     :ok:      |        :x:        |     :x:     |      :x:      |      :x:      |      :x:      |
| **GESTION DES TOURNOIS**                         |                 |               |                   |             |               |               |               |
| Ajout d'un tournoi                               |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Suppression d'un tournoi                         |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Édition d'un tournoi                             |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Ouverture/fermeture du pointage                  |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Moteur d'appariement                             |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Appariement manuel                               |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Publication des appariements                     |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Visualisation des appariements avant publication |       :x:       |      :x:      |       :ok:        |    :ok:     |      :x:      |      :x:      |      :x:      |
| Calcul des classements                           |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Publication des classements                      |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Visualisation des classements avant publication  |       :x:       |      :x:      |       :ok:        |    :ok:     |      :x:      |      :x:      |      :x:      |
| Publication en ligne                             |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| **GESTION DE L'AFFICHAGE**                       |                 |               |                   |             |               |               |               |
| Gestion des écrans/familles/écrans rotatifs      |       :x:       |     :ok:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Gestion des chronomètres                         |       :x:       |     :ok:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| **GESTION DES JOUEUR·EUSES**                     |                 |               |                   |             |               |               |               |
| Ajout d'un·e joueur·euse                         |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Suppression d'un·e joueur·euse                   |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Édition 'un·e joueur·euse                        |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Pointage                                         |       :x:       |      :x:      |       :ok:        |    :ok:     |     :ok:      |      :x:      |      :x:      |
| **GESTION DES PARTIES**                          |                 |               |                   |             |               |               |               |
| Utilisation des scores spéciaux                  |       :x:       |      :x:      |       :ok:        |     :x:     |      :x:      |      :x:      |      :x:      |
| Rectification des scores                         |       :x:       |      :x:      |       :ok:        |    :ok:     |      :x:      |      :x:      |      :x:      |
| Saisie des scores                                |       :x:       |      :x:      |       :ok:        |    :ok:     |      :x:      |     :ok:      |      :x:      |
| **VISUALISATION**                                |                 |               |                   |             |               |               |               |
| Pointage                                         |      :ok:       |     :ok:      |       :ok:        |    :ok:     |     :ok:      |     :ok:      |     :ok:      |
| Appariements                                     |      :ok:       |     :ok:      |       :ok:        |    :ok:     |     :ok:      |     :ok:      |     :ok:      |
| Résultats                                        |      :ok:       |     :ok:      |       :ok:        |    :ok:     |     :ok:      |     :ok:      |     :ok:      |

### Attribution des rôles

L'octroi d'un rôle se fait :
- par client (l'adresse IP de la machine qui accède au serveur Papi-web) ;
- par authentification (un identifiant et un mot de passe) ;
- par client et par authentification.

### Exemple d'attribution des rôles

Dans l'exemple ci-dessous :
- les connexions depuis le serveur ont tous les rôles, de manière automatique (non configurable) ;
- les connexions depuis le client ``192.168.1.115`` et authentifiées avec l'identifiant ``big-boss`` ont un rôle d'organisation et d'arbitrage en chef pour tous les tournois ;
- les connexions authentifiées avec les identifiants ``boss-1`` et ``boss-2`` ont un rôle d'arbitrage, respectivement pour les tournois A/B et C/D ;
- les deux derniers postes permettent respectivement le pointage et la saisie des résultats ;
- les autres clients non authentifiés peuvent visualiser les écrans d'affichage.

|      Client       |       ID       |    Commentaire    | Tournoi | Administration | Organisation | Arbitrage en chef | Arbitrage | Pointage | Saisie | Visualisation |
|:-----------------:|:--------------:|:-----------------:|:-------:|:--------------:|:------------:|:-----------------:|:---------:|:--------:|:------:|:-------------:|
|   ``127.0.0.1``   |       -        |      Serveur      |    -    |      :ok:      |     :ok:     |       :ok:        |   :ok:    |   :ok:   |  :ok:  |     :ok:      |
| ``192.168.1.115`` |  ``big-boss``  | Arbitre principal |         |      :x:       |     :ok:     |       :ok:        |   :ok:    |   :ok:   |  :ok:  |     :ok:      |
|         -         |   ``boss-1``   |  Arbitre adjoint  |  A, B   |      :x:       |     :x:      |        :x:        |   :ok:    |   :ok:   |  :ok:  |     :ok:      |
|         -         |   ``boss-2``   |  Arbitre adjoint  |  C, D   |      :x:       |     :x:      |        :x:        |   :ok:    |   :ok:   |  :ok:  |     :ok:      |
| ``192.168.1.27``  |       -        |  Poste pointage   |         |      :x:       |     :x:      |        :x:        |    :x:    |   :ok:   |  :x:   |     :ok:      |
| ``192.168.1.226`` |       -        |  Poste de saisie  |         |      :x:       |     :x:      |        :x:        |    :x:    |   :x:    |  :ok:  |     :ok:      |
|         -         |       -        |                   |         |      :x:       |     :x:      |        :x:        |    :x:    |   :x:    |  :x:   |     :ok:      |







