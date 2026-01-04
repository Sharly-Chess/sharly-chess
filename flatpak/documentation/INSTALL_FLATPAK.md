# Installation de Sharly Chess sur Linux (Flatpak)

Ce guide détaille les méthodes pour installer Sharly Chess sur les distributions Linux compatibles Flatpak (Fedora, Ubuntu, Linux Mint, Arch, etc.).

## Prérequis

Assurez-vous que Flatpak est installé sur votre système et que le dépôt Flathub est activé (nécessaire pour les dépendances GNOME).

*   **Fedora / Linux Mint :** Installé par défaut.
*   **Ubuntu :**
    ```bash
    sudo apt install flatpak
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    ```
*   **Autres distributions :** Consultez [flatpak.org/setup](https://flatpak.org/setup/).

## Méthode 1 : Installation en ligne de commande (Recommandée)

C'est la méthode la plus fiable. Ouvrez un terminal et copiez-collez la commande suivante :

```bash
flatpak remote-add --user --if-not-exists sharly-chess https://gilleshorn.github.io/sharly-chess/sharly-chess.flatpakrepo && \
flatpak install --user sharly-chess com.sharlychess.SharlyChess
```

*Note : Si vous rencontrez des erreurs de vérification GPG lors de l'ajout, vous pouvez ajouter l'option `--no-gpg-verify` à la commande `remote-add`.*

## Méthode 2 : Installation via fichier (Graphique)

Cette méthode permet d'ajouter le dépôt via votre logithèque (GNOME Software, KDE Discover).

1.  **Télécharger le fichier de configuration :**
    [sharly-chess.flatpakrepo](https://gilleshorn.github.io/sharly-chess/sharly-chess.flatpakrepo)

2.  **Installer :**
    *   Double-cliquez sur le fichier téléchargé.
    *   Votre logithèque devrait s'ouvrir et vous proposer d'installer le dépôt "Sharly Chess".
    *   Une fois ajouté, recherchez "Sharly Chess" dans la logithèque et cliquez sur **Installer**.

## Mises à jour

L'application se mettra à jour automatiquement avec vos autres applications Flatpak. Pour forcer une mise à jour :

```bash
flatpak update
```

## Dépannage

Si vous avez besoin de repartir de zéro (nettoyage complet) :

```bash
# Désinstaller l'application
flatpak uninstall --user com.sharlychess.SharlyChess

# Supprimer le dépôt
flatpak remote-delete --user sharly-chess
```
