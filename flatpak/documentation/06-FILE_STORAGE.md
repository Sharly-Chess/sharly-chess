# 💾 Stockage de Fichiers en Flatpak - Sharly Chess

Guide pour la gestion du stockage persistent et des fichiers locaux dans Flatpak.

## 📁 Structure de Répertoires

L'application Sharly Chess, lorsqu'elle est exécutée via Flatpak, utilise un stockage isolé dans le répertoire de données de l'application (`XDG_DATA_HOME`).

```
┌─────────────────────────────────────────────────┐
│ Système de Fichiers Hôte                         │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ Home Utilisateur (~)                             │
│                                                   │
│ └─ .var/app/com.sharlychess.SharlyChess/data/   │
│    │                                            │
│    └─ sharly-chess-3.4.4/ (Dossier de Version)  │
│       │                                         │
│       ├─ events/                                │
│       │  ├─ .scc (Configuration)                │
│       │  ├─ *.sce (Fichiers Tournois)           │
│       │  └─ archives/ (*.sca)                   │
│       │                                         │
│       ├─ logs/                                  │
│       │  └─ sharly-chess.log                    │
│       │                                         │
│       ├─ tmp/                                   │
│       │  ├─ fide.sqlite (Base Joueurs)          │
│       │  └─ session.db                          │
│       │                                         │
│       └─ custom/                                │
│          └─ (Fichiers personnalisés)            │
│                                                   │
└─────────────────────────────────────────────────┘
```

> **Note** : L'application utilise un sous-dossier spécifique à la version (ex: `sharly-chess-3.4.4`) pour garantir l'isolation des données entre les mises à jour majeures, tout en conservant la structure standard de Sharly Chess.

## 🔑 Permission de Stockage

### Manifest Flatpak
```json
"finish-args": [
  "--filesystem=home:rw"
]
```

Bien que l'application ait accès au répertoire `home` (pour permettre l'import/export de fichiers depuis `Documents` ou `Téléchargements`), elle stocke ses données internes dans son répertoire privé `~/.var/app/...`.

## 📂 Répertoires Principaux

Tous les répertoires suivants se trouvent à l'intérieur du dossier de version (ex: `~/.var/app/com.sharlychess.SharlyChess/data/sharly-chess-3.4.4/`).

### 1. Données et Configuration (`events/`)
Ce répertoire contient à la fois les données des tournois et la configuration de l'application.

```
.../events/
├─ .scc                  (Base de données de Configuration SQLite)
├─ *.sce                 (Bases de données de Tournois SQLite)
└─ archives/             (Tournois archivés *.sca)
```

### 2. Logs (`logs/`)
```
.../logs/
└─ sharly-chess.log      (Journal d'activité de l'application)
```

### 3. Temporaire (`tmp/`)
Contient les bases de données téléchargées (FIDE, FFE) et les sessions.
```
.../tmp/
├─ fide.sqlite           (Base joueurs FIDE)
├─ ffe.sqlite            (Base joueurs FFE)
└─ session.db            (Sessions web)
```

### 4. Personnalisé (`custom/`)
```
.../custom/
└─ ...                   (Fichiers spécifiques utilisateur)
```

## 🗄️ Base de Données SQLite

### Configuration (`.scc`)
- **Emplacement** : `.../events/.scc`
- **Rôle** : Stocke les préférences utilisateur, la configuration réseau, etc.

### Tournois (`.sce`)
- **Emplacement** : `.../events/*.sce`
- **Rôle** : Chaque fichier `.sce` est une base de données SQLite complète contenant toutes les données d'un tournoi.

## 🔄 Sauvegarde et Restauration

Pour sauvegarder toutes les données de l'application (configuration et tournois), il suffit de sauvegarder le répertoire `data` de l'application Flatpak.

### Backup Manuel
```bash
# Créer une archive de toutes les données (toutes versions confondues)
tar -czf sharly_chess_backup_$(date +%Y%m%d).tar.gz \
  ~/.var/app/com.sharlychess.SharlyChess/data/
```

### Restauration
```bash
# Restaurer les données (attention, cela écrase les données existantes)
tar -xzf sharly_chess_backup_20240101.tar.gz -C ~/
```

## 🧹 Nettoyage

Pour réinitialiser complètement l'application (supprimer toutes les données et configurations) :

```bash
# Via la commande flatpak
flatpak uninstall --delete-data com.sharlychess.SharlyChess

# Ou manuellement
rm -rf ~/.var/app/com.sharlychess.SharlyChess/
```

## ℹ️ Détails Techniques

Le script de lancement (`launcher.py`) configure l'environnement comme suit :
1. Il détecte ou définit `XDG_DATA_HOME` (par défaut `~/.var/app/com.sharlychess.SharlyChess/data`).
2. Il crée les sous-répertoires `events`, `logs`, et `tmp` s'ils n'existent pas.
3. Il change le répertoire de travail courant (`CWD`) vers ce répertoire de données.
4. Il lance l'application Python.

Comme l'application utilise des chemins relatifs (ex: `Path('events')`), les fichiers sont créés au bon endroit dans le stockage persistant de l'application.
