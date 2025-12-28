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
│    ├─ events/                                   │
│    │  ├─ .scc (Configuration)                   │
│    │  └─ *.sce (Fichiers Tournois)              │
│    │                                            │
│    ├─ logs/                                     │
│    │  └─ sharly-chess.log                       │
│    │                                            │
│    └─ tmp/                                      │
│       └─ (Fichiers temporaires)                 │
│                                                   │
└─────────────────────────────────────────────────┘
```

> **Note** : L'application n'utilise pas les répertoires standards `~/.local/share` ou `~/.config` directement. Elle utilise des chemins relatifs (`events/`, `logs/`) par rapport à son répertoire de travail, qui est défini par le lanceur Flatpak sur le répertoire de données de l'application.

## 🔑 Permission de Stockage

### Manifest Flatpak
```json
"finish-args": [
  "--filesystem=home:rw"
]
```

Bien que l'application ait accès au répertoire `home` (pour permettre l'import/export de fichiers depuis `Documents` ou `Téléchargements`), elle stocke ses données internes dans son répertoire privé `~/.var/app/...`.

## 📂 Répertoires Principaux

### 1. Données et Configuration (`events/`)
Ce répertoire contient à la fois les données des tournois et la configuration de l'application.

```
~/.var/app/com.sharlychess.SharlyChess/data/events/
├─ .scc                  (Base de données de Configuration SQLite)
└─ *.sce                 (Bases de données de Tournois SQLite)
```

### 2. Logs (`logs/`)
```
~/.var/app/com.sharlychess.SharlyChess/data/logs/
└─ sharly-chess.log      (Journal d'activité de l'application)
```

### 3. Temporaire (`tmp/`)
```
~/.var/app/com.sharlychess.SharlyChess/data/tmp/
└─ ...                   (Fichiers temporaires, cache, etc.)
```

## 🗄️ Base de Données SQLite

### Configuration (`.scc`)
- **Emplacement** : `~/.var/app/com.sharlychess.SharlyChess/data/events/.scc`
- **Rôle** : Stocke les préférences utilisateur, la configuration réseau, etc.

### Tournois (`.sce`)
- **Emplacement** : `~/.var/app/com.sharlychess.SharlyChess/data/events/*.sce`
- **Rôle** : Chaque fichier `.sce` est une base de données SQLite complète contenant toutes les données d'un tournoi.

## 🔄 Sauvegarde et Restauration

Pour sauvegarder toutes les données de l'application (configuration et tournois), il suffit de sauvegarder le répertoire `data` de l'application Flatpak.

### Backup Manuel
```bash
# Créer une archive de toutes les données
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
