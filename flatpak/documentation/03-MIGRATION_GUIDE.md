# Guide Complet: Transition AppImage → Flatpak pour Sharly Chess

**Version**: 1.0  
**Date**: 27 Décembre 2025  
**Audience**: DevOps, Développeurs, Release Manager

---

## 📚 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Prérequis](#prérequis)
4. [Installation environnement](#installation-environnement)
5. [Build local](#build-local)
6. [Tests fonctionnels](#tests-fonctionnels)
7. [CI/CD Setup](#cicd-setup)
8. [Publication Flathub](#publication-flathub)
9. [Troubleshooting](#troubleshooting)
10. [Rollback plan](#rollback-plan)

---

## Vue d'ensemble

### Objectif
Migrer la distribution Linux de Sharly Chess d'AppImage à Flatpak pour:
- ✅ Résoudre les incompatibilités multi-distribution
- ✅ Simplifier la maintenance des dépendances
- ✅ Améliorer l'intégration système
- ✅ Accéder au store Flathub

### Timeline
- **Semaine 1**: Setup + validation
- **Semaine 2**: Build local + tests
- **Semaine 3**: CI/CD + release
- **Semaine 4**: Flathub submission

---

## Architecture

```
flatpak/
├── configuration/              # Configuration files
│   ├── com.sharlychess.SharlyChess.json      # Manifest (YAML/JSON)
│   ├── com.sharlychess.SharlyChess.appdata.xml
│   └── com.sharlychess.SharlyChess.desktop
├── scripts/                    # Build & automation scripts
│   ├── launcher.py            # Application entrypoint
│   └── validate.py            # Manifest validation
├── testing/                    # Test suites
│   ├── functional_tests.py    # Flatpak-specific tests
│   └── unit_tests.py          # (Optional) Unit tests
├── .github/workflows/          # GitHub Actions workflows
│   └── linux-flatpak.yml      # Build automation
├── documentation/             # Guides & analysis
│   ├── 01-ANALYSE_REPOSITORY.md
│   ├── 02-ANALYSE_FLATPAK_FEASIBILITY.md
│   └── 03-MIGRATION_GUIDE.md  # This file
└── README.md                  # Quick start

requirements-flatpak.txt       # Python dependencies (root level)
```

---

## Prérequis

### Système
- **Linux** (Ubuntu 22.04+ ou Debian 12+, Fedora 39+, etc.)
- **Flatpak** >= 1.14
- **flatpak-builder** >= 1.2
- **Python 3.13+**
- **Git**
- **~10 GB** disque libre (pour runtimes + build)

### Compétences requises
- Familiarité avec Flatpak (ou volonté d'apprendre)
- Compréhension du manifest JSON
- Expérience Git/GitHub Actions

---

## Installation environnement

### Étape 1: Installer Flatpak & outils

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y flatpak flatpak-builder

# Fedora
sudo dnf install -y flatpak flatpak-builder

# Arch
sudo pacman -S flatpak flatpak-builder
```

**Vérification**:
```bash
flatpak --version
flatpak-builder --version
```

### Étape 2: Configurer Flathub

```bash
# Ajouter le repository principal Flathub
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

# Vérifier
flatpak remote-list
```

### Étape 3: Installer les runtimes GNOME

```bash
# Runtime GNOME Platform (base du système)
flatpak install -y flathub org.gnome.Platform//49

# SDK GNOME (pour la compilation)
flatpak install -y flathub org.gnome.Sdk//49

# Vérifier
flatpak list --runtimes
```

**Output attendu**:
```
org.gnome.Platform/x86_64/49              49      system
org.gnome.Sdk/x86_64/49                   49      system
```

### Étape 4: Cloner et explorer le repository

```bash
git clone https://github.com/sharly-chess/sharly-chess.git
cd sharly-chess

# Afficher la structure Flatpak
tree flatpak/ -L 2
```

---

## Build local

### Test 1: Validation du manifest

```bash
cd sharly-chess

# Valider le JSON manifest
python3 flatpak/scripts/validate.py
```

**Output attendu**:
```
========== FLATPAK MANIFEST VALIDATION REPORT ==========
Manifest: .../flatpak/configuration/com.sharlychess.SharlyChess.json
App ID: com.sharlychess.SharlyChess
Runtime: org.gnome.Platform
Modules: 4

✓ VALID
```

### Test 2: Build local (mode user)

```bash
# Créer répertoire build
mkdir -p build-flatpak

# Lancer le build
flatpak-builder \
  --user \
  --install \
  --force-clean \
  build-flatpak \
  flatpak/configuration/com.sharlychess.SharlyChess.json

# Cela peut prendre 10-30 minutes selon la vitesse du réseau
```

**Indicateurs de succès**:
- ✓ `Building module 'sharly-chess'`
- ✓ `Finishing build`
- ✓ Application installée

### Test 3: Lancer l'application (mode utilisateur)

```bash
# Lancer l'app
flatpak run com.sharlychess.SharlyChess

# Ou avec flags de debug
flatpak run --devel com.sharlychess.SharlyChess

# Ou en mode console
FLATPAK_DEBUG_PATH=/tmp/debug flatpak run --devel com.sharlychess.SharlyChess
```

**Vérifications**:
- [ ] Interface GUI apparaît
- [ ] Web server démarre (port 9000 accessible)
- [ ] Pas d'erreurs Python

### Troubleshooting Build

**Problème**: Build échoue sur cryptography
```bash
# Solution: Assurez-vous que libffi-dev est installé
sudo apt-get install -y libffi-dev libssl-dev
```

**Problème**: Timeout download
```bash
# Solution: Augmenter timeout
flatpak-builder --download-only build-flatpak flatpak/configuration/...
```

**Problème**: Espace disque insuffisant
```bash
# Vérifier espace
df -h

# Nettoyer (optionnel)
flatpak uninstall --unused
```

---

## Tests fonctionnels

### Suite de tests Flatpak

```bash
# Exécuter tous les tests
python3 flatpak/testing/functional_tests.py
```

**Output exemple**:
```
======================================================================
FLATPAK FUNCTIONAL TESTS
======================================================================

[ 1] Manifest exists                 ✓ Manifest exists: ...
[ 2] Valid JSON                      ✓ Manifest is valid JSON
[ 3] Required fields                 ✓ All required fields present
...
[15] Launcher script                 ✓ Launcher script exists: ...

======================================================================
RESULTS: 15 passed, 0 failed (15/15)
======================================================================
```

### Test d'intégration

```bash
# Test 1: Vérifier les données utilisateur sont sauvegardées
flatpak run com.sharlychess.SharlyChess
# => Créer un événement, quitter
# => Relancer et vérifier que l'événement existe toujours

# Test 2: Vérifier les connexions réseau
# => Essayer une connexion FFE (demande credentials)

# Test 3: Vérifier les permissions
flatpak info com.sharlychess.SharlyChess
```

### Tests système

```bash
# Test sur distribution cible
# Ex: Ubuntu 22.04, Debian 12, Fedora 39, etc.

# Installation depuis build local
flatpak install --user flatpak/build-dir/repo ...

# Ou exportation en fichier .flatpak
flatpak-builder --repo=/tmp/flatpak-repo build-flatpak flatpak/configuration/...
flatpak install --user file:///tmp/flatpak-repo
```

---

## CI/CD Setup

### Installation du workflow GitHub Actions

```bash
# Copier le workflow
mkdir -p .github/workflows
cp flatpak/ci-cd/flatpak-build.yml .github/workflows/

# Vérifier syntaxe YAML
python3 -m yaml -c .github/workflows/flatpak-build.yml || echo "YAML OK"

# Committer et pusher
git add .github/workflows/flatpak-build.yml
git commit -m "Add Flatpak CI/CD workflow"
git push origin main
```

### Vérifier le workflow dans GitHub

1. Aller à **GitHub** > **Actions** > **Flatpak Build & Test**
2. Déclencher manuellement si besoin:
   - Cliquer **Run workflow** > Choisir branche > **Run workflow**
3. Attendre que le build finisse (~5-10 min)

**Statut attendu**:
- ✓ Validate Flatpak Configuration
- ✓ Build Test (Dry-run)
- ✓ Security Checks
- ✓ Check Documentation

### Configuration des secrets (optionnel pour Flathub)

```bash
# Pour l'upload à Flathub (phase ultérieure)
# Ajouter dans GitHub Settings > Secrets:
# - FLATHUB_GITHUB_TOKEN
# - FLATHUB_REPO_PASSWORD
```

---

## Publication Flathub

### Préparation (Semaine 3)

#### 1. Vérifier la licence

```bash
# La licence AGPL-3.0 doit être dans le repo
cat LICENSE.md | head -20

# Vérifier dans le manifest
grep "project_license" flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml
# => Doit afficher: AGPL-3.0-or-later
```

#### 2. Tester avec appstream-util

```bash
# Installer outils
sudo apt-get install -y appstream-util

# Valider AppData
appstream-util validate-relax flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml

# Output attendu: ✓ Valid AppData
```

#### 3. Faire un test Flathub

```bash
# Cloner le repo Flathub
git clone https://github.com/flathub/flathub.git flathub-test
cd flathub-test

# Créer branche
git checkout -b sharly-chess-3.4.3

# Créer répertoire
mkdir -p com/sharlychess/SharlyChess

# Copier manifest
cp ~/sharly-chess/flatpak/configuration/com.sharlychess.SharlyChess.json \
   com/sharlychess/SharlyChess/

# Copier appdata
cp ~/sharly-chess/flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml \
   com/sharlychess/SharlyChess/

# Test build
flatpak-builder --repo=/tmp/test-repo build-test \
  com/sharlychess/SharlyChess/com.sharlychess.SharlyChess.json

# Vérifier
ls -la /tmp/test-repo/
```

### Publication officielle (Semaine 4)

#### 1. Fork Flathub

- Aller à https://github.com/flathub/flathub
- Cliquer **Fork**

#### 2. Préparer la PR

```bash
cd ~/flathub-fork

# Créer branche
git checkout -b sharly-chess

# Ajouter les fichiers
mkdir -p com/sharlychess/SharlyChess
cp flatpak/configuration/com.sharlychess.SharlyChess.json \
   com/sharlychess/SharlyChess/
cp flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml \
   com/sharlychess/SharlyChess/

# Ajouter un fichier metadata.yml
cat > com/sharlychess/SharlyChess/metadata.yml <<EOF
build-extension: false
skip-appdata-check: false
skip-icons-check: false

# Optionnel: build.yml pour CI/CD Flathub
EOF

# Committer
git add com/sharlychess/
git commit -m "Add Sharly Chess 3.4.3 to Flathub"
git push origin sharly-chess
```

#### 3. Créer Pull Request

- Aller à https://github.com/your-fork/flathub/compare/master...sharly-chess
- Cliquer **Create Pull Request**
- Remplir le template:
  ```
  - Application: Sharly Chess
  - Version: 3.4.3
  - License: AGPL-3.0
  - Category: Office/Utility
  ```

#### 4. Attendre review

- Flathub maintainers revieweront (1-2 semaines)
- Faire les ajustements demandés
- Une fois approuvé → publication automatique

#### 5. Post-publication

```bash
# Vérifier la publication
flatpak search sharly-chess

# Installer depuis Flathub
flatpak install flathub com.sharlychess.SharlyChess

# Vérifier
flatpak run com.sharlychess.SharlyChess
```

---

## Troubleshooting

### Build fails with "libffi not found"

```bash
# Solution
sudo apt-get install -y libffi-dev

# Nettoyer et relancer
flatpak-builder --force-clean build-flatpak flatpak/configuration/...
```

### "Permission denied" when launching

```bash
# Vérifier les permissions
flatpak run --devel com.sharlychess.SharlyChess --verbose

# Vérifier les finish-args
flatpak info --show=Permissions com.sharlychess.SharlyChess
```

### "Web server not starting"

```bash
# Vérifier que le port 9000 est disponible
netstat -tulpn | grep 9000

# Si occupé, trouver le processus
lsof -i :9000

# Vérifier les logs
flatpak run --devel com.sharlychess.SharlyChess 2>&1 | head -50
```

### "SQLite database not found"

```bash
# Vérifier les répertoires XDG
ls -la ~/.local/share/sharly-chess/
ls -la ~/.config/sharly-chess/

# Vérifier les permissions Flatpak
flatpak info com.sharlychess.SharlyChess | grep -i filesys
# => Doit avoir: --filesystem=home
```

### Débugging avancé

```bash
# Mode développeur complet
FLATPAK_DEBUG_PATH=/tmp/debug \
PYTHONUNBUFFERED=1 \
flatpak run --devel \
  --env=PYTHONPATH=/app/lib/python3.13/site-packages \
  com.sharlychess.SharlyChess --verbose 2>&1 | tee /tmp/flatpak-debug.log

# Analyser les logs
tail -100 /tmp/flatpak-debug.log
```

---

## Rollback plan

### Si problèmes majeurs

```bash
# 1. Désinstaller la version Flatpak
flatpak uninstall com.sharlychess.SharlyChess

# 2. Réactiver AppImage (temp)
# => Continuer à distribuer AppImage 3.4.2 pendant 6-12 mois

# 3. Git revert
git revert <commit-du-flatpak>
git push origin main

# 4. Notifier utilisateurs
# => Message dans app
# => Post sur forum/discord
```

### Rollback depuis Flathub

```bash
# Si la PR est rejetée ou problèmes post-publication
# 1. Clore la PR Flathub
# 2. Attendre que Flathub maintainers suppriment l'app
# 3. Ou garder AppImage comme principal
```

---

## Checklist finale

### Avant le release

- [ ] Tous les tests locaux passent (15/15)
- [ ] Manifest validé (JSON + schema)
- [ ] AppData validé avec appstream-util
- [ ] Build CI/CD successful
- [ ] Tests sur 3+ distributions Linux différentes
- [ ] Documentation mise à jour
- [ ] Release notes préparées

### Avant Flathub submission

- [ ] License déclarée correctement
- [ ] Metadata complétée (description, screenshots, etc.)
- [ ] Pas de dépendances propriétaires
- [ ] Permissions expliquées et justifiées
- [ ] Version numérotée correctement (3.4.3)

### Après publication

- [ ] Vérifier sur Flathub store
- [ ] Tester installation depuis Flathub
- [ ] Monitorer les issues/feedback
- [ ] Préparer hotfix si problèmes (3.4.4)

---

## Ressources

- [Flatpak Documentation](https://docs.flatpak.org/)
- [Flathub Submission Guide](https://github.com/flathub/flathub/wiki/App-Submission)
- [Flatpak for Python Developers](https://docs.flatpak.org/en/latest/python.html)
- [AppData Spec](https://www.freedesktop.org/software/appdata/docs/)

---

## Support

**Questions?**
- Ouvrir une issue sur GitHub
- Poser une question sur Discord
- Consulter la section FAQ

**Bugs Flatpak spécifiques?**
- Reporter sur [Flathub Issues](https://github.com/flathub/flathub/issues)
- Ou directement sur [Sharly Chess GitHub](https://github.com/sharly-chess/sharly-chess/issues)

