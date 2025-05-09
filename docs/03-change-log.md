**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - ChangeLog

## Version 2.5.9 - 9 mai 2025
- Correction d'un bug sur les titres des joueur·euses importé·es depuis ChesssEvent

## Version 2.5.8 - 30 avril 2025
- Correction d'un bug sur les droits d'inscription (#481)

## Version 2.5.7 - 20 avril 2025
- Correction d'un bug sur les impressions

## Version 2.5.6 - 17 avril 2025
- Correction d'un bug d'affichage des écrans multi-colonnes (#416)

## Version 2.5.5 - 13 avril 2025
- Correction d'un bug d'affichage des écrans d'appariements (#401)
- Correction d'un bug à la suppression d'un résultat

## Version 2.5.4 - 12 avril 2025
- Correction d'un bug de filtrage des clubs et fédérations sur l'onglet Joueur·euses (#378)

## Version 2.5.3 - 11 avril 2025
- Récupération de la configuration de l'application à partir d'une version antérieure
- Modification de l'encodage des fichiers de log
- Correction d'un bug d'affichage des rondes sur les écrans d'appariements (#389)
- Correction d'un bug d'initialisation des joueur·euses depuis ChessEvent (#388)

## Version 2.5.2 - 8 avril 2025
- Correction d'un bug à la récupération des versions antérieures
- Correction d'un bug sur la connexion au Serveur SQL de la FFE
- Correction du script ``bin/ffe.bat``
- Correction de l'absence de traductions dans les scripts ``bin/ffe.bat`` et ``bin/chessevent.bat``

## Version 2.5.1 - 8 avril 2025
- Correction d'un bug au lancement de l'application

## Version 2.5.0 - 7 avril 2025
- Passage en multilingue anglais et français
- Refonte complète de l'interface web
- Ajout/suppression/modification des joueur·euses, changements de tournoi
- Import et mise à jour des joueur·euses depuis les bases de données de la FIDE et de la FFE
- Gestion des présences/absences et des points joker
- Gestion complète du pointage (ouverture, pointage, fermeture)
- Suppression de l'onglet « ChessEvent » (la configuration des connexions à ChessEvent se fait désormais au niveau des évènements et des tournois)
- Ajout d'une fédération sur les évènements
- Support de la méthode HEAD pour les afficheurs dynamiques
- Suppression du fichier ``papi_web.ini`` et configuration de l'application par l'interface web
- Calcul des départages et classement des joueur·euses
- Impression et affichage du classement et de la grille américaine
- Impression des appariements et résultats
- Réduction du temps de démarrage de l'application
- Ajout de la possibilité de modifier la taille des polices sur les écrans d'affichage
- Correction du calcul des points virtuels en Système Accéléré Dégressif
- Correction d'un bug de mise en ligne des tournois sur le site FFE
- Correction d'un bug sur la duplication des écrans, familles et tournois
- Correction d'un bug empêchant l'affichage et la modification des écrans lorsque le numéro du premier échiquier est supérieur au nombre d'échiquiers
- Amélioration des logs et archivage sur disque

## Version 2.4.18 - 23 décembre 2024
- Ajout des écrans par défaut à la création d'un tournoi
- Correction d'un bug dans la gestion des connexions à ChessEvent
- Amélioration de l'ergonomie des écrans d'arbitrage

## Version 2.4.17 - 15 décembre 2024
- Masquage de tous les champs de saisie des mots de passe
- Correction d'un bug dans l'affichage du statut des tournois

## Version 2.4.16 - 5 décembre 2024
- Ajout de bandeaux d'alerte pour faire passer rapidement de l'information sur les écrans publics

## Version 2.4.15 - 1er décembre 2024
- Correction d'un bug dans la gestion des erreurs
- Correction d'un bug dans la création des bases d'exemple

## Version 2.4.14 - 29 novembre 2024
- Correction d'un bug de saisie des images de fond des évènements

## Version 2.4.13 - 24 novembre 2024
- Ajout de l'envoi du règlement des tournois sur le site fédéral
- Correction d'un bug d'affichage des menus des écrans publics

## Version 2.4.12 - 22 novembre 2024
- Ajout du règlement des évènements et des tournois
- Facilitation de la transmission des fichiers de personnalisation pour intégration dans la distribution
- Correction d'un bug sur la duplication des familles

## Version 2.4.11 - 18 novembre 2024
- Correction d'un bug sur la saisie des résultats
- Ajout de la possibilité de récupérer la configuration d'une version antérieure

## Version 2.4.10 - 17 novembre 2024
- Correction d'un bug sur l'affichage des tournois privés à venir

## Version 2.4.9 - 17 novembre 2024
- Correction d'un bug sur le téléchargement des tournois sur le site fédéral

## Version 2.4.8 - 16 novembre 2024
- Ajout de la possibilité de ne pas utiliser d'image de fond
- Correction d'un bug sur l'affichage des drapeaux des fédérations sur les écrans de pointage des écrans rotatifs
- Correction d'un bug empêchant l'affichage des appariements par ordre alphabétique

## Version 2.4.7 - 15 novembre 2024
- Affichage des drapeaux des fédérations sur les écrans de pointage des arbitres
- Correction d'un bug sur la récupération des évènements des versions précédentes

## Version 2.4.6 - 14 novembre 2024
- Mise à jour (à la demande) de la dernière version stable lorsque disponible
- Affichage de la licence des joueur·euses sur les écrans de pointage des arbitres (#45)
- Correction d'un bug sur le téléchargement des tournois sur le site fédéral

## Version 2.4.5 - 12 novembre 2024
- Optimisation des accès aux bases Access (#48)
- Réduction du trafic client/serveur (#49)

## Version 2.4.4 - 11 novembre 2024
- Ajout d'une fenêtre modale pour le pointage des joueur·euses (#46)
- Ajout de la possibilité de cacher les boutons de sortie des écrans de saisie

## Version 2.4.3 - 6 novembre 2024
- Correction d'un bug sur la mise à jour des bases de données (#43)

## Version 2.4.2 - 4 novembre 2024
- Optimisation des temps de rafraîchissement des pages de saisie des résultats
- Ajout de la possibilité d'effacer ou rectifier un résultat mal rentré sur les pages de saisie (#29)
- Ajout d'un paramètre pour les écrans de résultats pour limiter l'âge des résultats affichés (#27)

## Version 2.4.1 - 3 novembre 2024
- Correction d'un bug sur l'affichage des écrans rotatifs (#41)

## Version 2.4.0 - 30 octobre 2024
- Abandon du format INI, déclaration de tous les objets par l'interface web (#37)
- Ajout de la création automatique de tournois d'exemple
- Fluidification de la navigation (HTMX) (#31)
- Masquage de toutes les URLs de l'application
- Ajout de la possibilité (configurable) de supprimer un résultat mal rentré
- Ajout de la possibilité de spécifier des tables fixes sur les écrans d'appariements
- Ajout de la possibilité de spécifier les tournois affichés sur les écrans de résultats (#27)
- Affichage du numéro de ronde sur les écrans de résultats
- Simplification de la page d'accueil de l'interface web
- Présentation des évènements et des écrans à l'aide de tuiles
- Amélioration de l'authentification sur les écrans de saisie
- Ajout de la possibilité de restreindre la visibilité de certains évènements, certains écrans, certaines familles d'écrans, certains écrans rotatifs
- Ajout de la possibilité d'utiliser plusieurs chronomètres (#26)
- Ajout d'écrans fixes permettant d'insérer des images dans les écrans rotatifs
- Suppression de la personnalisation CSS et remplacement par une image et une couleur de fond
- Contournement d'un bug du site fédéral sur l'affichage des classements (suppression des forfaits en l'absence d'appariement) (#14)

## Version 2.3.2 - 15 avril 2024
- Correction d'un problème d'affichage des appariements par ordre alphabétique

## Version 2.3.1 - 14 avril 2024
- Correction d'un problème d'encodage des fichiers de configuration

## Version 2.3.0 - 8 avril 2024
- Affichage des joueur·euses par ordre alphabétique avant appariement
- Ajout du pointage sur les écrans de saisie
- Ajout de la [Foire Aux Questions](50-faq.md)
- Correction d'un problème d'affichage du classement et des grilles américaines sur le site fédéral pour les fichiers Papi générés depuis ChessEvent
- Correction d'un problème de couleurs sur les appariements par ordre alphabétique
- Interdiction du caractère `/` dans les identifiants des écrans et des tournois

## Version 2.2.1 - 28 mars 2024
- Correction d'un bug de configuration

## Version 2.2.0 - 27 mars 2024
- Allègement du moteur web (remplacement de Django par Litestar) (#24)
- Affichage du pointage des joueur·euses
- Enregistrement des coups illégaux (option `record_illegal_moves`)
- Mise à jour de l'URL de ChessEvent suite au déménagement de la plateforme

## Version 2.1.8 - 16 février 2024
- Suppression du _pooling_ ODBC

## Version 2.1.7 - 13 février 2024
- Corrections et amélioration de la documentation

## Version 2.1.6 - 4 février 2024
- Affichage des pilotes ODBC sur la page d'accueil

## Version 2.1.5 - 24 janvier 2024
- Simplification de la configuration des évènements :
  - Pour un modèle, suppression de l'obligation de préciser la rubrique `[template.<template_id>.boards]`/`[template.<template_id>.players]` lorsque l'évènement ne compte qu'un seul tournoi
  - Pour une famille, utilisation par défaut du modèle du même nom
  - Pour un écran rotatif, utilisation par défaut de la famille du même nom

## Version 2.1.4 - 23 janvier 2024
- Ajout de l'option `show_unpaired` pour limiter l'affichage des appariements par ordre alphabétique aux joueur·euses apparié·es

## Version 2.1.3 - 22 janvier 2024
- Mise en forfait général des joueur·euses non pointé·es dans ChessEvent dans les fichiers Papi

## Version 2.1.2 - 21 janvier 2024
- Ajout du numéro d'homologation de ChessEvent dans les fichiers Papi

## Version 2.1.1 - 10 décembre 2023
- Possibilité de fixer le nombre d'échiquiers ou de joueur·euses par écran
- Possibilité de fonctionner en réseau local sans aucune connexion internet (intégration des bibliothèques CSS et Javascript)

## Version 2.1.0 - 9 décembre 2023
- Création des fichiers Papi des tournois à partir de la plateforme d'inscription en ligne Chess Event
- Suppression des données personnelles des joueur·euses avant téléchargement sur le site fédéral

## Version 2.0.3 - 19 novembre 2023
- Réduction _a minima_ des téléchargements des tournois vers le site fédéral
- Amélioration de la détection de l'encodage des fichiers de configuration

## Version 2.0.0 - 10 novembre 2023
- Livraison sous forme d'un exécutable autonome (ne nécessite plus l'installation de XAMPP)
- Configuration des évènements au format INI (plus simple que PHP)
- Amélioration de la page d'accueil
- Ajout d'une page par évènement
- Ajout d'écrans d'affichage des appariements par ordre alphabétique
- Ajout des écrans rotatifs
- Simplification de la configuration des écrans grâce aux modèles et aux familles d'écran
- Ajout d'une temporisation pour le transfert des fichiers Papi sur le site fédéral
- Publication des sources

## Version 1.19 - 22 janvier 2023
- Correction d'un bug de protection des pages de saisie des résultats

## Version 1.18 - 4 février 2020
- Correction d'un bug d'affichage des derniers résultats
- Correction d'un bug de transmission sur le site fédéral

## Version 1.17 - 4 octobre 2019
- Correction d'un bug d'accès concurrent (saisie des résultats sur plusieurs écrans)
- Correction d'un bug d'affichage des joueurs avant appariement

## Version 1.16 - 31 août 2019
- Correction d'un bug d'affichage du chronomètre

## Version 1.15 - 31 août 2019
- Compatibilité avec Papi 3.3.6
- Support du système de Haley dégressif
- Support du « bye »
- Ajout du chronomètre
- Amélioration du rafraîchissement des pages
- Renommage de la propriété no-banner en no_banner

## Version 1.14 - 9 avril 2019
- Ajout des écrans d'affichage des résultats
- Ajout des écrans d'affichage des derniers résultats
- Ajout du rafraîchissement automatique des écrans de saisie
- Amélioration des temps de réponse
- Simplification des URL des écrans
- Téléchargement systématique des fichiers avant affichage sur le site FFE

## Version 1.13 - 10 novembre 2018
- Affichage des numéros des échiquiers

## Version 1.12 - 30 octobre 2018
- Support des tournois à handicap

## Version 1.11 - 27 octobre 2018
- Support du Suisse Accéléré Dégressif (SAD)
- Support de l'accélération de Haley

## Version 1.10 - 26 octobre 2018
- Possibilité de tester les codes d'accès au site FFE
- Possibilité de rendre les données visibles sur le site FFE
- Possibilité de télécharger les factures d'homologation depuis le site FFE
- Renommage du script `upload.bat` en `ffe.bat`

## Version 1.9 - 23 octobre 2018
- Correction de la mise en ligne sur le site fédéral

## Version 1.8 - 1er septembre 2018
- Amélioration des transitions entre les requêtes

## Version 1.7 - 31 août 2018
- Recherche automatique des mises à jour

## Version 1.6 - 30 août 2018
- Écriture de la documentation
- Diffusion sous forme d'une archive
- Amélioration de l'affichage des participants avant les appariements
- Amélioration des styles CSS (normalisation)
- Obfuscation des sources PHP

## Version 1.5 - 3 août 2018
- Ajout des personnalisations CSS
- Amélioration de l'affichage (bandeau supérieur toujours visible)

## Version 1.4 - 28 juillet 2018
- Gestion de plusieurs écrans de saisie

# Politique de numérotation des versions (`x.y.z`)

- `x` : numéro majeur (changements complets du logiciel)
- `y` : numéro mineur (modifications de configuration et évolutions fonctionnelles)
- `z` : numéro de correctif (modification du code)
