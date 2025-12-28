# 🚀 Guide de Publication sur Flathub

Ce document décrit la procédure pour publier **Sharly Chess** sur [Flathub](https://flathub.org/), le magasin d'applications principal pour Flatpak.

La publication sur Flathub permet aux utilisateurs d'installer et de mettre à jour l'application facilement via `flatpak install` et `flatpak update`, sans gérer de fichiers `.flatpak` manuellement.

---

## 📋 Prérequis

1.  Un compte GitHub.
2.  Le manifest Flatpak doit être stable et fonctionnel.
3.  L'application doit respecter les [Guidelines Flathub](https://docs.flathub.org/docs/for-app-authors/requirements/).

---

## 🛠️ Procédure de Soumission

### 1. Forker le dépôt `flathub/flathub`
Non, la procédure a changé. Maintenant, on soumet une **Pull Request** sur le dépôt [flathub/new-pr](https://github.com/flathub/new-pr) (ou on crée un dépôt dédié, mais la méthode standard est la suivante).

La méthode actuelle consiste à soumettre le manifest dans une PR sur le dépôt **New PRs** de Flathub.

1.  Allez sur [https://github.com/flathub/flathub/wiki/App-Submission](https://github.com/flathub/flathub/wiki/App-Submission).
2.  Forkez le dépôt [flathub/flathub](https://github.com/flathub/flathub) n'est plus la méthode.
3.  La méthode moderne :
    *   Créez un fork de [https://github.com/flathub/flathub](https://github.com/flathub/flathub) (pour les anciennes méthodes) ou suivez le workflow direct.
    *   En réalité, le plus simple est d'utiliser l'outil CLI ou l'interface web si disponible, mais la méthode standard reste via GitHub.

**Procédure simplifiée :**

1.  Forkez le dépôt [https://github.com/flathub/flathub](https://github.com/flathub/flathub).
2.  Créez une nouvelle branche `com.sharlychess.SharlyChess`.
3.  Ajoutez votre manifest (`com.sharlychess.SharlyChess.json`) et les fichiers associés (icônes, patchs) dans ce dépôt.
4.  Faites une Pull Request vers le dépôt principal `flathub/flathub`.

*Cependant, Flathub a migré vers une organisation par dépôt.*

**La VRAIE procédure actuelle (2024/2025) :**

1.  Allez sur [Flathub Submit](https://github.com/flathub/flathub/wiki/App-Submission).
2.  Vous devez créer une Pull Request sur le dépôt **[flathub/new-pr](https://github.com/flathub/new-pr)**.
3.  Cette PR doit contenir uniquement votre fichier manifest.

### Étape par Étape

1.  **Préparer le Manifest pour Flathub**
    *   Le manifest doit télécharger les sources depuis des URLs stables (GitHub Releases avec tags), pas de fichiers locaux.
    *   Actuellement, notre manifest utilise `../../requirements-flatpak.txt`. Pour Flathub, ce fichier doit être soit intégré dans le json, soit téléchargé depuis une URL brute (raw.githubusercontent...).

2.  **Créer la Pull Request**
    *   Forkez [flathub/new-pr](https://github.com/flathub/new-pr).
    *   Clonez votre fork.
    *   Créez une branche : `git checkout -b com.sharlychess.SharlyChess`.
    *   Ajoutez votre manifest renommé exactement en `com.sharlychess.SharlyChess.json`.
    *   Commitez et pushez.
    *   Ouvrez la PR sur GitHub.

3.  **Review et Bot**
    *   Le bot Flathub va valider la syntaxe (linter).
    *   Il va tenter un build de test.
    *   Des mainteneurs humains vont relire le manifest.

4.  **Acceptation**
    *   Une fois la PR acceptée, un dépôt dédié `https://github.com/flathub/com.sharlychess.SharlyChess` sera créé.
    *   Vous serez invité à rejoindre ce dépôt en tant que mainteneur.

---

## 🔄 Gestion des Mises à Jour (Une fois accepté)

Une fois que vous avez votre dépôt sur Flathub (`github.com/flathub/com.sharlychess.SharlyChess`) :

1.  **Pour mettre à jour l'application :**
    *   Modifiez le manifest dans ce dépôt Flathub (changez le tag de version, le hash du commit, etc.).
    *   Commitez et pushez sur la branche `master` (ou faites une PR).
    *   Le buildbot de Flathub détectera le changement, construira la nouvelle version et la publiera automatiquement.

2.  **Automatisation (GitHub Actions)**
    *   Il est possible de configurer un workflow dans le dépôt principal `sharly-chess` pour envoyer automatiquement les mises à jour vers le dépôt Flathub (via l'outil `flatpak-external-data-checker` ou des scripts custom).

---

## ⚠️ Modifications nécessaires du Manifest actuel

Le manifest actuel est conçu pour un build local (`sources: { type: file, path: ... }`). Pour Flathub, il faudra :

1.  Remplacer les sources locales par des sources `git` ou `archive` pointant vers les releases GitHub de Sharly Chess.
2.  Exemple pour le code source :
    ```json
    {
        "name": "sharly-chess",
        "buildsystem": "simple",
        "sources": [
            {
                "type": "git",
                "url": "https://github.com/Sharly-Chess/sharly-chess.git",
                "tag": "v3.4.3",
                "commit": "..."
            }
        ]
    }
    ```
3.  Gérer `requirements-flatpak.txt` : Le plus propre est d'utiliser le générateur `flatpak-pip-generator` pour convertir les dépendances Python en un manifest JSON complet, plutôt que d'utiliser `pip install -r requirements.txt` à l'exécution du build, car Flathub n'autorise pas l'accès réseau pendant le build (sauf pour les sources déclarées).

**Note importante :** Flathub interdit l'accès internet pendant la phase de build (`build-commands`). Tout doit être téléchargé en amont via la section `sources`.
*   Cela signifie que `pip install -r requirements.txt` **ne fonctionnera pas** tel quel sur Flathub.
*   Il faudra générer un fichier `python3-requirements.json` contenant toutes les URLs des wheels Python.

### Outil recommandé : `flatpak-pip-generator`
Utilisez cet outil pour générer les sources Python conformes à Flathub :
[https://github.com/flatpak/flatpak-builder-tools/tree/master/pip](https://github.com/flatpak/flatpak-builder-tools/tree/master/pip)
