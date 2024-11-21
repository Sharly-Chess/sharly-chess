**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Installation et mise à jour

## Prérequis

Un ordinateur sous Windows avec :
  - [la dernière version de Papi](https://dna.ffechecs.fr/ressources/appariements/papi/) opérationnelle (septembre 2024 : version 3.3.8)
  - [le pilote Access](https://www.microsoft.com/en-us/download/details.aspx?id=54920) permettant de modifier les fichiers Papi

> [!NOTE]
> L'installation de XAMPP ou d'autres outils tiers n'est plus nécessaire à partir de la version 2.0.

## Téléchargement et installation

Téléchargez la dernière version de Papi-web, décompressez et installez-la 
sur l'ordinateur qui jouera le rôle de serveur (sur lequel seront également les fichiers Papi).

- **[Télécharger la dernière version stable](https://github.com/papi-web-org/papi-web/releases)**

| Fichiers et répertoires      | Type                 | Signification                                                                              |
|------------------------------|----------------------|--------------------------------------------------------------------------------------------|
| **`server.bat`**             | **Script**           | Le script de lancement du serveur de Papi-web                                              |
| **`ffe.bat`**                | **Script**           | Le script de lancement des outils d'interface avec le site fédéral                         |
| **`chessevent.bat`**         | **Script**           | Le script de création des fichiers papi des tournois à partir de la plateforme Chess Event |
| **`papi-web.ini`**           | **Configuration**    | Le fichier de configuration de Papi-web                                                    |
| **`events\*.db`**            | **Configuration**    | Les évènements (un fichier par évènement)                                                  |
| **`papi\*.papi`**            | **Papi**             | Les fichiers Papi des tournois gérés (localisation par défaut)                             |
| **`custom\*.*`**             | **Personnalisation** | Les fichiers de personnalisation des écrans d'affichage, de saisie, ...                    |
| `bin\papi-web-<version>.exe` | Exécutable           | L'exécutable unique de Papi-web                                                            |
| `tmp\*.*`                    | Temporaire           | Les fichiers temporaires                                                                   |

> [!NOTE]
> Selon votre antivirus, il est possible que vous deviez ajouter une exception pour le fichier exécutable `bin\papi-web-<version>.exe` (par exemple dans Avast : ☰ Menu ▸ Paramètres ▸ Général ▸ Exclusions ▸ Ajouter une exclusion).

## Mise à jour

Pour installer une nouvelle version de Papi-web :
1. décompressez l'archive de la nouvelle version au même niveau que la version déjà installée
2. suivez les instructions pour récupérer vos évènements, fichiers Papi et fichiers de personnalisation
