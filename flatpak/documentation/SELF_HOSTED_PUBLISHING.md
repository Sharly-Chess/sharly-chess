# 📦 Guide de Publication Multi-Architecture (Self-Hosted)

Ce document décrit le processus de publication automatisé de Sharly Chess via GitHub Actions sur un dépôt Flatpak auto-hébergé (GitHub Pages).

## 🎯 Vue d'ensemble

Contrairement à Flathub, nous utilisons ici notre propre dépôt Flatpak hébergé sur GitHub Pages. Cela nous permet de :
1.  Contrôler totalement le cycle de release.
2.  Publier automatiquement à chaque tag Git.
3.  Supporter le multi-architecture (x86_64 et ARM64).
4.  Gérer l'historique des versions pour permettre les rollbacks.

## ⚙️ Workflow GitHub Actions

Le fichier de workflow est : `.github/workflows/publish-multiarch.yml`

### Déclencheurs
- **Push de tag** : `*` (ex: `3.4.4`)
- **Dispatch manuel** : Via l'interface GitHub Actions.
- **Push sur branche** : `linux-flatpak` (pour le développement).

### Étapes du Pipeline

1.  **Build x86_64** :
    - Construit le Flatpak sur un runner Ubuntu standard.
    - Génère un artefact OSTree (`repo-x86_64.tar.gz`).
    - Met à jour automatiquement la version dans `appdata.xml`.

2.  **Build ARM64** :
    - Construit le Flatpak sur un runner ARM64 (Ubuntu 24.04 ARM).
    - Génère un artefact OSTree (`repo-arm64.tar.gz`).

3.  **Publish (Merge & Sign)** :
    - Récupère les artefacts des deux architectures.
    - Clone le dépôt de publication (branche de déploiement).
    - **Importe les commits** en préservant l'historique et les métadonnées via `flatpak build-commit-from`.
    - Signe les commits avec une clé GPG privée (stockée dans les secrets).
    - Met à jour le sommaire du dépôt (`flatpak build-update-repo`).
    - Pousse les changements sur la branche de déploiement.

## 🔑 Gestion des Clés GPG

Le dépôt est signé par une clé GPG privée pour garantir l'authenticité des mises à jour.

- **Secret GitHub** : `GPG_PRIVATE_KEY` contient la clé privée ASCII-armored.
- **Clé Publique** : La clé publique est exportée automatiquement dans le fichier `.flatpakrepo` pour que les clients puissent vérifier les signatures.

## 🔄 Gestion de l'Historique et Rollbacks

Le workflow utilise une méthode spécifique pour garantir que l'historique des mises à jour est préservé (Linked History).

### Pourquoi c'est important ?
Cela permet aux utilisateurs de :
1.  Voir l'historique des versions (`flatpak remote-info --log ...`).
2.  Revenir à une version précédente en cas de bug (Rollback).
3.  Optimiser les téléchargements (Delta updates).

### Commande Technique
Nous utilisons `flatpak build-commit-from` au lieu de `ostree commit` manuel.
```bash
flatpak build-commit-from --force \
  --src-repo=$SOURCE_REPO \
  --src-ref=$REF \
  --subject="Update $ARCH" \
  flatpak-repo-publish/repo $REF
```
Cette commande assure que :
- Les métadonnées AppStream (`xa.metadata`) sont conservées.
- Le nouveau commit a pour parent le commit précédent du dépôt de destination.

## 🛠️ Maintenance du Dépôt

Le dépôt est hébergé sur une branche dédiée au déploiement statique.
URL du dépôt : `https://<user>.github.io/sharly-chess/repo/`

### Fichiers Clés
- `repo/` : Le contenu OSTree (objets, refs, deltas).
- `sharly-chess.flatpakrepo` : Le fichier de configuration pour les clients.

### Nettoyage
Le workflow utilise `--prune` lors de `flatpak build-update-repo` pour supprimer les objets obsolètes qui ne sont plus référencés par l'historique, gardant la taille du dépôt sous contrôle.
