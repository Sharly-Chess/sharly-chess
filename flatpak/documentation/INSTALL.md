# Installation de Sharly Chess sur Linux

Guide d'installation pour les utilisateurs Linux. Toutes les commandes utilisent le mode `--user` (aucun droit administrateur système requis, sauf pour l'installation initiale de Flatpak).

---

## 1. Prérequis : installer Flatpak

### Fedora / Linux Mint / Pop!_OS

Flatpak est **déjà installé** par défaut. Passez à l'étape 2.

### Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y flatpak
```

### Arch Linux / Manjaro

```bash
sudo pacman -S flatpak
```

### openSUSE

```bash
sudo zypper install flatpak
```

### Autres distributions

Consultez [flathub.org/setup](https://flathub.org/setup) pour votre distribution.

---

## 2. Intégration graphique (optionnel)

Pour installer des applications depuis la logithèque et ouvrir les fichiers `.flatpakrepo` en double-clic :

### GNOME (Ubuntu, Fedora Workstation)

```bash
sudo apt install gnome-software-plugin-flatpak    # Ubuntu/Debian
sudo dnf install gnome-software                    # Fedora (déjà inclus)
```

> Sur Ubuntu, cela ajoute "Logiciels" (icône bleu/blanc), distinct de "Ubuntu Software" (Snap Store).

### KDE Plasma (Kubuntu, KDE Neon)

```bash
sudo apt install plasma-discover-backend-flatpak   # Ubuntu/Debian
sudo dnf install discover                           # Fedora (déjà inclus)
```

---

## 3. Activer Flathub

Flathub **n'est pas configuré par défaut** sur la plupart des distributions. Il faut l'ajouter manuellement. Sharly Chess en a besoin pour télécharger ses dépendances (runtime GNOME).

```bash
# Ajouter Flathub en mode utilisateur (pas besoin de sudo)
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

Vérifier que Flathub est bien ajouté :

```bash
flatpak remotes --user
# Doit afficher "flathub" dans la liste
```

> **Note :** Si Flathub est déjà configuré au niveau système (`flatpak remotes` sans `--user`), il fonctionnera aussi. Mais l'ajout en `--user` est préférable car il ne nécessite aucun droit administrateur.

---

## 4. Redémarrer (obligatoire)

Si vous venez d'installer Flatpak pour la **première fois**, vous **devez redémarrer** votre ordinateur. Sans cela :

- Les icônes n'apparaîtront pas dans le menu
- Les variables d'environnement ne seront pas correctes
- La logithèque ne verra pas le plugin Flatpak

---

## 5. Installer Sharly Chess

### Méthode CLI (recommandée)

```bash
flatpak remote-add --user --if-not-exists sharly-chess \
  https://gilleshorn.github.io/sharly-chess/sharly-chess.flatpakrepo

flatpak install --user sharly-chess com.sharlychess.SharlyChess
```

### Méthode graphique

1. Téléchargez [sharly-chess.flatpakrepo](https://gilleshorn.github.io/sharly-chess/sharly-chess.flatpakrepo)
2. Double-cliquez sur le fichier → la logithèque s'ouvre
3. Ajoutez le dépôt, puis cherchez "Sharly Chess" et cliquez **Installer**

---

## Mises à jour

Sharly Chess se met à jour automatiquement avec vos autres applications Flatpak. Pour forcer :

```bash
flatpak update --user
```

---

## Revenir à une version précédente (rollback)

### 1. Lister les versions disponibles

```bash
flatpak remote-info --user --log sharly-chess com.sharlychess.SharlyChess
```

Repérez le hash du commit correspondant à la version souhaitée (ex : "Version 3.5.1 (x86_64)").

### 2. Revenir à cette version

```bash
flatpak update --user --commit=HASH_COMPLET com.sharlychess.SharlyChess
```

### 3. Épingler pour empêcher la mise à jour automatique

```bash
flatpak pin --user com.sharlychess.SharlyChess
```

Pour retirer l'épinglage :

```bash
flatpak pin --user --remove com.sharlychess.SharlyChess
```

---

## Canal de développement (Dev)

Un dépôt séparé contient les builds les plus récents (potentiellement instables). Utile pour tester les nouvelles fonctionnalités avant leur publication.

> **Note :** Les versions dev et production partagent le même App ID (`com.sharlychess.SharlyChess`). Il n'est pas possible de les avoir installées simultanément. Cependant, les données ne risquent pas d'être corrompues car chaque version stocke ses données dans un dossier dédié (ex : `sharly-chess-3.6.0b1/`).

### Installer le canal Dev

```bash
flatpak remote-add --user --if-not-exists sharly-chess-dev \
  https://gilleshorn.github.io/sharly-chess/sharly-chess-dev.flatpakrepo

flatpak install --user sharly-chess-dev com.sharlychess.SharlyChess
```

### Basculer de Production vers Dev

```bash
flatpak uninstall --user com.sharlychess.SharlyChess
flatpak install --user sharly-chess-dev com.sharlychess.SharlyChess
```

### Basculer de Dev vers Production

```bash
flatpak uninstall --user com.sharlychess.SharlyChess
flatpak install --user sharly-chess com.sharlychess.SharlyChess
```

---

## Stockage des données

Les données de l'application sont stockées dans un répertoire isolé, avec un sous-dossier par version :

```
~/.var/app/com.sharlychess.SharlyChess/data/
└── sharly-chess-X.Y.Z/
    ├── events/          # Tournois (.sce) et configuration (.scc)
    │   └── archives/    # Tournois archivés (.sca)
    ├── logs/            # Journal d'activité
    ├── tmp/             # Bases temporaires (FIDE, FFE, sessions)
    └── custom/          # Fichiers personnalisés
```

### Sauvegarde

```bash
tar -czf sharly_chess_backup_$(date +%Y%m%d).tar.gz \
  ~/.var/app/com.sharlychess.SharlyChess/data/
```

### Restauration

```bash
tar -xzf sharly_chess_backup_*.tar.gz -C ~/
```

---

## Désinstallation complète

```bash
# Supprimer l'application (conserver les données)
flatpak uninstall --user com.sharlychess.SharlyChess

# Supprimer l'application ET toutes les données
flatpak uninstall --user --delete-data com.sharlychess.SharlyChess

# Supprimer le dépôt
flatpak remote-delete --user sharly-chess

# (Optionnel) Supprimer aussi le dépôt dev
flatpak remote-delete --user sharly-chess-dev
```

---

## Dépannage

| Problème | Solution |
|----------|----------|
| L'app n'apparaît pas dans le menu | Avez-vous redémarré après la première installation de Flatpak ? |
| Erreur de vérification GPG | Ajoutez `--no-gpg-verify` à la commande `remote-add` |
| Icône manquante | `gtk-update-icon-cache ~/.local/share/icons/hicolor` |
| Runtime manquant | `flatpak install --user flathub org.gnome.Platform//49` |
| "App not found" lors de l'installation | Vérifiez que le remote est ajouté : `flatpak remotes --user` |
