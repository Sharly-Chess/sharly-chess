# 💾 Stockage de Fichiers en Flatpak - Sharly Chess

Guide pour la gestion du stockage persistent et des fichiers locaux dans Flatpak.

## 📁 Structure de Répertoires

```
┌─────────────────────────────────────────────────┐
│ Système de Fichiers Hôte                         │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ Home Utilisateur (~)                             │
│                                                   │
│ ├─ .local/share/sharly-chess/  ✅ RW            │
│ │  ├─ databases/                                │
│ │  │  ├─ sharly_chess.db                        │
│ │  │  └─ cache.db                               │
│ │  ├─ logs/                                     │
│ │  ├─ reports/                                  │
│ │  └─ uploads/                                  │
│ │                                                │
│ ├─ .config/sharly-chess/  ✅ RW                 │
│ │  ├─ config.json                               │
│ │  └─ credentials/                              │
│ │                                                │
│ ├─ .cache/sharly-chess/  ✅ RW                  │
│ │  ├─ http_cache/                               │
│ │  └─ compiled_assets/                          │
│ │                                                │
│ └─ Documents/  ✅ RW                            │
│    └─ Tournament Reports/                       │
│                                                   │
└─────────────────────────────────────────────────┘
```

## 🔑 Permission de Stockage

### Manifest Flatpak
```json
"finish-args": [
  "--filesystem=home:rw"
]
```

**Signification** :
- `home` : Accès au répertoire home (~)
- `:rw` : Lecture ET Écriture

**Alternative (plus restrictif)** :
```json
"--filesystem=xdg-data/sharly-chess:rw"  // ~/.local/share/sharly-chess seulement
```

Mais cela **casserait l'app** car Sharly Chess a besoin d'accéder à :
- `~/.config/` pour la configuration
- `~/.local/share/` pour les données
- `~/Documents/` pour les exports

## 📂 Répertoires Principaux

### 1. Données Applicatives
```
~/.local/share/sharly-chess/
├─ databases/
│  ├─ sharly_chess.db      (SQLite principal)
│  ├─ cache.db             (Cache)
│  └─ backup/              (Backups automatiques)
│
├─ logs/
│  ├─ application.log      (Logs app)
│  ├─ access.log           (Logs HTTP)
│  └─ errors.log           (Logs erreurs)
│
├─ reports/
│  ├─ tournaments/
│  ├─ rankings/
│  └─ pairings/
│
├─ uploads/
│  ├─ images/
│  ├─ documents/
│  └─ imports/
│
└─ temp/                   (Fichiers temporaires)
```

**Création automatique** : Sharly Chess les crée au premier lancement

### 2. Configuration
```
~/.config/sharly-chess/
├─ config.json            (Configuration globale)
├─ credentials.enc        (Crédentiels chiffrés)
└─ plugins.conf
```

### 3. Cache
```
~/.cache/sharly-chess/
├─ http_cache/            (Cache HTTP)
├─ compiled_assets/       (Assets compilés)
└─ thumbnails/            (Miniatures images)
```

### 4. Données Utilisateur
```
~/Documents/
└─ Sharly Chess/
   ├─ Tournament Reports/
   ├─ Exports/
   └─ Backups/
```

## 🗄️ Base de Données SQLite

### Emplacement
```
~/.local/share/sharly-chess/databases/sharly_chess.db
```

### Caractéristiques
- **Format** : SQLite 3
- **Taille** : ~10-100 MB (selon données)
- **Accès** : R/W (read/write)
- **Backup** : Automatique (quotidien par défaut)

### Permissions Flatpak
```bash
# Automatiquement RW via --filesystem=home:rw
chmod 644 ~/.local/share/sharly-chess/databases/sharly_chess.db
```

### Backup/Restore
```bash
# Backup manuel
cp ~/.local/share/sharly-chess/databases/sharly_chess.db \
   ~/.local/share/sharly-chess/databases/backup_$(date +%Y%m%d).db

# Restore
cp ~/.local/share/sharly-chess/databases/backup_20251227.db \
   ~/.local/share/sharly-chess/databases/sharly_chess.db
```

## 📋 Fichiers Générés

### Logs
```
~/.local/share/sharly-chess/logs/
├─ application.log          (Logs généraux)
├─ access.log               (Requêtes HTTP)
├─ chess_results.log        (Intégration Chess-Results)
└─ ffe.log                  (Intégration FFE)
```

### Reports
```
~/.local/share/sharly-chess/reports/
├─ tournament_2024.pdf      (Exports PDF)
├─ rankings_2024.xlsx       (Exports Excel)
└─ pairings_round5.txt      (Exports texte)
```

## 🛡️ Isolation et Sécurité

### Avantages Flatpak
✅ Isolé du reste du système
✅ Permissions explicites (`--filesystem=home:rw`)
✅ Logs de tous les accès fichiers
✅ Confinement par appID

### Limitations
⚠️ Tout utilisateur qui lance Flatpak peut accéder au home
⚠️ Pas de permission par-fichier (tout ou rien)
⚠️ Backup manuel à prévoir

## 📊 Espace Disque

| Component | Taille Typique | Croissance |
|-----------|----------------|------------|
| DB principale | 10-50 MB | +1 MB/tournoi |
| Logs | 5-20 MB | +1 MB/jour |
| Reports | 50-200 MB | +5 MB/export |
| Cache | 10-50 MB | +1 MB/semaine |
| **Total** | **100-300 MB** | **Graduellement** |

## 🔄 Synchronisation Réseau

### Nextcloud / Synology
```bash
# Syncer le home avec NAS
~/.local/share/sharly-chess/ → NAS backup

# Dans ~/.config/sharly-chess/
BACKUP_ENABLED=1
BACKUP_INTERVAL=daily
BACKUP_DESTINATION=/media/nas/backups/
```

### Git Backup (pour config)
```bash
cd ~/.config/sharly-chess
git init
git add .
git commit -m "Initial config"
# Pousser vers GitHub/GitLab
```

## 🚀 Migration / Restauration

### Déménagement vers Nouvelle Machine

```bash
# 1. Sur l'ancienne machine
tar -czf sharly_chess_backup.tar.gz \
  ~/.local/share/sharly-chess/ \
  ~/.config/sharly-chess/

# 2. Copier le fichier

# 3. Sur la nouvelle machine
mkdir -p ~/.local/share ~/.config
tar -xzf sharly_chess_backup.tar.gz -C ~/

# 4. Relancer l'app
flatpak run com.sharlychess.SharlyChess
```

### Docker/Kubernetes
```dockerfile
# Dockerfile
FROM ghcr.io/sharlychess/sharlychess:latest

# Copier données persistantes
COPY --chown=flatpak:flatpak ./data ~/.local/share/sharly-chess/
COPY --chown=flatpak:flatpak ./config ~/.config/sharly-chess/

VOLUME ["/home/flatpak/.local/share/sharly-chess"]
VOLUME ["/home/flatpak/.config/sharly-chess"]
```

## ✅ Bonnes Pratiques

### 1. Backup Régulier
```bash
#!/bin/bash
# backup-sharly-chess.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/external/backups"

tar -czf "$BACKUP_DIR/sharly_chess_$DATE.tar.gz" \
  ~/.local/share/sharly-chess/ \
  ~/.config/sharly-chess/

# Garder les 10 derniers backups
cd "$BACKUP_DIR"
ls -t sharly_chess_*.tar.gz | tail -n +11 | xargs rm -f
```

### 2. Monitoring Espace Disque
```bash
du -sh ~/.local/share/sharly-chess/
du -sh ~/.config/sharly-chess/
du -sh ~/.cache/sharly-chess/
```

### 3. Nettoyage Cache
```bash
# Vider le cache (sûr)
rm -rf ~/.cache/sharly-chess/*

# Nettoyer logs anciens
find ~/.local/share/sharly-chess/logs -mtime +30 -delete
```

### 4. Permissions Fichiers
```bash
# Vérifier permissions
ls -l ~/.local/share/sharly-chess/databases/

# Corriger si nécessaire
chmod 644 ~/.local/share/sharly-chess/databases/*.db
chmod 755 ~/.local/share/sharly-chess/databases/
```

## 🔒 Données Sensibles

### Stockage de Crédentiels
```
~/.config/sharly-chess/credentials.enc
```

**Chiffrement** : AES-256 (via Python cryptography)
**Clés** : Stockées dans les secrets GitHub (production)

### Logs Sensibles
Les fichiers de log peuvent contenir :
- Usernames
- IPs clients
- Requêtes HTTP

**Protection** :
```bash
chmod 600 ~/.local/share/sharly-chess/logs/*.log
```

## 🧹 Nettoyage Complet

### Désinstallation Complète
```bash
# Désinstaller Flatpak
flatpak uninstall --delete-data com.sharlychess.SharlyChess

# Ou manuellement
rm -rf ~/.local/share/sharly-chess/
rm -rf ~/.config/sharly-chess/
rm -rf ~/.cache/sharly-chess/
```

## 📚 Documentation Supplémentaire

- [Flatpak Filesystem Permissions](https://docs.flatpak.org/en/latest/portal-permissions.html#filesystem)
- [XDG Base Directory](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- [SQLite Best Practices](https://www.sqlite.org/bestpractice.html)
