# 🐧 Guide Utilisateur : Installation de Sharly Chess (Flatpak)

Ce guide explique comment installer et utiliser **Sharly Chess** sur Linux via Flatpak. Cette méthode est recommandée car elle garantit que l'application fonctionne sur toutes les distributions Linux compatibles, indépendamment des versions de bibliothèques système.

---

## 📋 Prérequis

Avant de commencer, assurez-vous que **Flatpak** est installé sur votre système.

### 1. Vérifier si Flatpak est installé
Ouvrez un terminal et tapez :
```bash
flatpak --version
```
Si la commande retourne une version (ex: `Flatpak 1.14.x`), passez directement à l'étape **Installation**. Sinon, suivez les instructions ci-dessous.

### 2. Installer Flatpak (si nécessaire)

#### 🟠 Ubuntu / Debian / Linux Mint / Pop!_OS
```bash
sudo apt update
sudo apt install flatpak
```
*Note pour Ubuntu :* Si vous utilisez une version ancienne (avant 18.04), vous devrez peut-être ajouter le PPA officiel :
```bash
sudo add-apt-repository ppa:alexlarsson/flatpak
sudo apt update
sudo apt install flatpak
```

#### 🔵 Fedora / CentOS / RHEL
Flatpak est installé par défaut sur Fedora. Si ce n'est pas le cas :
```bash
sudo dnf install flatpak
```

#### 🟢 Arch Linux / Manjaro
```bash
sudo pacman -S flatpak
```

---

## 🚀 Installation de Sharly Chess

### 1. Ajouter le dépôt Flathub (Requis pour les dépendances)
Bien que Sharly Chess soit distribué indépendamment, il dépend de la plateforme **GNOME 49** qui est hébergée sur Flathub. Vous devez ajouter ce dépôt pour que Flatpak puisse télécharger automatiquement les composants nécessaires.

```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
```

### 2. Télécharger la dépendance GNOME 49 depuis Flathub
Sharly Chess nécessite l'environnement d'exécution **GNOME 49**. Si vous installez l'application depuis un fichier local, Flatpak peut ne pas le télécharger automatiquement.

Il est donc recommandé de le télécharger et l'installer manuellement depuis Flathub avec cette commande :

```bash
flatpak install flathub org.gnome.Platform//49
```

### 3. Télécharger et Installer Sharly Chess

Le paquet d'installation est disponible sur le site officiel.

1.  Téléchargez la dernière version Linux (`.flatpak`) à cette adresse :
    👉 **[https://sharly-chess.com/installation-linux/](https://sharly-chess.com/installation-linux/)**

2.  Ouvrez un terminal dans le dossier où vous avez téléchargé le fichier (généralement `Téléchargements`) :
    ```bash
    cd ~/Téléchargements
    ```

3.  Installez le paquet (remplacez `sharly-chess.flatpak` par le nom réel du fichier téléchargé) :
    ```bash
    flatpak install --user sharly-chess.flatpak
    ```
    *Note : Si l'étape 2 a été ignorée, Flatpak devrait vous proposer d'installer `org.gnome.Platform//49`. Acceptez avec `Y`.*

---

## 🎮 Lancer l'Application

### Via le Menu des Applications
L'icône **Sharly Chess** devrait apparaître dans votre menu d'applications système (GNOME, KDE, etc.). Cliquez simplement dessus pour lancer.

### Via le Terminal
Si vous préférez la ligne de commande ou pour voir les logs de démarrage :
```bash
flatpak run com.sharlychess.SharlyChess
```

---

## 🌐 Accéder à l'Interface Web

Sharly Chess démarre un serveur web local. Une fois l'application lancée :

1. Ouvrez votre navigateur web (Firefox, Chrome, etc.).
2. Accédez à l'adresse : **[http://localhost:8000](http://localhost:8000)**

> **Note** : Le port par défaut est `8000`. Si ce port est déjà utilisé, vous pouvez le changer (voir Configuration Avancée).

---

## 📂 Où sont mes fichiers ?

Contrairement à une installation classique, Flatpak isole l'application (sandbox). Vos données sont stockées dans des dossiers spécifiques :

| Type de Données | Emplacement sur votre disque |
|----------------|------------------------------|
| **Tournois (.sce)** | `~/.var/app/com.sharlychess.SharlyChess/data/events/` |
| **Logs** | `~/.var/app/com.sharlychess.SharlyChess/data/logs/` |
| **Configuration (.scc)** | `~/.var/app/com.sharlychess.SharlyChess/data/events/.scc` |

*(Le symbole `~` représente votre dossier personnel `/home/votre_nom`)*

---

## ⚙️ Configuration Avancée (Optionnel)

### Changer le Port d'Écoute
Si le port 8000 est occupé, vous pouvez lancer l'application sur un autre port via une variable d'environnement :

```bash
flatpak run --env=SHARLY_CHESS_PORT=9090 com.sharlychess.SharlyChess
```
L'application sera alors accessible sur `http://localhost:9090`.

### Mettre à jour l'application
Puisque l'application n'est pas encore hébergée sur un dépôt en ligne (comme Flathub), la mise à jour se fait manuellement :

1.  Téléchargez la nouvelle version du fichier `.flatpak` sur le site officiel.
2.  Lancez la commande d'installation (la même que pour la première installation) :
    ```bash
    flatpak install --user sharly-chess-nouvelle-version.flatpak
    ```
3.  Flatpak détectera que l'application est déjà installée et effectuera la mise à jour vers la nouvelle version tout en conservant vos données.

---

## ❓ Résolution de Problèmes

**L'application ne démarre pas ?**
Lancez-la depuis un terminal pour voir les erreurs :
```bash
flatpak run com.sharlychess.SharlyChess
```

**Problème de permissions ?**
Si vous n'arrivez pas à accéder à un fichier spécifique hors de votre dossier personnel, c'est normal (sécurité Flatpak). Déplacez le fichier dans votre dossier `Documents` ou `Téléchargements` pour que Sharly Chess puisse y accéder.

---

## 🖥️ Compatibilité Architecture

Cette image Flatpak est construite et testée pour l'architecture **x86_64** (PC standard Intel/AMD 64-bits).

| Architecture | Supporté ? | Remarques |
|--------------|------------|-----------|
| **x86_64** (AMD64) | ✅ OUI | Architecture standard PC/Laptop |
| **aarch64** (ARM64) | ❓ À TESTER | Théoriquement compatible (Python pur), mais non validé officiellement |
| **x86** (32-bits) | ❌ NON | Non supporté |
