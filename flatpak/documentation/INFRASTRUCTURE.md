# Guide Infrastructure — Configuration du déploiement Flatpak

Ce document est destiné au **mainteneur** qui configure l'infrastructure de déploiement de zéro. Il couvre la génération des clés GPG, la configuration de GitHub Pages pour héberger les dépôts OSTree, et la mise en place des secrets.

> **Ce document est interne.** Il ne doit pas être publié sur GitHub ou partagé publiquement car il décrit des procédures sensibles (gestion des clés de signature).

---

## Vue d'ensemble

```
┌──────────────────────────────────────────────────────────┐
│                    GitHub Repository                      │
│                                                           │
│  Branche: linux-flatpak          Branche: gh-pages        │
│  ┌───────────────────┐           ┌──────────────────────┐ │
│  │ Code source        │           │ repo/                │ │
│  │ flatpak/config      │  build   │   (OSTree prod)      │ │
│  │ .github/workflows   │────────▶ │ repo-dev/            │ │
│  │                     │ publish  │   (OSTree dev)       │ │
│  └───────────────────┘           │ sharly-chess.flatpakrepo │
│                                   │ sharly-chess-dev.flatpakrepo │
│         Secrets:                  │ .nojekyll             │ │
│         • GPG_PRIVATE_KEY         └──────────────────────┘ │
│         • FFE_*                                           │
│         • CHESS_RESULTS_*         GitHub Pages activé      │
│                                   sur gh-pages             │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
              https://gilleshorn.github.io/sharly-chess/
              ├── repo/                    ← utilisateurs prod
              ├── repo-dev/                ← testeurs dev
              ├── sharly-chess.flatpakrepo ← fichier config prod
              └── sharly-chess-dev.flatpakrepo ← fichier config dev
```

---

## 1. Générer les clés GPG

Les dépôts OSTree doivent être signés avec une clé GPG pour que Flatpak accepte les mises à jour. La clé privée est utilisée par le CI pour signer, et la clé publique est embarquée dans les fichiers `.flatpakrepo` pour que les clients puissent vérifier.

### Génération

```bash
# Générer une paire de clés (sans phrase de passe pour le CI)
gpg --batch --gen-key <<EOF
%no-protection
Key-Type: RSA
Key-Length: 4096
Name-Real: Sharly Chess Flatpak
Name-Email: flatpak@sharly-chess.com
Expire-Date: 0
%commit
EOF
```

### Export

```bash
# Identifier l'ID de la clé
gpg --list-secret-keys --with-colons | grep "^sec" | cut -d: -f5

# Exporter la clé privée (pour GitHub Secrets)
gpg --export-secret-keys --armor <KEY_ID> > private.key

# Exporter la clé publique (pour référence)
gpg --export --armor <KEY_ID> > public.key
```

### Stockage sécurisé

- **`private.key`** : Stocker en local hors du dépôt git (ex: `C:\tools\gpg\private.key`). Ne jamais committer.
- **`public.key`** : Même emplacement, pour référence. La clé publique est auto-générée dans les `.flatpakrepo` par le workflow.
- Le `.gitignore` du projet contient déjà `*.key`.

---

## 2. Configurer GitHub Pages

### Activer GitHub Pages

1. Aller dans **Settings → Pages** du repository GitHub
2. Source : **Deploy from a branch**
3. Branche : **gh-pages** / dossier **/ (root)**
4. Sauvegarder

### Initialiser la branche gh-pages

Si la branche `gh-pages` n'existe pas encore :

```bash
git checkout --orphan gh-pages
git rm -rf .
touch .nojekyll    # Empêcher Jekyll de traiter les fichiers
git add .nojekyll
git commit -m "Initialize gh-pages"
git push origin gh-pages
```

> **Important :** Le fichier `.nojekyll` est indispensable. Sans lui, GitHub Pages ignore les dossiers commençant par un underscore et peut mal traiter les fichiers binaires OSTree.

### Structure attendue sur gh-pages

Le workflow crée automatiquement cette structure :

```
gh-pages/
├── .nojekyll
├── sharly-chess.flatpakrepo        # Config client production
├── sharly-chess-dev.flatpakrepo    # Config client dev
├── repo/                           # Dépôt OSTree production
│   ├── config
│   ├── objects/
│   ├── refs/
│   ├── summary
│   ├── summary.sig
│   └── deltas/
└── repo-dev/                       # Dépôt OSTree dev
    ├── config
    ├── objects/
    ├── refs/
    ├── summary
    ├── summary.sig
    └── deltas/
```

---

## 3. Configurer les secrets GitHub

Aller dans **Settings → Secrets and variables → Actions** du repository.

### Secrets requis

| Secret | Contenu | Comment l'obtenir |
|--------|---------|-------------------|
| `GPG_PRIVATE_KEY` | Contenu ASCII-armored de `private.key` | `cat private.key` et copier intégralement (y compris les lignes `-----BEGIN/END-----`) |
| `FFE_HOSTNAME` | Hôte du serveur SQL FFE | Fourni par l'équipe Sharly Chess |
| `FFE_USER` | Utilisateur SQL FFE | Fourni par l'équipe Sharly Chess |
| `FFE_PASSWORD` | Mot de passe SQL FFE | Fourni par l'équipe Sharly Chess |
| `FFE_DATABASE` | Nom de la base FFE | Fourni par l'équipe Sharly Chess |
| `CHESS_RESULTS_AES_KEY` | Clé AES Chess-Results | Fourni par l'équipe Sharly Chess |
| `CHESS_RESULTS_AES_IV` | IV AES Chess-Results | Fourni par l'équipe Sharly Chess |

### Vérifier les secrets

Après configuration, lancer un build de test :

```
GitHub Actions → Publish Multi-Arch Flatpak Repo → Run workflow
  (laisser version_tag vide → build dev)
```

Si le build échoue à l'étape "Import GPG key" ou "Inject secrets", vérifier que les secrets sont correctement renseignés (pas d'espace en trop, pas de retour à la ligne manquant).

---

## 4. Configurer le workflow permissions

Le repository doit autoriser les workflows à écrire :

1. **Settings → Actions → General**
2. Section "Workflow permissions" : sélectionner **Read and write permissions**
3. Cocher **Allow GitHub Actions to create and approve pull requests** (pour les Issues auto-créées)

---

## 5. Fonctionnement technique du dépôt OSTree

### Signature des commits

Le workflow importe la clé GPG depuis le secret, puis :

1. `flatpak build-commit-from` importe les commits depuis les repos staging
2. `flatpak build-sign` signe tous les commits de l'application
3. `flatpak build-update-repo --gpg-sign` met à jour et signe le summary

### Fichiers .flatpakrepo

Ces fichiers **n'existent pas** dans le code source. Ils sont **générés dynamiquement** par le workflow `publish-multiarch.yml` à chaque publication (étape "Generate .flatpakrepo files"), puis poussés sur `gh-pages`.

Le workflow :
1. Exporte la clé publique GPG en binaire (`gpg --export`)
2. L'encode en base64
3. Génère les deux fichiers avec un heredoc `cat <<EOF`

**Production** (`sharly-chess.flatpakrepo`) :
```ini
[Flatpak Repo]
Title=Sharly Chess
Url=https://gilleshorn.github.io/sharly-chess/repo/
Homepage=https://github.com/GillesHorn/sharly-chess
Comment=Official repository for Sharly Chess
Description=Play chess and manage tournaments with Sharly Chess
GPGKey=<BASE64_PUBLIC_KEY>
```

**Dev** (`sharly-chess-dev.flatpakrepo`) :
```ini
[Flatpak Repo]
Title=Sharly Chess (Dev)
Url=https://gilleshorn.github.io/sharly-chess/repo-dev/
Homepage=https://github.com/GillesHorn/sharly-chess
Comment=Development builds of Sharly Chess (may be unstable)
Description=Development and testing builds for Sharly Chess
GPGKey=<BASE64_PUBLIC_KEY>
```

Les deux fichiers partagent la même clé GPG. Le champ `Url` est la seule différence significative : il pointe vers `repo/` (prod) ou `repo-dev/` (dev).

URLs publiques :
- https://gilleshorn.github.io/sharly-chess/sharly-chess.flatpakrepo
- https://gilleshorn.github.io/sharly-chess/sharly-chess-dev.flatpakrepo

### Static deltas

Deux types de deltas sont générés :

1. **Deltas incrémentaux** (`--generate-static-deltas`) : Pour les mises à jour version-à-version
2. **Deltas from-empty** (`ostree static-delta generate --empty REF`) : Pour la première installation complète

Sans les deltas from-empty, une première installation télécharge des milliers de petits objets OSTree individuellement (très lent). Avec, tout est regroupé en quelques gros fichiers.

### Historique des commits

`flatpak build-commit-from --force` préserve la chaîne de commits en reparentant le nouveau commit sur le tip existant du dépôt de destination. Cela permet :

- `flatpak remote-info --log` pour voir l'historique
- `flatpak update --commit=HASH` pour rollback
- Les delta updates entre versions consécutives

---

## 6. Renouvellement des clés GPG

Si la clé GPG expire ou est compromise :

1. Générer une nouvelle paire de clés (voir section 1)
2. Mettre à jour le secret `GPG_PRIVATE_KEY` dans GitHub
3. **Rebuilder toutes les versions actives** pour les re-signer :
   ```
   GitHub Actions → Publish Multi-Arch Flatpak Repo → Run workflow
     version_tag: <chaque_version>
   ```
4. Les utilisateurs devront re-ajouter le remote (car le `GPGKey` dans le `.flatpakrepo` aura changé) :
   ```bash
   flatpak remote-delete --user sharly-chess
   flatpak remote-add --user sharly-chess https://gilleshorn.github.io/sharly-chess/sharly-chess.flatpakrepo
   ```

---

## 7. Dépannage infrastructure

### Le build réussit mais GitHub Pages ne se met pas à jour

- Vérifier que GitHub Pages est bien activé sur la branche `gh-pages`
- Vérifier que `.nojekyll` existe à la racine de `gh-pages`
- Attendre quelques minutes (propagation GitHub Pages)
- Vérifier dans **Settings → Pages** qu'il n'y a pas d'erreur de déploiement

### Erreur "GPG: no secret key"

- Vérifier que le secret `GPG_PRIVATE_KEY` contient bien la clé **privée** complète (y compris les lignes d'en-tête)
- S'assurer qu'il n'y a pas d'espace ou de retour à la ligne parasite

### Le dépôt OSTree grossit trop

- `--prune` est déjà activé dans le workflow pour nettoyer les objets obsolètes
- Si nécessaire, recréer le dépôt de zéro en supprimant `repo/` ou `repo-dev/` sur `gh-pages`, puis rebuilder

### Taille limite GitHub Pages

GitHub Pages a une limite de 1 Go par repository. Surveiller la taille de `gh-pages` :

```bash
git checkout gh-pages
du -sh repo/ repo-dev/
```

Si la limite est approchée, envisager de réduire la profondeur d'historique ou migrer vers un hébergement alternatif.

---

## 8. Configurer un nouveau fork (prérequis)

Si un autre développeur ou l'organisation `Sharly-Chess` veut reproduire cette infrastructure sur un autre compte GitHub, voici **tout ce qui doit être adapté**.

### 8.1 Prérequis upstream

Le repo upstream `Sharly-Chess/sharly-chess` doit :
- Publier des **GitHub Releases** avec des tags (ex: `3.6.0`) et le flag `isPrerelease` correctement positionné
- Le workflow `sync-upstream.yml` utilise l'API `repos/Sharly-Chess/sharly-chess/releases` pour détecter les nouvelles versions

### 8.2 Créer le fork et les branches

1. Fork le repo upstream
2. Créer la branche `linux-flatpak` (branche principale du fork)
3. Créer la branche `gh-pages` (orpheline, pour héberger les dépôts OSTree — voir section 2)
4. Activer GitHub Pages sur `gh-pages` (voir section 2)

### 8.3 Générer et configurer les clés GPG

Suivre la section 1 de ce document, puis ajouter le secret `GPG_PRIVATE_KEY` (section 3).

### 8.4 Configurer les secrets GitHub

Tous les secrets listés en section 3 (GPG + FFE + Chess-Results).

### 8.5 Références hardcodées à modifier

Les fichiers suivants contiennent des URLs ou noms de repo hardcodés. Remplacer `GillesHorn` et `gilleshorn.github.io` par les nouvelles valeurs.

#### Workflows (`.github/workflows/`)

| Fichier | Ce qui change | Lignes |
|---------|--------------|--------|
| `publish-multiarch.yml` | URLs GitHub Pages dans les `.flatpakrepo` générés (`Url=`, `Homepage=`) | Étape "Generate .flatpakrepo files" |
| `sync-upstream.yml` | URL du remote upstream (`Sharly-Chess/sharly-chess`) — **uniquement si l'upstream change** | Étapes "Add upstream remote" + "Determine release to sync" + Issues |

#### Scripts

| Fichier | Ce qui change |
|---------|--------------|
| `scripts/rebuild_production_repo.sh` | Variable `REPO="GillesHorn/sharly-chess"` (ligne 19) |

#### Documentation

| Fichier | Ce qui change |
|---------|--------------|
| `flatpak/documentation/INSTALL.md` | Toutes les URLs `gilleshorn.github.io/sharly-chess/` |
| `flatpak/documentation/DEVELOPER_GUIDE.md` | Nom du fork, URLs GitHub Pages |
| `flatpak/documentation/INFRASTRUCTURE.md` | URLs GitHub Pages (ce fichier) |
| `flatpak/documentation/README.md` | Liens rapides vers les dépôts |

#### Configuration Flatpak

| Fichier | Ce qui change |
|---------|--------------|
| `flatpak/configuration/com.sharlychess.SharlyChess.appdata.xml` | URL du bugtracker (ligne `<url type="bugtracker">`) |

> **Note :** Les fichiers du code source (`src/common/engine.py`, `src/antivirus/control.py`, etc.) contiennent aussi des références à `Sharly-Chess/sharly-chess` mais celles-ci pointent vers l'upstream et ne doivent **pas** être modifiées.

### 8.6 Checklist de validation

Après avoir tout configuré :

- [ ] Secrets GitHub configurés (7 secrets)
- [ ] GitHub Pages activé sur `gh-pages`
- [ ] Workflow permissions en "Read and write"
- [ ] `.nojekyll` présent sur `gh-pages`
- [ ] URLs mises à jour dans les workflows et la documentation
- [ ] Lancer un build dev (push sur `linux-flatpak` ou dispatch manuel)
- [ ] Vérifier que le `.flatpakrepo` est accessible via l'URL GitHub Pages
- [ ] Tester l'installation sur une machine Linux : `flatpak remote-add --user ...`
- [ ] Lancer un build production (dispatch avec `version_tag`)
- [ ] Vérifier le rollback : `flatpak remote-info --user --log ...`
